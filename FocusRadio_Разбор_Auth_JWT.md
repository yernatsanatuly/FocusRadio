# 🔐 FocusRadio (Assignment 7): Максимально подробный разбор аутентификации, JWT, bcrypt, RBAC и авторизации

> **Зачем нужен этот файл:** чтобы любой участник команды — даже если раньше никогда не настраивал JWT, bcrypt или ролевую модель — прочитал его и полностью понял:
> 1. **Что** именно мы изменили в проекте после 5–6 заданий и **зачем**;
> 2. **Как** работают хеширование паролей (`bcrypt`), JWT-токены (`PyJWT`) и Bearer-авторизация в FastAPI;
> 3. **В чём разница между аутентификацией (`401`) и авторизацией (`403`)** и как устроены роли (`user`/`admin`) + владение ресурсами;
> 4. **Как** прошла миграция Alembic на уже существующей БД без потери данных;
> 5. **За что отвечает каждый новый и обновлённый файл**;
> 6. **Как красиво показать всё в Swagger UI и уверенно ответить на любой вопрос преподавателя на защите.**

---

## Оглавление

1. [Главная идея простыми словами](#1-главная-идея-простыми-словами)
2. [Все инструменты и понятия «на пальцах» + примеры кода](#2-все-инструменты-и-понятия-на-пальцах--примеры-кода)
3. [Как мы встроили Auth & Authorization в FocusRadio (5 шагов)](#3-как-мы-встроили-auth--authorization-в-focusradio-5-шагов)
4. [Было vs Стало — сравнение на реальном коде](#4-было-vs-стало--сравнение-на-реальном-коде)
5. [Миграция Alembic и обновление сидера демо-данных](#5-миграция-alembic-и-обновление-сидера-демо-данных)
6. [Полная матрица прав доступа: Public vs User vs Admin](#6-полная-матрица-прав-доступа-public-vs-user-vs-admin)
7. [Полная карта новых и обновлённых файлов](#7-полная-карта-новых-и-обновлённых-файлов)
8. [Как проходит запрос от Swagger до PostgreSQL](#8-как-проходит-запрос-от-swagger-до-postgresql)
9. [Как устроены автотесты и как показать всё в Swagger UI](#9-как-устроены-автотесты-и-как-показать-всё-в-swagger-ui)
10. [6 реальных технических ловушек, которые мы учли](#10-6-реальных-технических-ловушек-которые-мы-учли)
11. [Шпаргалка к защите: 15 вопросов преподавателя и готовые ответы](#11-шпаргалка-к-защите-15-вопросов-преподавателя-и-готовые-ответы)

---

## 1. Главная идея простыми словами

### Как проект работал раньше (Assignments 5 и 6)
Раньше никакой настоящей защиты в API не было:
- У модели `User` не было ни пароля, ни роли.
- Вместо аутентификации стояла учебная заглушка: клиент просто писал в заголовке `X-User-Id: 1` — и сервер **на слово верил**, что перед ним действительно Alice!
- В `POST /rooms`, `POST /tasks`, `POST /sessions` можно было вообще передать чужой `"user_id": 1` в JSON-теле и создать задачу или комнату от имени любого человека.
- Любой желающий мог просмотреть чужие задачи (`GET /tasks`), чужие сессии (`GET /sessions`) и даже удалить все треки из каталога (`DELETE /tracks/1?force=true`).

**Аналогия:** это как вход в офис без охраны — достаточно написать на стикере «Я директор» и наклеить себе на лоб, и тебе выдадут ключи от всех кабинетов.

### Как проект работает теперь (Assignment 7)
Теперь в FocusRadio работает полноценная система **аутентификации** и **авторизации**:
1. Пользователь **регистрируется** через `POST /auth/register` — его пароль никогда не сохраняется в открытом виде, а превращается в криптографический хеш `bcrypt` и кладётся в PostgreSQL.
2. Пользователь **входит** через `POST /auth/login` — сервер проверяет пароль и выдаёт **подписанный JWT-токен** (цифровой пропуск с ограниченным сроком действия).
3. При каждом обращении к защищённому эндпоинту клиент передаёт заголовок `Authorization: Bearer <token>`. Сервер проверяет криптографическую подпись токена, срок жизни (`exp`) и сам определяет, кто делает запрос (`current_user`) — **подделать чужой ID невозможно**.
4. Дальше включается **авторизация**:
   - **По ролям (`RBAC`):** управлять каталогом треков, создавать пользователей через `POST /users`, менять роли и модерировать чужие ресурсы может только `admin`.
   - **По владению (`Ownership`):** обычный пользователь (`user`) видит, изменяет и удаляет только **свои** задачи, сессии, профиль и комнаты. При попытке тронуть чужое сервер жёстко отвечает `403 Forbidden`.

---

## 2. Все инструменты и понятия «на пальцах» + примеры кода

### 1) Аутентификация (`401`) vs Авторизация (`403`) — главное различие
Эти два слова часто путают, а преподаватели почти всегда про них спрашивают:

| Понятие | Вопрос | Когда срабатывает ошибка | Код HTTP |
|---|---|---|---|
| **Аутентификация (Authentication)** | *«Кто ты?»* | Неверный логин/пароль, нет токена, битый или просроченный токен | **`401 Unauthorized`** (+ заголовок `WWW-Authenticate: Bearer`) |
| **Авторизация (Authorization)** | *«Тебе это можно?»* | Мы точно знаем, кто ты (токен валиден), но у тебя нет прав (не `admin` или не владелец ресурса) | **`403 Forbidden`** |

---

### 2) `bcrypt` — безопасное хеширование паролей
**Простыми словами:** пароль нельзя хранить в базе как `"password123"` (если базу украдут — утекут все пароли). И нельзя просто зашифровать его обратимо. Пароль нужно **хешировать** — пропустить через одностороннюю функцию, из результата которой невозможно восстановить исходный пароль.

**Почему именно `bcrypt`, а не `MD5` или `SHA-256`?**
1. `SHA-256` слишком **быстрый** — современная видеокарта перебирает миллиарды паролей в секунду. `bcrypt` намеренно **медленный** (~150–250 мс на проверку), что делает брутфорс бессмысленным.
2. `bcrypt` автоматически генерирует уникальную случайную **соль (salt)** для каждого пользователя. Даже если у Bob и Carol одинаковый пароль `"password123"`, их хеши в PostgreSQL будут **совершенно разными** — таблицы радужных хешей (rainbow tables) не работают.

Пример того, как выглядит хеш в нашей БД:
```text
$2b$12$KIXx8...случайная_соль...хеш_пароля
```
- `$2b$` — версия алгоритма bcrypt;
- `12` — фактор сложности (`2^12 = 4096` раундов);
- остальная строка — соль + результат хеширования.

Наш код в `app/core/security.py`:
```python
def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_BCRYPT_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password or not hashed_password.startswith("$2"):
        return False
    raw = plain_password.encode("utf-8")
    if len(raw) > MAX_BCRYPT_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
    except ValueError:
        return False
```

---

### 3) `JWT` (`PyJWT`) — цифровой пропуск без хранения сессий в БД
**Что такое JWT (JSON Web Token):** строка из трёх частей, разделённых точками:

```text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 . eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzk1... . SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
└───────────── Header ──────────────┘   └──────────────────── Payload ────────────────────┘   └─────────────── Signature ───────────────┘
```

1. **Header** — алгоритм подписи (`HS256`) и тип (`JWT`).
2. **Payload (данные токена)** — какие поля мы туда кладём в `app/core/security.py`:
   - `sub`: `"1"` — ID пользователя (по стандарту RFC 7519 `sub` всегда строка!);
   - `role`: `"admin"` или `"user"`;
   - `type`: `"access"` — чтобы нельзя было подсунуть другой тип токена;
   - `iat`: время выпуска;
   - `exp`: время истечения (по умолчанию через `60` минут, настраивается в `ACCESS_TOKEN_EXPIRE_MINUTES`).
3. **Signature (подпись)** — вычисляется с помощью `HMAC-SHA256(Header + "." + Payload, JWT_SECRET_KEY)`.

**Важно помнить для защиты:**
- Payload в JWT **НЕ зашифрован** (он просто закодирован в Base64Url — любой может прочитать `sub` и `role`). Поэтому в JWT **никогда не кладут пароль** или секреты!
- Но **подделать** Payload (например, поменять `"role": "user"` на `"role": "admin"` или `"sub": "2"` на `"sub": "1"`) **невозможно**: без секретного ключа `JWT_SECRET_KEY` подпись перестанет совпадать, и `jwt.decode()` мгновенно выкинет `InvalidTokenError` → **`401 INVALID_TOKEN`**.

Наш код в `app/core/security.py`:
```python
def create_access_token(
    user_id: int,
    role: UserRole,
    *,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, int]:
    delta = expires_delta if expires_delta is not None else timedelta(
        minutes=settings.access_token_expire_minutes
    )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": now,
        "exp": now + delta,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, max(0, int(delta.total_seconds()))
```

---

### 4) Переиспользуемые зависимости FastAPI (`CurrentUser` и `AdminUser`)
Чтобы не копировать проверку токена в каждом из 27 эндпоинтов, мы написали **две зависимости** в `app/core/dependencies.py`:

```python
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="JWT Bearer access token obtained from POST /auth/login",
)

def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: DB,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise UnauthorizedError("Missing Bearer access token", code="NOT_AUTHENTICATED")

    payload = decode_access_token(credentials.credentials)
    user_id = int(payload["sub"])
    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Authenticated user no longer exists", code="USER_NOT_FOUND")
    return user

CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    if not current_user.is_admin:
        raise ForbiddenError("Administrator privileges are required for this action", code="ADMIN_REQUIRED")
    return current_user

AdminUser = Annotated[User, Depends(require_admin)]
```

**Смотри, как изящно это работает в роутерах:**
- Нужен любой залогиненный пользователь? Просто пишем `current_user: CurrentUser` в параметрах функции роутера — и FastAPI сама вытащит токен, проверит подпись/срок, загрузит объект `User` из PostgreSQL и передаст его в функцию!
- Нужен именно администратор (например, `POST /tracks`)? Пишем `_admin: AdminUser` — `require_admin` сама сначала вызовет `CurrentUser` (`401`, если нет токена), а потом проверит `role == ADMIN` (`403`, если обычный юзер).
- Дополнительно: поскольку `get_current_user` **каждый раз** читает пользователя из БД по `sub`, если администратор повысит/понизит роль пользователя или удалит его аккаунт, изменение вступит в силу **мгновенно**, не дожидаясь истечения старого токена!

---

## 3. Как мы встроили Auth & Authorization в FocusRadio (5 шагов)

1. **Зависимости и конфигурация:**
   - Добавили в `requirements.txt` пакеты `PyJWT>=2.9.0`, `bcrypt>=4.2.0`, `python-multipart>=0.0.9`.
   - Вынесли `JWT_SECRET_KEY`, `JWT_ALGORITHM` и `ACCESS_TOKEN_EXPIRE_MINUTES` в `.env`, `.env.example` и `app/config.py`.
   - Добавили `UnauthorizedError` (`401` + заголовок `WWW-Authenticate: Bearer`) в `app/core/exceptions.py`.

2. **Модель `User`, сидер и миграция PostgreSQL:**
   - Добавили `UserRole` (`user`, `admin`) в `app/models/enums.py`.
   - Добавили колонки `hashed_password` и `role` (с индексом `ix_users_role`) + свойство `is_admin` в `app/models/user.py`.
   - Сгенерировали, доработали и применили миграцию Alembic `4aa834cf96ea_add_user_auth_fields.py`.
   - Обновили `app/core/seed.py`: демо-пользователи `alice` (`admin`), `bob` (`user`), `carol` (`user`) получают bcrypt-хеш пароля `password123`.

3. **Модуль аутентификации (`/auth`):**
   - `app/core/security.py` — `hash_password`, `verify_password`, `create_access_token`, `decode_access_token`.
   - `app/schemas/auth.py` — `RegisterRequest`, `LoginRequest` (логин по `username` или `email`), `TokenResponse`.
   - `app/services/auth_service.py` — регистрация с проверкой дубликатов и логин с выдачей JWT.
   - `app/routers/auth.py` — эндпоинты `POST /auth/register`, `POST /auth/login`, `GET /auth/me` (подключён в `app/main.py`).

4. **Убрали все «дыры» в схемах и перевели все эндпоинты на JWT + RBAC/Ownership:**
   - Полностью удалили `ActingUserId` (`X-User-Id`) из `app/core/dependencies.py` и `ensure_actor_exists` из `app/services/common.py`.
   - Убрали `user_id` / `owner_id` из входящих схем `RoomCreate`, `JoinRoomRequest`, `SessionCreate`, `TaskCreate` — теперь владелец всегда берётся из `current_user.id`.
   - Заменили проверку владельца на единый хелпер `ensure_owner_or_admin(actor, owner_id, what)`.
   - Закрыли `GET /tasks`, `GET /tasks/{id}`, `GET /sessions`, `GET /sessions/{id}` так, чтобы обычный пользователь видел **только свои** данные, а при запросе чужих получал `403`.
   - Закрыли `POST/PATCH/DELETE /tracks`, `POST /users` и новый эндпоинт `PATCH /users/{user_id}/role` через `AdminUser`.

5. **Тестирование и документация:**
   - Перевели все 8 интеграционных тестов в `tests/test_api.py` на реальный JWT Bearer.
   - Написали 6 подробных тестов в `tests/test_auth.py`, покрывающих все требования задания (итого **14/14 passed** на PostgreSQL).
   - Обновили `README.md`.

---

## 4. Было vs Стало — сравнение на реальном коде

### Зависимости аутентификации (`app/core/dependencies.py`)
```python
# ❌ БЫЛО (Assignments 5–6): любой мог подставить чужой ID в заголовок
ActingUserId = Annotated[int, Header(alias="X-User-Id", ge=1)]

# ✅ СТАЛО (Assignment 7): реальный JWT Bearer + проверка в PostgreSQL
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
```

### Создание задачи (`app/schemas/tasks.py` и `app/routers/tasks.py`)
```python
# ❌ БЫЛО: user_id передавался в JSON — можно было создать задачу чужому юзеру!
class TaskCreate(BaseModel):
    user_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)

@router.post("")
def create_task(data: TaskCreate, service: Tasks):
    return service.create(data)

# ✅ СТАЛО: user_id убран из тела запроса, владелец берётся из JWT-токена
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)

@router.post("", responses=error_responses(401, 409, 422))
def create_task(data: TaskCreate, current_user: CurrentUser, service: Tasks):
    return service.create(current_user, data)
```

### Просмотр списка задач (`app/services/task_service.py`)
```python
# ❌ БЫЛО: любой без токена мог прочитать все чужие задачи
def list(self, *, user_id, ...):
    stmt = select(Task)
    if user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)

# ✅ СТАЛО: обычный user видит только свои задачи; при попытке запросить чужие -> 403
def list(self, *, actor: User, user_id: Optional[int], ...):
    if not actor.is_admin:
        if user_id is not None and user_id != actor.id:
            raise ForbiddenError("You can only view your own tasks", code="NOT_RESOURCE_OWNER")
        user_id = actor.id
```

### Управление каталогом треков (`app/routers/tracks.py`)
```python
# ❌ БЫЛО: любой мог добавить или удалить трек
@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_track(track_id: int, service: Tracks, force: bool = False):
    service.delete(track_id, force=force)

# ✅ СТАЛО: только администратор (без токена -> 401, обычный юзер -> 403)
@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=error_responses(401, 403, 404, 409))
def delete_track(track_id: int, _admin: AdminUser, service: Tracks, force: bool = False):
    service.delete(track_id, force=force)
```

### Проверка владельца (`app/services/common.py`)
```python
# ❌ БЫЛО:
def ensure_same_user(acting_user_id: int, owner_id: int, what: str) -> None:
    if acting_user_id != owner_id:
        raise ForbiddenError(...)

# ✅ СТАЛО: доступ есть у владельца ИЛИ у администратора
def ensure_owner_or_admin(actor: User, owner_id: int, what: str) -> None:
    if actor.id != owner_id and not actor.is_admin:
        raise ForbiddenError(
            f"Only the owner or an administrator can access this {what}",
            code="NOT_RESOURCE_OWNER",
            details={"owner_id": owner_id, "acting_user_id": actor.id},
        )
```

---

## 5. Миграция Alembic и обновление сидера демо-данных

### Вторая ревизия в истории Alembic
Теперь цепочка миграций выглядит так:
```text
9458035c95c7 (initial_schema)  ──▶  4aa834cf96ea (add_user_auth_fields) [HEAD]
```

Что делает миграция `alembic/versions/4aa834cf96ea_add_user_auth_fields.py`:
1. Создаёт в PostgreSQL нативный тип `user_role_enum` (`'user'`, `'admin'`) с `checkfirst=True`.
2. Добавляет колонку `users.hashed_password VARCHAR(255) NOT NULL`.
   - **Хитрость для непустой БД:** если в `users` уже были старые строки (`alice`, `bob`, `carol` из 6-го задания), обычный `ADD COLUMN ... NOT NULL` упадёт с ошибкой PostgreSQL! Поэтому мы сначала добавляем колонку с временным `server_default="!unusable!"`, а следующей строкой убираем `server_default` (`op.alter_column(..., server_default=None)`).
   - Почему `"!unusable!"`? Потому что ни один bcrypt-хеш не начинается с `!` — наша `verify_password()` проверяет `startswith("$2")`, поэтому войти под немигрированной записью невозможно!
3. Добавляет колонку `users.role user_role_enum NOT NULL DEFAULT 'user'` и индекс `ix_users_role`.
4. В `downgrade()` аккуратно удаляет индекс, обе колонки и сам тип `user_role_enum` (`drop(..., checkfirst=True)`). Мы проверили полный цикл `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` — всё отрабатывает чисто.

### Бесшовное обновление в `app/core/seed.py`
При старте приложения (`lifespan` в `app/main.py`):
- Если база пустая — сидер создаёт `alice` (`admin`), `bob` (`user`), `carol` (`user`) с bcrypt-хешем пароля `password123`.
- Если база уже была заполнена в 6-м задании и только что прошла миграцию — сидер находит демо-пользователей с маркером `"!unusable!"`, прописывает им реальный bcrypt-хеш и назначает `alice` роль `admin`.

---

## 6. Полная матрица прав доступа: Public vs User vs Admin

В проекте объединены **оба подхода авторизации**, требуемые в задании: **RBAC** (разделение ролей `user` / `admin`) и **Ownership** (владение ресурсами).

| Эндпоинт | Без токена | Обычный `user` | `admin` |
|---|---|---|---|
| `GET /`, `GET /docs`, `GET /leaderboard` | `200` | `200` | `200` |
| `GET /tracks`, `GET /tracks/{id}` | `200` | `200` | `200` |
| `GET /rooms`, `GET /rooms/{id}`, `/members`, `/recommended-tracks`, `/leaderboard` | `200` | `200` | `200` |
| `POST /auth/register`, `POST /auth/login` | `201` / `200` | `201` / `200` | `201` / `200` |
| `GET /auth/me` | `401` | `200` (свой профиль) | `200` (свой профиль) |
| `GET /users`, `GET /users/{id}`, `/stats`, `/achievements` | `401` | `200` | `200` |
| `PATCH /users/{id}`, `DELETE /users/{id}` | `401` | Только **свой** (`403` на чужой) | **Любой** пользователь |
| `POST /users`, `PATCH /users/{id}/role` | `401` | `403 ADMIN_REQUIRED` | `201` / `200` |
| `POST /tracks`, `PATCH /tracks/{id}`, `DELETE /tracks/{id}` | `401` | `403 ADMIN_REQUIRED` | `201` / `200` / `204` |
| `POST /rooms`, `POST /rooms/{id}/members` | `401` | `201` (от своего имени) | `201` (от своего имени) |
| `PATCH /rooms/{id}`, `DELETE /rooms/{id}` | `401` | Только **владелец** комнаты (`403` остальным) | **Любая** комната |
| `DELETE /rooms/{id}/members/{uid}` | `401` | Выйти сам **или** кикнуть, если владелец комнаты (`403` иначе) | Кикнуть любого участника |
| `PUT /rooms/{id}/track`, `DELETE /rooms/{id}/track` | `401` | Только **участник** комнаты (`403 NOT_A_MEMBER`) | Только **участник** комнаты |
| `POST /tasks` | `401` | `201` (создаётся для себя) | `201` (для себя) |
| `GET /tasks` | `401` | Только **свои** задачи (`403` при чужом `user_id`) | **Все** задачи или фильтр по любому `user_id` |
| `GET /tasks/{id}`, `PATCH /tasks/{id}`, `DELETE /tasks/{id}` | `401` | Только **своя** задача (`403` на чужую) | **Любая** задача |
| `POST /sessions` | `401` | `201` (свой таймер; чужую задачу привязать нельзя → `403`) | `201` |
| `GET /sessions` | `401` | Только **своя** история (`403` при чужом `user_id`) | **Вся** история |
| `GET /sessions/{id}`, `PATCH`, `DELETE`, `pause`, `resume`, `complete`, `cancel` | `401` | Только **своя** сессия (`403` на чужую) | **Любая** сессия |

---

## 7. Полная карта новых и обновлённых файлов

### Новые файлы
| Файл | За что отвечает |
|---|---|
| `app/core/security.py` | Хеширование и проверка паролей (`bcrypt`), генерация и валидация JWT-токенов (`PyJWT`). |
| `app/schemas/auth.py` | Pydantic-схемы `RegisterRequest`, `LoginRequest` (логин по `username` или `email`) и `TokenResponse`. |
| `app/services/auth_service.py` | Логика регистрации (`register`) и аутентификации (`login`). |
| `app/routers/auth.py` | HTTP-эндпоинты `POST /auth/register`, `POST /auth/login`, `GET /auth/me`. |
| `alembic/versions/4aa834cf96ea_add_user_auth_fields.py` | Миграция БД: добавление `user_role_enum`, `users.hashed_password`, `users.role` и индекса `ix_users_role`. |
| `tests/test_auth.py` | 6 комплексных тестов на регистрацию, bcrypt в БД, дубликаты, логин, 401 (без/битый/просроченный/поддельный/удалённый токен), RBAC и ownership. |

### Обновлённые файлы
| Файл | Что изменилось |
|---|---|
| `requirements.txt` | Добавлены `PyJWT>=2.9.0`, `bcrypt>=4.2.0`, `python-multipart>=0.0.9`. |
| `app/config.py`, `.env`, `.env.example` | Добавлены `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, версия API обновлена до `3.0.0`. |
| `app/core/exceptions.py`, `app/schemas/common.py` | Добавлены `headers` в `AppError`, исключение `UnauthorizedError (401)` с `WWW-Authenticate: Bearer`, описание кода `401` в OpenAPI. |
| `app/core/dependencies.py` | Удалён `ActingUserId` (`X-User-Id`); добавлены `bearer_scheme`, `get_current_user` (`CurrentUser`), `require_admin` (`AdminUser`), `Auth`. |
| `app/models/enums.py`, `app/models/user.py` | Добавлен `UserRole` (`user`, `admin`), поля `hashed_password`, `role` и свойство `is_admin`. |
| `app/core/seed.py` | Сидирование демо-пользователей с bcrypt-хешем `password123` и ролями (`alice` — `admin`, `bob`/`carol` — `user`) + автообновление после миграции. |
| `app/main.py` | Подключён `auth.router`. |
| `app/schemas/users.py`, `rooms.py`, `sessions.py`, `tasks.py` | В `UserResponse` добавлена `role`; в `UserCreate` добавлены `password` и `role`; добавлена `UserRoleUpdate`; из `RoomCreate`, `JoinRoomRequest`, `SessionCreate`, `TaskCreate` убраны `user_id`/`owner_id`. |
| `app/services/common.py`, `user_service.py`, `room_service.py`, `task_service.py`, `session_service.py` | Вместо `acting_user_id: int` сервисы принимают `actor: User`; добавлены `ensure_owner_or_admin`, `update_role`, фильтрация списков задач/сессий по текущему пользователю. |
| `app/routers/users.py`, `tracks.py`, `rooms.py`, `tasks.py`, `sessions.py` | Подключены зависимости `CurrentUser` и `AdminUser`, добавлен `PATCH /users/{user_id}/role`, обновлены описания и коды ответов OpenAPI. |
| `tests/test_api.py` | Все интеграционные тесты переведены с `X-User-Id` на реальный логин и `Authorization: Bearer <token>`. |
| `README.md` | Добавлен раздел про Authentication & Authorization, таблица прав доступа, демо-аккаунты и инструкция для Swagger UI. |

---

## 8. Как проходит запрос от Swagger до PostgreSQL

### Сценарий А: Логин (`POST /auth/login`)
```text
1. Клиент отправляет POST /auth/login
   Body: { "username": "bob", "password": "password123" }
        │
        ▼
2. Pydantic (LoginRequest)
   Проверяет, что передан username или email, приводит к нижнему регистру,
   проверяет, что password не пустой (иначе сразу 422 VALIDATION_ERROR).
        │
        ▼
3. AuthService.login()
   а) Делает SELECT * FROM users WHERE username = 'bob' OR email = 'bob'.
   б) Вызывает verify_password("password123", user.hashed_password) через bcrypt.
   в) Если пользователь не найден ИЛИ пароль не совпал →
      UnauthorizedError (401 INVALID_CREDENTIALS + WWW-Authenticate: Bearer).
   г) Если всё верно → create_access_token(user.id=2, user.role=USER)
      подписывает JWT ключом JWT_SECRET_KEY (HS256, exp = now + 60 min).
        │
        ▼
4. Ответ 200 OK:
   { "access_token": "eyJhbG...", "token_type": "bearer", "expires_in": 3600, "user": { ... } }
```

### Сценарий Б: Защищённый запрос (`PATCH /tasks/1`)
```text
1. Клиент отправляет PATCH /tasks/1
   Header: Authorization: Bearer eyJhbG...
   Body:   { "status": "done" }
        │
        ▼
2. FastAPI Dependency Injection: get_current_user()
   а) HTTPBearer извлекает строку токена из заголовка Authorization.
      Нет заголовка? → 401 NOT_AUTHENTICATED.
   б) decode_access_token() проверяет подпись (JWT_SECRET_KEY),
      срок действия (exp) и type == "access".
      Просрочен? → 401 TOKEN_EXPIRED. Подделан? → 401 INVALID_TOKEN.
   в) Берёт user_id = int(payload["sub"]) и загружает User из PostgreSQL.
      Удалён? → 401 USER_NOT_FOUND.
   г) Передаёт живой ORM-объект current_user: User в роутер.
        │
        ▼
3. TaskService.update(task_id=1, actor=current_user, data=...)
   а) Находит Task(id=1) в PostgreSQL (нет → 404 TASK_NOT_FOUND).
   б) Вызывает ensure_owner_or_admin(actor, task.user_id, "task"):
      • Если это задача Bob (user_id=2), а пришёл Carol (id=3, role=user)
        → 403 NOT_RESOURCE_OWNER!
      • Если пришёл Bob (id=2) или Admin Alice (role=admin) → разрешено.
   в) Обновляет status = 'done', начисляет +15 XP в users, сохраняет ачивки
      и фиксирует всё одной транзакцией self.db.commit().
        │
        ▼
4. Ответ 200 OK с обновлённой задачей и новыми достижениями.
```

---

## 9. Как устроены автотесты и как показать всё в Swagger UI

### Автотесты (`pytest -v`)
В проекте **14 автоматических тестов**, которые прогоняются против настоящей тестовой БД PostgreSQL `focusradio_test` (перед запуском тесты сами выполняют `alembic upgrade head`, а перед каждым тестом очищают таблицы и заливают свежие демо-данные):

- **`tests/test_api.py` (8 тестов):** все бизнес-процессы (пользователи, комнаты, адаптивное аудио, фокус-сессии, задачи, XP/стрики/лидерборд, персистентность в PostgreSQL, каскадные удаления), теперь работающие через реальный `POST /auth/login` и `Authorization: Bearer`.
- **`tests/test_auth.py` (6 тестов):**
  1. `test_register_hashes_password_and_prevents_duplicates` — проверяет `201`, что в PostgreSQL лежит именно `$2...` bcrypt-хеш, что `role: "admin"` в теле регистрации игнорируется, что дубликаты `username`/`email` дают `409`, а короткий пароль — `422`.
  2. `test_login_by_username_or_email_and_invalid_credentials` — вход по `username`, по `email`, по email в поле `username`; неверный пароль и несуществующий пользователь дают `401 INVALID_CREDENTIALS`.
  3. `test_protected_endpoints_reject_missing_invalid_and_expired_tokens` — 6 защищённых роутов без токена (`401`), битый JWT (`401`), токен с чужим секретом (`401`), просроченный токен (`401 TOKEN_EXPIRED`), токен удалённого юзера (`401 USER_NOT_FOUND`), валидный токен (`200`).
  4. `test_role_based_access_control_tracks_and_user_admin` — обычный юзер получает `403` на `POST/PATCH/DELETE /tracks`, `POST /users`, `PATCH /users/{id}/role`; админ успешно создаёт/правит/удаляет треки, не может разжаловать последнего админа (`409`), повышает Bob до `admin` — и у Bob сразу появляются права.
  5. `test_task_and_session_ownership_restrictions` — Carol не видит задачи и сессии Bob в списках, получает `403` на чтение/изменение/паузу/завершение/отмену/удаление его ресурсов, а админ видит всё.
  6. `test_room_and_user_ownership_vs_admin_moderation` — Carol не может редактировать/закрывать комнату Bob, кикать его или менять его аккаунт (`403`), а админ Alice может модерировать комнату и удалять аккаунт.

Запуск:
```bash
docker compose up -d
source .venv/bin/activate
pytest -v
```

### Пошаговая демонстрация преподавателю в Swagger UI (`/docs`)
1. Запусти проект:
   ```bash
   docker compose up -d
   source .venv/bin/activate
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```
2. Открой `http://localhost:8000/docs`.
3. **Шаг 1 — Защита без токена (`401`):**
   - Попробуй выполнить `GET /auth/me` или `GET /tasks` без авторизации → сразу **`401 NOT_AUTHENTICATED`**.
4. **Шаг 2 — Регистрация (`201`) и защита от дубликатов (`409`):**
   - `POST /auth/register` с `username: "student1"`, `email: "student1@test.com"`, `password: "SecurePass123"` → **`201 Created`**, в ответе `"role": "user"`, поля пароля нет.
   - Повтори тот же запрос → **`409 USERNAME_TAKEN`**.
5. **Шаг 3 — Логин (`200` и `401`):**
   - `POST /auth/login` с неверным паролем → **`401 INVALID_CREDENTIALS`**.
   - `POST /auth/login` с правильным паролем → **`200 OK`**, скопируй `access_token`.
   - Нажми зелёную кнопку **Authorize** справа сверху в Swagger UI, вставь токен и нажми **Authorize**.
6. **Шаг 4 — Работа под обычным пользователем + проверки `403`:**
   - `GET /auth/me` → вернёт профиль `student1`.
   - `POST /tasks` (без `user_id`!) → создаст личную задачу `id=1`.
   - Попробуй `POST /tracks` (требуется `admin`) → **`403 ADMIN_REQUIRED`**.
   - Попробуй `PATCH /users/2` (чужой профиль Bob) → **`403 NOT_RESOURCE_OWNER`**.
7. **Шаг 5 — Работа под администратором (`alice`):**
   - Выйди в **Authorize** (**Logout**), залогинься через `POST /auth/login` как `{"username": "alice", "password": "password123"}`, вставь её токен в **Authorize**.
   - `GET /tasks` → админ видит задачу `student1`.
   - `POST /tracks` → **`201 Created`** (админу разрешено управлять каталогом треков!).

---

## 10. 6 реальных технических ловушек, которые мы учли

Если упомянуть эти детали на защите — сразу видно глубокое понимание безопасности и FastAPI:

1. **Прямой `bcrypt` вместо устаревшего `passlib` + лимит 72 байта:** библиотека `passlib` давно не обновляется и ломается с новыми версиями `bcrypt >= 4.1` и Python 3.12+. Мы подключили официальный пакет `bcrypt` напрямую и добавили валидацию длины пароля в UTF-8 байтах (≤ 72 байта) на уровне Pydantic, чтобы длинный пароль (в том числе с кириллицей или эмодзи) возвращал аккуратный `422`, а не падал с `500`.
2. **`HTTPBearer(auto_error=False)` ради правильного `401`:** стандартный `HTTPBearer(auto_error=True)` в части версий FastAPI/Starlette отдаёт `403 Forbidden`, когда заголовок `Authorization` вообще отсутствует (что противоречит стандарту HTTP!). С `auto_error=False` мы сами выбрасываем `UnauthorizedError` с кодом **`401 Unauthorized`**, заголовком `WWW-Authenticate: Bearer` и тем же JSON-форматом ошибок, что и во всём API.
3. **Защита от подмены владельца (IDOR) и самоназначения роли (Mass Assignment):**
   - Мы полностью убрали `user_id` и `owner_id` из схем создания комнат, задач и сессий — клиент физически не может создать сущность от чужого имени.
   - В `RegisterRequest` нет поля `role` — даже если злоумышленник отправит `"role": "admin"` в JSON при регистрации, Pydantic его проигнорирует, и в БД запишется `UserRole.USER`.
4. **Безопасная миграция на непустой БД:** `alembic --autogenerate` сгенерировал `ADD COLUMN hashed_password NOT NULL` без дефолта и без создания `user_role_enum`. Мы вручную дописали создание/удаление `user_role_enum` и временный `server_default="!unusable!"`, чтобы миграция не ломалась на уже заполненных базах команды и проверялась в обе стороны (`upgrade`/`downgrade`).
5. **Защита от потери последнего администратора:** в `PATCH /users/{user_id}/role` стоит проверка — нельзя понизить роль последнему оставшемуся `admin` (`409 LAST_ADMIN_REQUIRED`), иначе система останется вообще без администраторов.
6. **Защита от перебора пользователей (User Enumeration):** при логине с несуществующим `username`/`email` и при логине с неверным паролем API возвращает абсолютно одинаковую ошибку `401 INVALID_CREDENTIALS`, не подсказывая злоумышленнику, какие логины зарегистрированы в системе.

---

## 11. Шпаргалка к защите: 15 вопросов преподавателя и готовые ответы

### 1. «В чём разница между аутентификацией и авторизацией?»
**Аутентификация** проверяет личность пользователя (*«кто ты?»* — логин/пароль или JWT-токен; при провале возвращается **`401 Unauthorized`**). **Авторизация** проверяет права доступа уже известного пользователя (*«можно ли тебе это действие?»* — роль `admin` или владение ресурсом; при отказе возвращается **`403 Forbidden`**).

### 2. «Почему вы не храните пароли в открытом виде и почему выбрали именно `bcrypt`?»
Если база данных утечёт, открытые пароли сразу скомпрометируют аккаунты пользователей. `bcrypt` — это односторонняя медленная функция хеширования со встроенной случайной **солью** для каждого пароля: из хеша нельзя восстановить пароль, одинаковые пароли дают разные хеши, а намеренная медленность защищает от перебора (brute-force).

### 3. «Из чего состоит JWT и можно ли подделать в нём роль `admin`?»
JWT состоит из трёх частей: **Header** (алгоритм `HS256`), **Payload** (`sub`, `role`, `type`, `iat`, `exp`) и **Signature** (HMAC-подпись на секретном ключе `JWT_SECRET_KEY`). Payload можно прочитать (это Base64Url, не шифрование), но **изменить его нельзя**: при изменении хотя бы одного символа подпись перестанет совпадать, и `jwt.decode()` отклонит токен с `401 INVALID_TOKEN`.

### 4. «Что случится, если срок действия токена истёк?»
В каждый токен мы записываем claim `exp` (`now + ACCESS_TOKEN_EXPIRE_MINUTES`). При проверке `PyJWT` автоматически сверяет `exp` с текущим UTC-временем, ловит `ExpiredSignatureError` и возвращает **`401 Unauthorized`** с кодом `TOKEN_EXPIRED`. Пользователю нужно снова пройти `POST /auth/login`.

### 5. «Как именно реализована переиспользуемая зависимость текущего пользователя?»
В `app/core/dependencies.py` определена функция `get_current_user` (алиас `CurrentUser = Annotated[User, Depends(get_current_user)]`). Она извлекает Bearer-токен через `HTTPBearer`, декодирует и валидирует его через `decode_access_token()`, достаёт пользователя из PostgreSQL по `sub` и передаёт ORM-объект `User` в роутер. Поверх неё построена зависимость `AdminUser` (`require_admin`), проверяющая `current_user.is_admin`.

### 6. «Зачем в `get_current_user` ходить в базу данных, если `user_id` и `role` уже есть в токене?»
Потому что токен может жить 60 минут, а за это время пользователя могли удалить или поменять ему роль (`admin` ↔ `user`). Загрузка `db.get(User, user_id)` гарантирует, что удалённый пользователь сразу получит `401 USER_NOT_FOUND`, а изменение роли начнёт действовать немедленно.

### 7. «Как вы защитились от того, чтобы пользователь зарегистрировался сразу как `admin`?»
В схеме `RegisterRequest` поля `role` вообще нет, а в `AuthService.register()` жёстко прописано `role=UserRole.USER`. Создать или повысить администратора может только уже существующий администратор через `POST /users` или `PATCH /users/{id}/role`.

### 8. «Как вы разделили права между обычным пользователем и администратором?»
Мы совместили **RBAC** и **Resource Ownership**:
- **RBAC (`admin` only):** добавление/редактирование/удаление треков в каталоге (`POST/PATCH/DELETE /tracks`), создание юзеров через `POST /users`, смена ролей (`PATCH /users/{id}/role`) и модерация чужих комнат/профилей/задач.
- **Ownership (`user`):** обычный пользователь работает только со своими задачами (`GET/PATCH/DELETE /tasks`), своими фокус-сессиями (`GET/PATCH/DELETE/pause/resume/complete/cancel /sessions`), своим профилем (`PATCH/DELETE /users/{id}`) и комнатами, которыми владеет (`PATCH/DELETE /rooms/{id}`).

### 9. «Что мешает пользователю Bob создать задачу или запустить таймер от имени Alice?»
Ничего не позволит: мы удалили `user_id` и `owner_id` из схем `TaskCreate`, `SessionCreate`, `RoomCreate` и `JoinRoomRequest`. Владелец всегда берётся на сервере из `current_user.id`, полученного из подписанного JWT-токена. А при попытке привязать чужую задачу к своей сессии `_validate_task` возвращает `403 TASK_NOT_OWNED`.

### 10. «Что вернёт API, если обычный пользователь вызовет `GET /tasks` или `GET /tasks?user_id=1`?»
- `GET /tasks` вернёт **только его собственные задачи** (фильтр `Task.user_id == current_user.id` подставляется автоматически).
- `GET /tasks?user_id=1` (чужой ID) вернёт **`403 NOT_RESOURCE_OWNER`**.
- Для администратора оба запроса разрешены: `GET /tasks` вернёт все задачи, а `GET /tasks?user_id=1` отфильтрует задачи конкретного пользователя.

### 11. «Почему при неверном пароле и несуществующем логине возвращается одно и то же сообщение?»
Чтобы не допускать уязвимость **User Enumeration**: злоумышленник не сможет перебором узнать, какие email/username зарегистрированы в базе. В обоих случаях возвращается `401 INVALID_CREDENTIALS`.

### 12. «Где хранится секретный ключ для подписи JWT и почему он не захардкожен жёстко?»
Ключ задаётся через переменную окружения `JWT_SECRET_KEY` в файле `.env` (который добавлен в `.gitignore` и не попадает в Git) и читается через `pydantic-settings` в `app/config.py`. В репозитории лежит только шаблон `.env.example`.

### 13. «Почему вы добавили `WWW-Authenticate: Bearer` в ответы `401`?»
Это требование стандарта HTTP (RFC 6750 / RFC 9110): когда сервер отвечает `401 Unauthorized` на защищённом ресурсе, он обязан сообщить клиенту схему аутентификации (`Bearer`), которую ожидает получить.

### 14. «Как вы добавили `NOT NULL`-колонку `hashed_password` в таблицу `users`, если там уже могли быть строки?»
В миграции Alembic `4aa834cf96ea_add_user_auth_fields.py` мы добавили колонку с временным `server_default="!unusable!"`, затем сразу удалили `server_default` через `op.alter_column(..., server_default=None)`. А `seed_demo_data()` при запуске обновляет демо-аккаунты с этим маркером, выдавая им реальный bcrypt-хеш.

### 15. «Как проверить, что ваша аутентификация и авторизация реально работают?»
1. Запустить `pytest -v` — пройдут все **14 тестов** (`tests/test_api.py` и `tests/test_auth.py`), которые проверяют регистрацию, bcrypt в PostgreSQL, дубликаты, логин, отсутствие/подделку/истечение токена (`401`), права `user` vs `admin` (`403`) и изоляцию чужих ресурсов.
2. Показать в живом Swagger UI (`/docs`) через кнопку **Authorize** все сценарии под `student1` (`user`) и `alice` (`admin`).

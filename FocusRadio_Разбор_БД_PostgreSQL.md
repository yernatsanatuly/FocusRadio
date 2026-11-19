# 🎧 FocusRadio (Assignment 6): Максимально подробный разбор PostgreSQL, SQLAlchemy, Alembic и архитектуры

> **Зачем нужен этот файл:** чтобы абсолютно любой человек — даже если он раньше никогда не работал с PostgreSQL, SQLAlchemy, Docker или Alembic — прочитал его и полностью понял:
> 1. **Что** именно мы поменяли в проекте и **зачем**;
> 2. **Как** устроены все инструменты и как PostgreSQL связан с FastAPI;
> 3. **Что такое миграции** и как работает Alembic;
> 4. **За что отвечает каждый файл** проекта;
> 5. **Как уверенно ответить на любой вопрос преподавателя на защите.**

---

## Оглавление

1. [Главная идея простыми словами](#1-главная-идея-простыми-словами)
2. [Все инструменты «на пальцах» + примеры кода](#2-все-инструменты-на-пальцах--примеры-кода)
3. [Как мы связали PostgreSQL и FastAPI (4 шага)](#3-как-мы-связали-postgresql-и-fastapi-4-шага)
4. [Было vs Стало — сравнение на реальном коде](#4-было-vs-стало--сравнение-на-реальном-коде)
5. [Схема базы данных: все 7 таблиц, связи и защита данных](#5-схема-базы-данных-все-7-таблиц-связи-и-защита-данных)
6. [Что такое миграции и как работает Alembic](#6-что-такое-миграции-и-как-работает-alembic)
7. [Полная карта файлов проекта: за что отвечает каждый файл](#7-полная-карта-файлов-проекта-за-что-отвечает-каждый-файл)
8. [Как проходит один запрос от Swagger до PostgreSQL](#8-как-проходит-один-запрос-от-swagger-до-postgresql)
9. [Как устроены тесты и как проверить всё в Swagger UI](#9-как-устроены-тесты-и-как-проверить-всё-в-swagger-ui)
10. [5 реальных технических проблем, которые мы поймали и починили](#10-5-реальных-технических-проблем-которые-мы-поймали-и-починили)
11. [Шпаргалка к защите: 15 вопросов преподавателя и готовые ответы](#11-шпаргалка-к-защите-15-вопросов-преподавателя-и-готовые-ответы)

---

## 1. Главная идея простыми словами

### Как проект работал раньше (Assignment 5)
Раньше в `app/core/database.py` всё хранилось в обычных Python-словарях (`dict`) прямо в оперативной памяти (RAM):
- `db.users = {1: User(...), 2: User(...)}`
- `db.rooms = {1: Room(...)}`
- ID выдавались счётчиком `itertools.count(1)`.

**Аналогия:** это как писать заметки мелом на школьной доске. Пока сервер `uvicorn` работает — записи есть. Нажал `Ctrl+C` (перезапустил сервер) — **доска стёрта**, все созданные пользователи, комнаты, задачи, XP и достижения исчезли бесследно.

### Как проект работает теперь (Assignment 6)
Теперь все данные хранятся в настоящей реляционной базе данных **PostgreSQL 16** на жёстком диске.
- Перезапустил `uvicorn` (или даже компьютер) — **все данные на месте**.
- База сама проверяет уникальность, связи между таблицами (Foreign Keys), диапазоны значений (`CHECK`) и защищает данные транзакциями.
- Структура таблиц описана в версионируемых файлах миграций (**Alembic**), поэтому любой участник команды и преподаватель может поднять точно такую же базу за пару секунд.

### Самый крутой факт о нашей архитектуре
Мы **вообще не меняли** роутеры (`app/routers/*.py`) и Pydantic-схемы (`app/schemas/*.py`)!
Почему? Потому что в проекте соблюдено разделение слоёв:
- **Роутеры** не знают, где лежат данные — они просто вызывают методы сервисов (`service.create(data)`).
- **Схемы** только проверяют входящий/исходящий JSON.
- Всю работу с базой мы аккуратно заменили в слоях `core/`, `models/`, `services/` + добавили `alembic/`.

---

## 2. Все инструменты «на пальцах» + примеры кода

### 1) PostgreSQL 16 — сама база данных
**Что это:** мощная реляционная СУБД (система управления базами данных), которая хранит данные в виде связанных таблиц на диске.

**Зачем именно она:**
- Требование задания + индустриальный стандарт.
- Умеет крутые вещи, которых нет в простых БД вроде SQLite:
  - **Нативные `ENUM`** (например, статус сессии может быть только `active`, `paused`, `completed`, `ended_early`, `cancelled` — ничего левого записать нельзя);
  - **Массивы `ARRAY`** (теги комнаты хранятся прямо как `VARCHAR(20)[]`, например `{'coding', 'lofi'}`);
  - **Время с часовым поясом `TIMESTAMPTZ`** (таймеры всегда хранятся в UTC);
  - **Частичные уникальные индексы (`WHERE ...`)** — например, запретить два активных таймера одному юзеру прямо на уровне БД.

---

### 2) Docker и Docker Compose — «коробка с готовым PostgreSQL»
**Простыми словами:** чтобы не мучиться с установкой PostgreSQL вручную на Windows/macOS/Linux и не ловить «а у меня другая версия и другой пароль», мы описали готовый контейнер с PostgreSQL 16 в файле `docker-compose.yml`.

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16-alpine               # Лёгкий официальный образ PostgreSQL 16
    container_name: focusradio-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-focusradio}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-focusradio}
      POSTGRES_DB: ${POSTGRES_DB:-focusradio}
    ports:
      - "${POSTGRES_PORT:-5433}:5432"       # Наружу порт 5433, внутри контейнера 5432
    volumes:
      - focusradio_pgdata:/var/lib/postgresql/data               # Папка на диске, чтобы данные не пропадали
      - ./docker/init-test-db.sql:/docker-entrypoint-initdb.d/01-init-test-db.sql:ro  # Создаёт тестовую БД
```

**Две важные детали:**
1. **Почему порт `5433`, а не `5432`?** Порт `5432` на компьютере часто уже занят локальным Postgres (так и случилось у нас). Порт `5433` избавляет команду от конфликта портов.
2. **Зачем `docker/init-test-db.sql`?** При первом запуске контейнера он автоматически создаёт вторую БД `focusradio_test` специально для автотестов, чтобы тесты никогда не трогали твои рабочие данные в `focusradio`.

---

### 3) `.env`, `.env.example` и `pydantic-settings` — настройки и секреты
**Простыми словами:** пароль и адрес базы **нельзя** писать прямо внутри Python-кода, потому что код улетает в Git. Их хранят в переменных окружения в файле `.env`.

- `.env` — лежит только у тебя на компьютере (добавлен в `.gitignore`, в Git **не попадает**).
- `.env.example` — шаблон без секретов (лежит в Git, чтобы напарник скопировал его: `cp .env.example .env`).
- `pydantic-settings` автоматически читает `.env` в файл `app/config.py`:

```python
# app/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://focusradio:focusradio@localhost:5433/focusradio",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    test_database_url: str = Field(
        default="postgresql+psycopg://focusradio:focusradio@localhost:5433/focusradio_test",
        validation_alias=AliasChoices("TEST_DATABASE_URL", "test_database_url"),
    )
```

---

### 4) `psycopg` (psycopg3) — драйвер-переводчик
**Простыми словами:** Python сам не умеет «разговаривать» по сетевому протоколу PostgreSQL. `psycopg` — это сетевой драйвер (как адаптер питания).
В строке подключения `postgresql+psycopg://user:pass@localhost:5433/focusradio`:
- `postgresql` — какая СУБД;
- `+psycopg` — через какой драйвер подключаемся (используем современный **psycopg3** `psycopg[binary]`, идеально подходит для Python 3.12 + SQLAlchemy 2.0).

---

### 5) SQLAlchemy 2.0 (ORM) — работа с базой через Python-классы
**Простыми словами:** вместо того чтобы везде склеивать руками длинные SQL-строки вроде `"INSERT INTO users (username, email) VALUES ('alice', ...)"`, мы описываем таблицы как обычные классы Python (ORM-модели) и пишем типизированные запросы. SQLAlchemy сама переводит их в безопасный SQL (с защитой от SQL-инъекций!).

**Пример модели (таблицы):**
```python
# app/models/track.py
class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    artist: Mapped[str] = mapped_column(String(100), nullable=False)
    energy: Mapped[int] = mapped_column(Integer, nullable=False)
```

**Пример запроса в сервисе:**
```python
# Python-код в app/services/track_service.py:
stmt = select(Track).where(Track.genre == Genre.LOFI, Track.energy <= 5).order_by(Track.id.asc())
tracks = self.db.scalars(stmt).all()
```
SQLAlchemy сама превращает это в SQL:
```sql
SELECT tracks.id, tracks.title, tracks.artist, tracks.genre, tracks.mood, tracks.energy, ...
FROM tracks
WHERE tracks.genre = 'lofi' AND tracks.energy <= 5
ORDER BY tracks.id ASC;
```

#### 4 главных понятия SQLAlchemy, которые нужно знать наизусть:
1. **`Engine`** — «труба / пул соединений» к PostgreSQL. Создаётся **один раз** при запуске приложения.
2. **`Session` (сессия)** — «черновик / рабочая тетрадь» для **одного** HTTP-запроса. В ней накапливаются изменения (добавления, обновления, удаления), а потом сохраняются в БД одной транзакцией.
3. **`flush()` vs `commit()`**:
   - `db.flush()` — отправляет SQL в PostgreSQL **внутри текущей транзакции**, но ещё **НЕ сохраняет навсегда**. Зачем это нужно? Например, чтобы сразу получить сгенерированный базой `room.id` и тут же создать `RoomMember(room_id=room.id, ...)`. Если дальше случится ошибка — всё откатится!
   - `db.commit()` — **фиксирует** все изменения в базе навсегда (завершает транзакцию).
   - `db.rollback()` — **отменяет** всё, что мы сделали в текущей транзакции, если произошла ошибка.
4. **`joinedload` / `selectinload` (жадная загрузка)** — защита от **проблемы N+1 запросов**.
   - *Плохо:* загрузили 20 комнат (1 запрос), а потом в цикле для каждой комнаты отдельно запрашиваем её трек (ещё 20 запросов = 21 запрос).
   - *Хорошо:* пишем `.options(joinedload(Room.current_track), selectinload(Room.members))` — и SQLAlchemy загружает все комнаты, треки и участников всего за **2 быстрых запроса**.

---

### 6) Alembic — «Git для таблиц базы данных»
**Простыми словами:** инструмент для управления миграциями БД. Подробно разберём в [разделе 6](#6-что-такое-миграции-и-как-работает-alembic).

---

### 7) Pydantic v2 — фейсконтроль на входе API
**Простыми словами:** Pydantic проверяет JSON, который прислал клиент, **ещё до того, как мы обратимся к базе**.
- *Pydantic* проверяет формат входных данных (email похож на email, `capacity` от 2 до 50, в `RoomUpdate` передано хотя бы одно поле).
- *PostgreSQL* проверяет целостность хранимых данных (`UNIQUE`, `FOREIGN KEY`, `CHECK`, partial indexes), даже если данные попытаются записать в обход API или придут два одинаковых запроса в одну миллисекунду.
Это **двойной рубеж защиты**.

---

## 3. Как мы связали PostgreSQL и FastAPI (4 шага)

Вот вся цепочка подключения — всего 4 файла:

### Шаг 1. Прочитали адрес базы из `.env` (`app/config.py`)
```python
# .env
DATABASE_URL=postgresql+psycopg://focusradio:focusradio@localhost:5433/focusradio
```
`app/config.py` читает это в `settings.database_url`.

### Шаг 2. Создали движок и фабрику сессий (`app/core/database.py`)
```python
# app/core/database.py
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # Перед выдачей соединения проверяет, что Postgres жив
    echo=settings.sql_echo,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,     # Мы сами явно управляем db.commit()
    expire_on_commit=False,
)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()   # 1. Открываем новую сессию под текущий HTTP-запрос
    try:
        yield db          # 2. Передаём её в сервис/роутер
    except Exception:
        db.rollback()     # 3. Если где-то упала ошибка — откатываем незавершённую транзакцию
        raise
    finally:
        db.close()        # 4. В любом случае возвращаем соединение в пул
```

> **Почему нельзя создать одну глобальную `db = SessionLocal()` для всего приложения?**
> Потому что на сервер могут приходить два запроса одновременно. Если они делят одну `Session`, один запрос сделает `commit()` или `rollback()` чужих данных, и всё сломается. Правило железное: **1 HTTP-запрос = 1 отдельная `Session`**.

### Шаг 3. Прокинули `Session` в сервисы через `Depends` (`app/core/dependencies.py`)
```python
# app/core/dependencies.py
DB = Annotated[Session, Depends(get_db)]

def get_room_service(db: DB) -> RoomService:
    return RoomService(db)

Rooms = Annotated[RoomService, Depends(get_room_service)]
```
Когда приходит запрос на `POST /rooms`, FastAPI сам вызывает `get_db()` → передаёт `Session` в `RoomService(db)` → передаёт `RoomService` в роутер `create_room(data, service)` → после ответа закрывает `Session`!

### Шаг 4. Настроили идемпотентный старт (`app/main.py` + `app/core/seed.py`)
При запуске сервера срабатывает `lifespan`:
```python
# app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.seed_demo_data:
        db = SessionLocal()
        try:
            seed_demo_data(db)   # Добавит демо-треки/юзеров/комнату, ТОЛЬКО если таблицы пустые
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    yield
```
**Что значит «идемпотентный»?** Сколько раз ты ни перезапускай сервер — демо-данные запишутся **только один раз** (при первом старте на пустой базе). При 2-м, 3-м, 100-м перезапуске `seed_demo_data` увидит, что записи уже есть, и просто выйдет, ничего не дублируя.

---

## 4. Было vs Стало — сравнение на реальном коде

Ниже — 6 наглядных примеров, как конкретно изменился наш код.

### Пример 1. Хранилище (`app/core/database.py`)
**Было (в памяти):**
```python
class Database:
    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self.rooms: dict[int, Room] = {}
        self._counters = {name: count(1) for name in ("users", "rooms", ...)}

db = Database()
def get_db() -> Database:
    return db
```
**Стало (PostgreSQL + SQLAlchemy):**
```python
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

---

### Пример 2. Описание сущности (`User`)
**Было (`app/models/entities.py` — обычный dataclass):**
```python
@dataclass
class User:
    id: int
    username: str
    email: str
    xp: int = 0
    achievements: dict[str, datetime] = field(default_factory=dict)  # Словарь внутри объекта
    current_room_id: Optional[int] = None                            # Просто число без проверки FK
```
**Стало (`app/models/user.py` — реальные таблицы PostgreSQL со связями и ограничениями):**
```python
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("xp >= 0", name="xp_non_negative"),
        ...
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Реальные реляционные связи:
    tasks: Mapped[list["Task"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    sessions: Mapped[list["FocusSession"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    achievements: Mapped[list["UserAchievement"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    room_membership: Mapped[Optional["RoomMember"]] = relationship(back_populates="user", uselist=False, lazy="joined")

    @property
    def current_room_id(self) -> Optional[int]:
        return self.room_membership.room_id if self.room_membership else None
```
Обрати внимание на `@property current_room_id`! Благодаря ему весь остальной код и `UserResponse` продолжают спокойно читать `user.current_room_id`, хотя в базе это нормализованная таблица `room_members`.

---

### Пример 3. Создание записи (`TrackService.create`)
**Было:**
```python
def create(self, data: TrackCreate) -> TrackResponse:
    self._ensure_unique(data.title, data.artist)
    tid = self.db.next_id("tracks")
    track = Track(id=tid, **data.model_dump())
    self.db.tracks[tid] = track
    return TrackResponse.model_validate(track)
```
**Стало:**
```python
def create(self, data: TrackCreate) -> TrackResponse:
    self._ensure_unique(data.title, data.artist)
    track = Track(**data.model_dump())
    self.db.add(track)      # Помещаем новый объект в сессию
    self.db.commit()        # PostgreSQL выполняет INSERT и сам назначает id
    self.db.refresh(track)  # Подтягиваем id и created_at, сгенерированные базой
    return TrackResponse.model_validate(track)
```

---

### Пример 4. Поиск, фильтрация и пагинация (`TrackService.list`)
**Было (выгребали всё и фильтровали циклом в Python):**
```python
tracks = [
    t for t in self.db.tracks.values()
    if (genre is None or t.genre == genre)
    and (not search or search.lower() in f"{t.title} {t.artist}".lower())
]
tracks.sort(key=lambda t: t.id)
page = paginate(tracks, limit, offset)   # Резали Python-список [offset:offset+limit]
```
**Стало (всю работу делает PostgreSQL прямо на SQL):**
```python
stmt = select(Track)
if genre is not None:
    stmt = stmt.where(Track.genre == genre)
if search:
    pattern = f"%{search}%"
    stmt = stmt.where(or_(Track.title.ilike(pattern), Track.artist.ilike(pattern)))
stmt = stmt.order_by(Track.id.asc())

items, total = paginate_query(self.db, stmt, limit, offset)  # SQL COUNT(*) + LIMIT/OFFSET
```
Даже если в каталоге будет 1 000 000 треков, PostgreSQL вернёт только нужные 20 строк, а не будет грузить миллион объектов в память Python.

---

### Пример 5. Создание комнаты (использование `flush()` + `commit()`)
**Было:**
```python
rid = self.db.next_id("rooms")
room = Room(id=rid, ..., owner_id=owner.id, member_ids=[owner.id])
self.db.rooms[rid] = room
owner.current_room_id = rid
```
**Стало (атомарная транзакция в две таблицы `rooms` и `room_members`):**
```python
room = Room(name=data.name, owner_id=owner.id, capacity=data.capacity, tags=list(data.tags), ...)
self.db.add(room)
self.db.flush()                                      # Получаем room.id из Postgres, транзакция ещё открыта
self.db.add(RoomMember(room_id=room.id, user_id=owner.id))
self.db.commit()                                     # Обе записи фиксируются одновременно!
```
Если вставка в `room_members` вдруг упадёт, комната в `rooms` тоже **не** создастся (полная атомарность).

---

### Пример 6. Подсчёт фокусирующихся напарников в комнате (`SessionService._focusing_room_mates`)
**Было (вложенные циклы в Python):**
```python
count = 0
for member_id in self.db.rooms[room_id].member_ids:
    if member_id == user_id:
        continue
    s = find_active_session(self.db, member_id)
    if s and s.status == SessionStatus.ACTIVE:
        count += 1
```
**Стало (один быстрый SQL `JOIN` + `COUNT`):**
```python
return (
    self.db.scalar(
        select(func.count(FocusSession.id))
        .join(RoomMember, RoomMember.user_id == FocusSession.user_id)
        .where(
            RoomMember.room_id == room_id,
            FocusSession.user_id != user_id,
            FocusSession.status == SessionStatus.ACTIVE,
        )
    )
    or 0
)
```

---

## 5. Схема базы данных: все 7 таблиц, связи и защита данных

### Визуальная ER-схема
```text
                         ┌────────────────────────────┐
                         │           tracks           │
                         │ PK id                      │
                         │ title, artist (UQ lower)   │
                         │ genre, mood, energy, bpm   │
                         └──────────────┬─────────────┘
                                        │ 1 : N  (rooms.current_track_id, SET NULL)
                                        ▼
┌─────────────────────┐  ┌────────────────────────────┐  ┌──────────────────────────┐
│        users        │  │           rooms            │  │       room_members       │
│ PK id               │◄─┤ FK owner_id (RESTRICT)     │◄─┤ FK room_id (CASCADE)     │
│ UQ username         │1:N PK id                      │1:N PK id                    │
│ UQ email            │  │ name (UQ lower)            │  │ FK user_id (UQ, CASCADE) │──┐
│ xp, streaks, stats  │  │ capacity, is_private       │  │ joined_at (очередь       │  │
│ ...                 │  │ access_code, tags[]        │  │ передачи прав владельца) │  │
└──┬─────┬────────┬───┘  └──────────────┬─────────────┘  └──────────────────────────┘  │
   │     │        │                     │                                              │ 1:1
   │1:N  │1:N     │1:N                  │ 1:N (focus_sessions.room_id, SET NULL)       │ (к users)
   │     │        │                     ▼                                              │
   │     │        │      ┌────────────────────────────┐                                │
   │     │        └─────►│       focus_sessions       │◄───────────────────────────────┘
   │     │               │ PK id                      │
   │     │               │ FK user_id (CASCADE)       │
   │     │               │ FK room_id (SET NULL)      │
   │     │               │ FK task_id (SET NULL)      │◄───┐
   │     │               │ mode, status, timers, xp   │    │ 1 : N
   │     │               └──────────────┬─────────────┘    │ (tasks.id → focus_sessions.task_id)
   │     │                              │ 1:N (SET NULL)   │
   │     ▼                              ▼                  │
   │ ┌────────────────────┐  ┌────────────────────────┐    │
   │ │       tasks        │  │   user_achievements    │    │
   │ │ PK id              │  │ PK id                  │    │
   │ │ FK user_id (CASC)  │──┘ FK user_id (CASCADE)   │    │
   │ │ title, status, prio│  │ FK session_id          │    │
   │ │ est/done pomodoros │  │ code, unlocked_at      │    │
   │ └────────────────────┘  │ UQ (user_id, code)     │    │
   │                         └────────────────────────┘    │
   └───────────────────────────────────────────────────────┘
```

### Почему 7 таблиц, а не 5? (Ключевые дизайнерские решения)

#### 1. Зачем вынесли `room_members` отдельно?
Раньше у `User` было поле `current_room_id`, а у `Room` — список `member_ids: list[int]`. В реляционной БД так делать плохо по **3 причинам**:
1. **Убрали циклический Foreign Key!** Если бы `users.current_room_id` ссылался на `rooms.id`, а `rooms.owner_id` ссылался на `users.id` — получился бы цикл «курица и яйцо» (тяжело создавать и удалять таблицы в миграциях). С таблицей `room_members` цикла нет вообще!
2. **Порядок входа (`joined_at`)**: по бизнес-логике, когда владелец выходит из комнаты, права переходят к **самому давнему участнику**. В таблице `room_members` есть `joined_at` — делаем `ORDER BY joined_at ASC, id ASC LIMIT 1` и точно знаем, кто зашёл раньше всех.
3. **Гарантия «1 комната на юзера» прямо в БД**: на `room_members.user_id` стоит ограничение `UNIQUE`. База физически не даст добавить одного пользователя в две комнаты одновременно.

#### 2. Зачем вынесли `user_achievements` отдельно?
Раньше ачивки были словарём `dict[str, datetime]` внутри объекта `User`. В SQL хранить словарь неудобно — правильный реляционный подход это отдельная таблица **`user_achievements`** (`User` **1 : N** `UserAchievement`) с ограничением `UNIQUE(user_id, code)` (одну и ту же ачивку нельзя выдать дважды) и опциональной ссылкой `session_id` (знаем, какая сессия открыла ачивку).

---

### Политики удаления `ON DELETE` (что происходит при удалении записей)

В PostgreSQL у каждого Foreign Key есть правило поведения при удалении «родителя»:

- **`ON DELETE CASCADE`** («удалил родителя → удаляются дети»):
  - Удалили `User` → автоматически удаляются его `tasks`, `focus_sessions`, `user_achievements`, `room_members`.
  - Удалили `Room` → автоматически удаляются строки из `room_members`.
- **`ON DELETE SET NULL`** («удалил родителя → у детей ссылка просто обнуляется, сами дети остаются жить»):
  - Закрыли `Room` → у всех `focus_sessions` поле `room_id` становится `NULL`, но **история и статистика фокус-сессий юзера не пропадает!**
  - Удалили `Task` (не привязанную к активной сессии) → у старых `focus_sessions` поле `task_id` становится `NULL`, история сохраняется.
  - Удалили `Track` с `force=true` → у комнат `current_track_id` становится `NULL` (музыка просто останавливается).
- **`ON DELETE RESTRICT`** («запретить удаление родителя, пока на него есть ссылки»):
  - Стоит на `rooms.owner_id → users.id`. Это страховка: комната никогда не сможет остаться без владельца! Перед удалением юзера `UserService.delete()` сначала обязан передать `owner_id` следующему участнику (или закрыть пустую комнату), и только потом удалить `User`.

---

### Умные ограничения (Constraints и Индексы) прямо в PostgreSQL

```python
# 1. Один активный/приостановленный таймер на пользователя (app/models/session.py)
Index(
    "uq_focus_sessions_one_active_per_user",
    FocusSession.user_id,
    unique=True,
    postgresql_where=text("status IN ('active', 'paused')"),
)
# Позволяет иметь сколько угодно COMPLETED/CANCELLED сессий,
# но МАКСИМУМ ОДНУ в статусе active или paused!

# 2. Уникальность открытых задач без учёта регистра (app/models/task.py)
Index(
    "uq_tasks_open_user_title_lower",
    Task.user_id,
    func.lower(Task.title),
    unique=True,
    postgresql_where=text("status != 'done'"),
)

# 3. Согласованность приватности комнаты (app/models/room.py)
CheckConstraint(
    "(is_private = true AND access_code IS NOT NULL) "
    "OR (is_private = false AND access_code IS NULL)",
    name="privacy_access_code_consistency",
)
```

---

## 6. Что такое миграции и как работает Alembic

### Что такое миграция простыми словами?
Представь, что база данных — это **дом**, а ваши модели в `app/models/` — это **чертёж**.
- Если ты добавил в Python-класс `User` новое поле `avatar_url: str`, PostgreSQL об этом **сам не узнает** — колонка в таблице не появится магическим образом.
- Можно было бы снести всю базу и пересоздать с нуля (`Base.metadata.create_all()`), но тогда ты **сотрёшь всех реальных пользователей**! И `create_all()` вообще не умеет добавлять новые колонки в уже существующие таблицы.

**Миграция** — это Python-скрипт с инструкцией, как аккуратно перевести базу из состояния «версия N» в «версию N+1» (и при желании откатить обратно):
- функция `upgrade()` — что создать/добавить/изменить;
- функция `downgrade()` — как всё вернуть назад, если что-то пошло не так.

**Alembic** — это инструмент, который хранит все миграции в папке `alembic/versions/`, а в самой базе создаёт маленькую служебную таблицу `alembic_version`, где записан номер последней применённой миграции (`9458035c95c7`).

### Как устроен Alembic у нас в проекте
1. **`alembic.ini`** — главный конфиг (без пароля от БД!).
2. **`alembic/env.py`** — подключает наш `DATABASE_URL` из `app.config.settings` и нашу схему `Base.metadata` из `app.models`:
   ```python
   from app.config import settings
   from app.models import Base  # Подтягивает все 7 таблиц

   target_metadata = Base.metadata
   ```
3. **`alembic/versions/9458035c95c7_initial_schema.py`** — первая миграция, которая создаёт все 6 ENUM-типов, 7 таблиц, все `CHECK`, `FOREIGN KEY`, `UNIQUE` и partial-индексы.

### Главные команды Alembic (шпаргалка)
```bash
# 1. Применить все миграции (создать/обновить всю схему с нуля)
alembic upgrade head

# 2. Посмотреть, на какой версии сейчас база
alembic current

# 3. Откатить все миграции до пустой базы
alembic downgrade base

# 4. Проверить, что модели в Python на 100% совпадают с таблицами в PostgreSQL
alembic check

# 5. Когда в будущем добавишь новое поле в модель — сгенерировать новую миграцию:
alembic revision --autogenerate -m "add_user_avatar"
alembic upgrade head
```

---

## 7. Полная карта файлов проекта: за что отвечает каждый файл

### Инфраструктура и конфигурация
- **`docker-compose.yml`** — поднимает PostgreSQL 16 в Docker на порту `5433` с постоянным диском (`volume`).
- **`docker/init-test-db.sql`** — при первом запуске Docker автоматически создаёт вторую БД `focusradio_test` для тестов.
- **`.env.example`** — шаблон переменных окружения (лежит в Git).
- **`.env`** — твои локальные настройки подключения (в `.gitignore`, в Git не попадает).
- **`.gitignore`** — список файлов, которые Git игнорирует (`.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.DS_Store`).
- **`requirements.txt`** — список всех Python-библиотек проекта.
- **`README.md`** — документация проекта: архитектура, схема БД, запуск, миграции, тесты.

### Миграции (`alembic/`)
- **`alembic.ini`** — настройки запуска Alembic.
- **`alembic/env.py`** — связывает Alembic с `DATABASE_URL` и моделями `Base.metadata`.
- **`alembic/versions/9458035c95c7_initial_schema.py`** — миграция создания всех 7 таблиц, 6 ENUM-ов и индексов.

### Ядро приложения (`app/` и `app/core/`)
- **`app/config.py`** — читает `.env` через `pydantic-settings`, хранит `DATABASE_URL`, `TEST_DATABASE_URL`, константы таймера и XP.
- **`app/main.py`** — собирает FastAPI-приложение: CORS, обработчики ошибок, все 6 роутеров, `lifespan` с идемпотентным сидером.
- **`app/core/database.py`** — создаёт `engine`, `SessionLocal` и генератор `get_db()` для `Depends`.
- **`app/core/seed.py`** — идемпотентно заполняет пустую БД демо-данными (10 треков, 3 юзера `alice`/`bob`/`carol`, 1 стартовая комната).
- **`app/core/dependencies.py`** — Dependency Injection (`DB = Annotated[Session, Depends(get_db)]`, `ActingUserId` из заголовка `X-User-Id`, фабрики сервисов).
- **`app/core/exceptions.py`** — доменные ошибки (`400`, `403`, `404`, `409`, `422`) + обработчики ошибок SQLAlchemy (`IntegrityError` → `409`/`422`, `OperationalError` → `503`).

### Модели БД (`app/models/`)
- **`app/models/base.py`** — `Base(DeclarativeBase)`, единые правила именования ограничений (`NAMING_CONVENTION`), хелпер `pg_enum()` и `utcnow()`.
- **`app/models/enums.py`** — перечисления `Genre`, `Mood`, `SessionMode`, `SessionStatus`, `TaskStatus`, `TaskPriority`, `LeaderboardMetric`.
- **`app/models/user.py`** — ORM-модели `User` (`users`) и `UserAchievement` (`user_achievements`).
- **`app/models/room.py`** — ORM-модели `Room` (`rooms`) и `RoomMember` (`room_members`).
- **`app/models/track.py`** — ORM-модель `Track` (`tracks`).
- **`app/models/task.py`** — ORM-модель `Task` (`tasks`).
- **`app/models/session.py`** — ORM-модель `FocusSession` (`focus_sessions`).
- **`app/models/__init__.py`** — собирает и реэкспортирует `Base` и все 7 моделей (нужно для Alembic и коротких импортов).
- *(Старый `app/models/entities.py` с `@dataclass` удалён.)*

### Схемы валидации (`app/schemas/` — не менялись)
- **`common.py`**, **`users.py`**, **`rooms.py`**, **`sessions.py`**, **`tasks.py`**, **`tracks.py`**, **`leaderboard.py`** — Pydantic-схемы входящих запросов и исходящих JSON-ответов.

### Сервисы / бизнес-логика (`app/services/`)
- **`common.py`** — SQL-поиск по ID (`get_user`, `get_room`, ...), поиск активной сессии, проверка владельца, SQL-пагинация `paginate_query`.
- **`gamification.py`** — расчёт XP, формула уровней `50 * (N - 1) * N`, стрики, запись достижений в `user_achievements`, сборка лидерборда.
- **`user_service.py`** — CRUD юзеров, статистика, глобальный лидерборд, безопасное удаление аккаунта (сначала передача/закрытие комнаты → `flush` → удаление юзера с каскадом).
- **`room_service.py`** — CRUD комнат, подзапрос подсчёта мест (`has_space`), поиск по тегам (`Room.tags.contains`), живой статус участников за 1 запрос, адаптивный подбор треков, передача прав по `joined_at`.
- **`session_service.py`** — state machine таймера (`ACTIVE ↔ PAUSED → COMPLETED / ENDED_EARLY / CANCELLED`), SQL `JOIN` подсчёт напарников, атомарный `complete()`.
- **`task_service.py`** — CRUD задач, SQL-сортировка `CASE` (открытые выше выполненных, по приоритету), лимит 50 открытых задач, запрет удаления задачи из активного таймера.
- **`track_service.py`** — каталог треков с SQL-фильтрацией и защитой от удаления играющего в комнате трека (`force=true`).

### Роутеры (`app/routers/` — не менялись)
- **`users.py`**, **`rooms.py`**, **`sessions.py`**, **`tasks.py`**, **`tracks.py`**, **`leaderboard.py`** — HTTP-эндпоинты (`/users`, `/rooms`, `/sessions`, `/tasks`, `/tracks`, `/leaderboard`).

### Тесты (`tests/`)
- **`tests/test_api.py`** — 8 полных end-to-end тестов, работающих против реальной тестовой БД PostgreSQL (`focusradio_test`).

---

## 8. Как проходит один запрос от Swagger до PostgreSQL

Разберём самый интересный запрос — **завершение фокус-сессии**: `POST /sessions/5/complete` с заголовком `X-User-Id: 2`.

```text
1. Swagger UI отправляет HTTP POST /sessions/5/complete (Header: X-User-Id: 2)
        │
        ▼
2. Router (app/routers/sessions.py)
   FastAPI проверяет типы: session_id=5 (int), X-User-Id=2 (>=1), force=False (bool)
        │
        ▼
3. Dependency Injection (app/core/dependencies.py → app/core/database.py)
   Вызывается get_db() → открывается новая SQLAlchemy Session → создаётся SessionService(db)
        │
        ▼
4. Service (app/services/session_service.py → complete())
   а) SELECT из users и focus_sessions — проверяет, что юзер 2 существует и сессия 5 его.
   б) Проверяет, что таймер дошёл до конца (иначе 409 FOCUS_TIME_NOT_REACHED).
   в) Делает SELECT COUNT(*) ... JOIN room_members — считает, сколько напарников сейчас фокусится рядом.
   г) Обновляет объекты в памяти текущей транзакции (4 таблицы сразу!):
        • focus_sessions: status = 'completed', ended_at = now, xp_earned = ...
        • users: xp += ..., total_focus_minutes += ..., completed_sessions += 1, current_streak += 1
        • user_achievements: INSERT новых ачивок (например, 'first_tune_in')
        • tasks: completed_pomodoros += 1 (если сессия была привязана к задаче)
   д) Вызывает self.db.commit() → PostgreSQL сохраняет ВСЕ 4 таблицы АТОМАРНО!
      (Если на любом шаге случится сбой — get_db() вызовет rollback() и ни одна таблица не испортится.)
        │
        ▼
5. get_db() в блоке finally закрывает Session (соединение возвращается в пул).
   Pydantic собирает SessionFinishResult в JSON и отдаёт 200 OK клиенту.
```

---

## 9. Как устроены тесты и как проверить всё в Swagger UI

### Как работают автотесты (`tests/test_api.py`)
1. При старте (`setUpClass`) тесты сами прогоняют **`alembic upgrade head`** на отдельной тестовой БД `focusradio_test`.
2. Подменяют зависимость `get_db` на тестовую БД через стандартный механизм FastAPI:
   ```python
   app.dependency_overrides[get_db] = override_get_db
   ```
3. Перед каждым тестом (`setUp`) очищают все 7 таблиц и сбрасывают счётчики ID:
   ```sql
   TRUNCATE TABLE user_achievements, focus_sessions, room_members, rooms, tasks, tracks, users
   RESTART IDENTITY CASCADE;
   ```
   и заново заливают демо-данные через `seed_demo_data(db)`.

Запуск тестов:
```bash
source .venv/bin/activate
pytest -v
# или
python3 tests/test_api.py
```

### Как продемонстрировать преподавателю в Swagger UI (`/docs`)
1. Запусти БД и сервер:
   ```bash
   docker compose up -d
   source .venv/bin/activate
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```
2. Открой `http://localhost:8000/docs`.
3. **Успешные операции:**
   - `POST /users` → создай нового пользователя (получишь `id=4`, статус `201`).
   - `POST /rooms` → создай комнату с `owner_id=4` (автоматически появится запись и в `rooms`, и в `room_members`).
   - `POST /tasks` → создай задачу для `user_id=4`.
   - `POST /sessions` → запусти таймер с `user_id=4`, `task_id=1` (задача сама перейдёт в `in_progress`, а `room_id` подтянется автоматически).
4. **Ошибочные операции (проверка валидации и целостности):**
   - Повторный `POST /users` с тем же `username` → `409 USERNAME_TAKEN`.
   - `POST /users` с кривым email (`"abc"`) → `422 VALIDATION_ERROR`.
   - `POST /rooms` с несуществующим `owner_id=9999` → `404 USER_NOT_FOUND`.
   - `PATCH /users/4` с заголовком `X-User-Id: 1` → `403 NOT_RESOURCE_OWNER`.
   - Повторный `POST /sessions` для `user_id=4` → `409 SESSION_ALREADY_RUNNING`.
5. **Главный тест — персистентность (перезапуск сервера):**
   - Нажми `Ctrl+C` в терминале, чтобы **полностью остановить** `uvicorn`.
   - Запусти `uvicorn app.main:app --reload --port 8000` заново.
   - В Swagger сделай `GET /users/4`, `GET /rooms/2`, `GET /tasks/1`, `GET /sessions/1`.
   - **Все данные на месте!** А в `GET /tracks` по-прежнему ровно 10 треков (сидер не наплодил дубликатов).

---

## 10. 5 реальных технических проблем, которые мы поймали и починили

Если рассказать про эти реальные кейсы на защите — сразу видно, что команда реально понимает, как работает PostgreSQL и SQLAlchemy:

1. **Конфликт порта `5432`:** при первом `docker compose up` выяснилось, что порт `5432` на хосте уже занят. Вынесли порт в переменную `POSTGRES_PORT` со значением `5433` по умолчанию.
2. **Особенности `alembic --autogenerate` с PostgreSQL ENUM:**
   - Тип `genre_enum` используется в двух таблицах (`tracks` и `rooms`), поэтому в миграции вынесли создание всех 6 ENUM в начало с `checkfirst=True` и `create_type=False` в колонках.
   - `autogenerate` не удаляет ENUM-типы в `downgrade()` — дописали их удаление вручную и проверили цикл `upgrade → downgrade → upgrade` + `alembic check` (`No new upgrade operations detected`).
3. **Кэш SQLAlchemy при `expire_on_commit=False`:** в тесте `join_room` после добавления `RoomMember` и `commit()` повторный `select(Room)` в той же сессии возвращал старый список `room.members` (`member_count=1` вместо `2`). Починили через `.execution_options(populate_existing=True)` в `get_room(..., load_relations=True)`.
4. **Двойное удаление `RoomMember` при автозакрытии комнаты:** когда последний участник выходил, `detach_member` удалял `RoomMember`, а следом `close_room` удалял `Room`, и SQLAlchemy пытался удалить `RoomMember` повторно (`SAWarning`). Починили через `self.db.expire(room, ["members"])` после `flush()`.
5. **Устаревший `ARRAY.any()` в SQLAlchemy 2.1:** заменили `Room.tags.any(tag)` на нативный PostgreSQL-оператор `Room.tags.contains([tag])` (`@>`) — убрали warning и сделали запрос совместимым с GIN-индексами.

---

## 11. Шпаргалка к защите: 15 вопросов преподавателя и готовые ответы

### 1. «Чем ORM (SQLAlchemy) отличается от обычного SQL?»
ORM позволяет описывать таблицы как классы Python и писать запросы на Python (`select(User).where(...)`). SQLAlchemy сама генерирует безопасный SQL (с параметризацией против SQL-инъекций), маппит строки обратно в объекты, управляет пулом соединений и транзакциями.

### 2. «Почему вы использовали Alembic, а не `Base.metadata.create_all()`?»
`create_all()` только создаёт несуществующие таблицы и **не умеет** изменять уже существующие (добавлять колонки, менять типы, добавлять индексы) без потери данных. Alembic хранит историю всех изменений схемы в Git, позволяет безопасно обновлять БД (`upgrade head`) и откатывать изменения (`downgrade`).

### 3. «Какие связи между сущностями есть в вашей БД?»
- **1-to-N (один ко многим):**
  - `User` → `Task` (у юзера много задач)
  - `User` → `FocusSession` (много фокус-сессий)
  - `User` → `UserAchievement` (много достижений)
  - `User` → `Room` (как владелец `owner_id`)
  - `Room` → `RoomMember` (в комнате много участников)
  - `Room` → `FocusSession` (много сессий проходило в комнате)
  - `Task` → `FocusSession` (много сессий по одной задаче)
  - `Track` → `Room` (один трек может играть в нескольких комнатах одновременно)
  - `FocusSession` → `UserAchievement` (одна сессия может открыть несколько ачивок сразу)
- **1-to-1 (один к одному):**
  - `User` ↔ `RoomMember` (за счёт `UNIQUE(user_id)` — пользователь может быть максимум в одной комнате в один момент времени).

### 4. «Зачем нужна отдельная таблица `room_members`, если можно было просто хранить `current_room_id` в таблице `users`?»
По трём причинам:
1. Избавляемся от **циклического Foreign Key** между `users` и `rooms` (`users → rooms` и `rooms → users`).
2. Храним точное время входа `joined_at`, чтобы при выходе владельца передавать права самому давнему участнику (`ORDER BY joined_at ASC, id ASC`).
3. Ограничение `UNIQUE(user_id)` гарантирует правило «не более 1 комнаты на пользователя» прямо на уровне PostgreSQL.

### 5. «Что произойдёт, если удалить пользователя, который владеет комнатой?»
На `rooms.owner_id` стоит `ON DELETE RESTRICT`, поэтому случайно оставить комнату без владельца нельзя. В `UserService.delete()` мы в одной транзакции:
1. Выводим пользователя из `room_members`;
2. Если в комнате остались люди — передаём `owner_id` следующему по `joined_at` + `flush()`, если комната пустая — закрываем её;
3. Отменяем активную сессию (если есть);
4. Удаляем `User`, после чего `ON DELETE CASCADE` автоматически удаляет его задачи, сессии и ачивки.

### 6. «Что произойдёт с историей сессий, если закрыть комнату или удалить задачу?»
На `focus_sessions.room_id` и `focus_sessions.task_id` стоит **`ON DELETE SET NULL`**. Ссылки обнулятся, но сами сессии, статистика и заработанный XP сохранятся. При этом удалить задачу, привязанную к *активной* сессии, сервис вообще запрещает (`409 TASK_IN_ACTIVE_SESSION`).

### 7. «Как вы защищаетесь от ситуации, когда у пользователя запускаются 2 активные сессии одновременно?»
Двумя уровнями:
1. В `SessionService.start()` проверяем `find_active_session()` и отдаём понятный `409 SESSION_ALREADY_RUNNING`.
2. В PostgreSQL стоит **partial unique index** `UNIQUE (user_id) WHERE status IN ('active', 'paused')` — даже если два запроса придут в одну миллисекунду (race condition), база пропустит только один, а второй поймает обработчик `IntegrityError` и вернёт `409`.

### 8. «Что такое транзакция и где она особенно важна в вашем проекте?»
Транзакция — принцип «всё или ничего» (атомарность). Например, в `SessionService.complete()` за один раз меняются **4 таблицы**: закрывается `focus_sessions`, добавляются XP/стрик в `users`, записываются новые строки в `user_achievements` и увеличивается `completed_pomodoros` в `tasks`. Всё это фиксируется одним `self.db.commit()`. Если произойдёт ошибка — `rollback()` отменит всё целиком, не будет «сессия завершена, а XP не начислился».

### 9. «В чём разница между `db.flush()` и `db.commit()`?»
`flush()` отправляет SQL в PostgreSQL, чтобы получить сгенерированный `id` или проверить ограничения, но **не закрывает транзакцию** (ещё можно откатить). `commit()` фиксирует транзакцию в базе окончательно. Мы используем `flush()` например при создании комнаты: сначала вставляем `Room` → `flush()` → получаем `room.id` → вставляем `RoomMember(room_id=room.id, ...)` → `commit()`.

### 10. «Как вы управляете сессиями SQLAlchemy в FastAPI?»
Через генератор `get_db()` и `Depends(get_db)`. На каждый HTTP-запрос создаётся своя `Session`, при необработанной ошибке выполняется `db.rollback()`, а в блоке `finally` всегда вызывается `db.close()`, возвращая соединение в пул `engine`.

### 11. «Зачем использовать `.env`, если можно было прописать строку подключения прямо в коде?»
Чтобы не коммитить пароли и локальные порты в общий Git-репозиторий, и чтобы один и тот же код без правок работал на машине каждого разработчика, в тестах (`TEST_DATABASE_URL`) и на сервере. В Git лежит только шаблон `.env.example`, а `.env` добавлен в `.gitignore`.

### 12. «Что такое проблема N+1 запросов и как вы её решили?»
Если загрузить список комнат (1 запрос), а потом в цикле для каждой комнаты обращаться к `room.current_track` или `room.members` — SQLAlchemy сделает по отдельному SQL-запросу на каждую комнату (N+1). Мы решили это с помощью `joinedload(Room.current_track)` и `selectinload(Room.members)`, а в `RoomService.activity()` подгружаем активные сессии всех участников одним запросом `WHERE user_id IN (...)`.

### 13. «Зачем нужны `CHECK` и `UNIQUE` в PostgreSQL, если у вас уже есть валидация в Pydantic?»
Pydantic проверяет только формат одного входящего HTTP-запроса, но он **не знает**, что уже лежит в базе (уникальность, внешние ключи, параллельные запросы), и не защищает от ошибок в скриптах или ручных SQL-запросов. Ограничения в PostgreSQL — последняя железобетонная гарантия целостности данных.

### 14. «Что случится, если PostgreSQL вернёт `IntegrityError` или база выключится?»
В `app/core/exceptions.py` зарегистрированы обработчики:
- `IntegrityError` по коду SQLSTATE (`23505` / `23503` / `23514`) возвращает чистый JSON `409 Conflict` или `422 Unprocessable Content`, а не «голый» `500 Internal Server Error`.
- `OperationalError` (если БД недоступна) возвращает `503 Service Unavailable` с кодом `DATABASE_UNAVAILABLE`.

### 15. «Почему в ORM-моделях для `datetime` стоит `DateTime(timezone=True)` и для `Enum` — `values_callable`?»
- В коде таймеров используется `datetime.now(timezone.utc)` (timezone-aware). Если в Postgres хранить `TIMESTAMP WITHOUT TIME ZONE`, вычитание `utcnow() - session.started_at` упадёт с `TypeError`. Поэтому везде `DateTime(timezone=True)` (`TIMESTAMPTZ`).
- По умолчанию SQLAlchemy сохраняет в Postgres **имена** констант Enum (`"LOFI"`, `"ACTIVE"`), а наш API и Pydantic работают со **значениями** (`"lofi"`, `"active"`). Параметр `values_callable=lambda obj: [item.value for item in obj]` решает эту нестыковку.

# 🎧 FocusRadio — Shared Rooms for Work and Study (Coworking Space)

**FocusRadio** is an interactive REST API for a virtual coworking space built with **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0**, **Alembic**, and **Pydantic**. It helps students, developers, and freelancers stay focused, work together in shared rooms, manage tasks, and track progress through gamification and adaptive audio.

---

## 🏛 Project Architecture

The codebase follows a clean layered architecture separating HTTP routing, request/response validation, business logic, database models, and migrations:

```text
focusradio/
├── docker-compose.yml            # PostgreSQL 16 service (+ automatic test DB creation)
├── docker/
│   └── init-test-db.sql          # Creates the focusradio_test database on container init
├── .env.example                  # Template for environment variables
├── alembic.ini                   # Alembic configuration (URL loaded dynamically from env)
├── alembic/
│   ├── env.py                    # Binds Alembic to app.config.settings & SQLAlchemy Base
│   └── versions/                 # Versioned database migration scripts
├── app/
│   ├── config.py                 # Pydantic BaseSettings (.env, DATABASE_URL, timer & XP rules)
│   ├── main.py                   # FastAPI app, CORS, exception handlers, idempotent demo seed
│   ├── core/
│   │   ├── database.py           # SQLAlchemy Engine, SessionLocal, get_db() dependency
│   │   ├── seed.py               # Idempotent initial demo tracks, users, and starter room
│   │   ├── dependencies.py       # FastAPI Depends: SQLAlchemy Session, service DI, X-User-Id
│   │   └── exceptions.py         # Domain exceptions (400/403/404/409/422) + SQLAlchemy handlers
│   ├── models/                   # SQLAlchemy 2.0 ORM models & PostgreSQL constraints
│   │   ├── __init__.py           # Re-exports Base and all ORM models for Alembic
│   │   ├── base.py               # DeclarativeBase, naming conventions, pg_enum, utcnow()
│   │   ├── enums.py              # Genre, Mood, SessionMode, SessionStatus, TaskStatus, etc.
│   │   ├── user.py               # User, UserAchievement
│   │   ├── room.py               # Room, RoomMember
│   │   ├── track.py              # Track
│   │   ├── task.py               # Task
│   │   └── session.py            # FocusSession
│   ├── schemas/                  # Pydantic v2 validation & response models
│   ├── services/                 # Business logic & atomic SQLAlchemy transactions
│   │   ├── common.py             # Shared SQL lookup helpers, ownership checks, SQL pagination
│   │   ├── user_service.py       # User CRUD, stats, leaderboards, cascading account deletion
│   │   ├── room_service.py       # Room lifecycle, join order, ownership transfer, adaptive audio
│   │   ├── session_service.py    # Focus timer state machine & coworking XP bonuses
│   │   ├── task_service.py       # Task CRUD, open-task limit, session linking & rewards
│   │   ├── track_service.py      # Audio catalog filtering and in-use delete protection
│   │   └── gamification.py       # XP breakdown, quadratic levels, streaks, achievements
│   └── routers/                  # FastAPI HTTP route handlers (/users, /rooms, /sessions, ...)
├── tests/
│   └── test_api.py               # End-to-end tests against PostgreSQL (focusradio_test)
├── requirements.txt
└── README.md
```

---

## 🗄 Database Schema & Relationships

PostgreSQL stores **7 normalized tables** managed exclusively through Alembic migrations:

| Table | Primary Key | Foreign Keys & Relationships | Key Constraints |
|---|---|---|---|
| `users` | `id` | 1-to-N `tasks`, `focus_sessions`, `user_achievements`, `rooms` (owner); 1-to-1 `room_members` | `UNIQUE(username)`, `UNIQUE(email)`, non-negative XP/counters |
| `tracks` | `id` | 1-to-N `rooms` (`current_track_id`) | `UNIQUE(lower(title), lower(artist))`, `CHECK` on `energy` (1–10), `duration_seconds` (30–7200), `bpm` (40–220) |
| `rooms` | `id` | `owner_id → users.id` (`RESTRICT`), `current_track_id → tracks.id` (`SET NULL`); 1-to-N `room_members`, `focus_sessions` | `UNIQUE(lower(name))`, `CHECK` on `capacity` (2–50) and private/access_code consistency, `VARCHAR(20)[]` tags |
| `room_members` | `id` | `room_id → rooms.id` (`CASCADE`), `user_id → users.id` (`CASCADE`) | `UNIQUE(user_id)` (one room per user at a time), `joined_at` preserves ownership-transfer order |
| `tasks` | `id` | `user_id → users.id` (`CASCADE`); 1-to-N `focus_sessions` | Partial unique index `UNIQUE(user_id, lower(title)) WHERE status != 'done'`, `CHECK` on `estimated_pomodoros` (1–20) |
| `focus_sessions` | `id` | `user_id → users.id` (`CASCADE`), `room_id → rooms.id` (`SET NULL`), `task_id → tasks.id` (`SET NULL`) | Partial unique index `UNIQUE(user_id) WHERE status IN ('active', 'paused')`, `CHECK` on timer & pause bounds |
| `user_achievements` | `id` | `user_id → users.id` (`CASCADE`), `session_id → focus_sessions.id` (`SET NULL`) | `UNIQUE(user_id, code)` |

---

## 🚀 3 Key Business Workflows

### 1. Virtual Coworking and Adaptive Audio
- Users create public or private rooms (`POST /rooms`) with a capacity of 2–50 seats.
- Users join rooms via `POST /rooms/{id}/members`. Join order is persisted in `room_members.joined_at`, so when the owner leaves, ownership transfers deterministically to the longest-standing member; when the last member leaves, the room closes automatically.
- **Live status synchronization**: `GET /rooms/{id}/members` reports real-time focus status for all room members.
- **Adaptive audio**: `GET /rooms/{id}/recommended-tracks` switches between `focus` (≥50% focusing → calm, low-energy tracks) and `break` (energetic tracks).

### 2. Focus Sessions and Task Management
- Users create tasks (`POST /tasks`) and start focus sessions (`POST /sessions`) linked to a task and current room.
- **State machine**: `ACTIVE` ↔ `PAUSED` → `COMPLETED` / `ENDED_EARLY` / `CANCELLED`.
- **Integrity rules**: max 1 running session per user (`409 Conflict` + DB partial unique index), max 3 pauses (`422`), early finish requires `force=true`, completed sessions credit a pomodoro to the linked task atomically.

### 3. Gamification, Streaks, and Leaderboards
- **XP rewards**: 2 XP/min of full focus + 20 XP completion bonus + 10 XP no-pause bonus + 5 XP per focusing teammate + daily streak bonus.
- **Levels**: $XP(N) = 50 \times (N - 1) \times N$, from *Listener* (1) to *Zen Legend* (20).
- **Persistent achievements & leaderboards**: unlocked achievements are stored in `user_achievements`; global and room leaderboards support `xp`, `focus_minutes`, `streak`, and `sessions`.

---

## 🛠 Setup, Migrations, and Running

### 1. Create virtual environment & install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables
Copy `.env.example` to `.env` (adjust credentials/port if using a local PostgreSQL installation instead of Docker):
```bash
cp .env.example .env
```

### 3. Start PostgreSQL
**Option A — Docker Compose (recommended for teams):**
```bash
docker compose up -d
```
This starts PostgreSQL 16 on port `5433` (configurable via `POSTGRES_PORT`) and creates both `focusradio` and `focusradio_test` databases automatically.

**Option B — Local PostgreSQL:**
Create databases `focusradio` and `focusradio_test`, then set `DATABASE_URL` and `TEST_DATABASE_URL` in `.env`.

### 4. Apply Alembic database migrations
```bash
alembic upgrade head
```
Useful Alembic commands:
```bash
alembic current                                  # Show current revision
alembic revision --autogenerate -m "description" # Generate a new migration
alembic downgrade base                           # Roll back all migrations
```

### 5. Start the FastAPI backend
```bash
uvicorn app.main:app --reload --port 8000
```
On first startup (when `FOCUSRADIO_SEED=1`), the app idempotently seeds 10 demo tracks, 3 demo users (`alice`, `bob`, `carol`), and 1 starter room.

### 6. Interactive API Documentation (Swagger UI)
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

Endpoints that modify user-owned resources require the `X-User-Id` request header.

### 7. Run automated tests
Make sure PostgreSQL is running (the test suite applies Alembic migrations to `TEST_DATABASE_URL` automatically):
```bash
pytest -v
# or
python3 tests/test_api.py
```

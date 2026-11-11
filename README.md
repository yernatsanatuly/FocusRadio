# 🎧 FocusRadio — Shared Rooms for Work and Study (Coworking Space)

**FocusRadio** is an interactive REST API for a virtual coworking space. It helps students, developers, and freelancers stay focused, work together in real time, and increase productivity through a gamified environment with adaptive audio and structured sessions.

---

## 🏛 Project Architecture

The project is strictly divided into layers in accordance with the principles of clean architecture:

```text
focusradio/
├── app/
│   ├── config.py                 # Application settings (environment variables, timer, XP multipliers)
│   ├── main.py                   # FastAPI entry point, CORS, middleware, Swagger
│   ├── core/
│   │   ├── database.py           # In-memory data storage (dict + ID counters) + seed data
│   │   ├── dependencies.py       # FastAPI Depends: service injection, pagination, X-User-Id
│   │   └── exceptions.py         # Domain exceptions (400, 403, 404, 409, 422) and handlers
│   ├── models/
│   │   ├── enums.py              # Enumerations: Genre, Mood, SessionMode, SessionStatus, etc.
│   │   └── entities.py           # Internal entity structures (dataclasses)
│   ├── schemas/                  # Pydantic models for request/response validation
│   │   ├── common.py             # Page[T], ErrorResponse
│   │   ├── users.py              # UserCreate, UserUpdate, UserResponse, UserStats
│   │   ├── rooms.py              # RoomCreate, RoomUpdate, RoomActivity, RoomResponse
│   │   ├── sessions.py           # SessionCreate, SessionResponse, SessionFinishResult
│   │   ├── tasks.py              # TaskCreate, TaskUpdate, TaskResponse
│   │   ├── tracks.py             # TrackCreate, TrackUpdate, TrackResponse
│   │   └── leaderboard.py        # Leaderboard, LeaderboardEntry
│   ├── services/                 # Business logic layer (pure Python, outside the routers)
│   │   ├── common.py             # Shared helpers for lookup and ownership checks
│   │   ├── user_service.py       # User management and cascading data deletion
│   │   ├── room_service.py       # Room lifecycle, owner changes, adaptive audio
│   │   ├── session_service.py    # Focus timer state machine and time calculations
│   │   ├── task_service.py       # Task logic, limits, session binding, automatic rewards
│   │   ├── track_service.py      # Audio catalog with filters by mood and energy
│   │   └── gamification.py       # XP calculations, level formula, streaks, achievement system
│   └── routers/                  # FastAPI controllers (HTTP method handlers)
│       ├── users.py              # /users/*
│       ├── rooms.py              # /rooms/*
│       ├── sessions.py           # /sessions/*
│       ├── tasks.py              # /tasks/*
│       ├── tracks.py             # /tracks/*
│       └── leaderboard.py        # /leaderboard
├── tests/
│   └── test_api.py               # End-to-end tests for all workflows and validation
├── requirements.txt              # Project dependencies
└── README.md
```

---

## 🚀 3 Key Business Workflows

### 1. Virtual Coworking and Adaptive Audio
- A user creates a public or private room with a participant limit (for example, from 2 to 50 seats).
- Users join the room through `POST /rooms/{id}/members`. When the last participant leaves, the room is automatically deleted.
- **Live status synchronization**: `GET /rooms/{id}/members` reflects the current activity of all participants in real time.
- **Adaptive audio**: the algorithm analyzes the ratio of users working versus taking a break:
  - If at least 50% of participants are focused → the room enters **`focus`** mode and recommends calm low-energy tracks (Lo-Fi, Ambient, Nature).
  - If most participants are resting → the room enters **`break`** mode and recommends more energetic tracks (Synthwave, Chillhop) to help them recharge.

### 2. Focus Sessions and Task Management
- A user creates a task (ToDo) with a pomodoro estimate and starts a session using `POST /sessions`.
- Supported focus session modes include active work and breaks.
- **State machine**: `ACTIVE` ↔ `PAUSED` → `COMPLETED` / `ENDED_EARLY` / `CANCELLED`.
- **Business rules**:
  - A user cannot have two active sessions at the same time; the API returns `409 Conflict`.
  - The pause limit is no more than 3 pauses per session.
  - Ending a session early without confirmation triggers `409 Conflict`, with remaining time considered.
  - When a session ends honestly, the completed pomodoro is automatically credited to the linked task.

### 3. Gamification, Streaks, and Leaderboards
- **XP calculation**:
  - Base reward: 2 XP per minute of honest focus.
  - Bonus for successful session completion: +20 XP.
  - Bonus for a session without any pauses (“Laser Focus”): +10 XP.
  - Coworking bonus: +5 XP for each teammate actively working in the room.
  - Daily streak bonus: +5 XP for each consecutive day of focus.
- **Dynamic levels**: level `N` is calculated using the quadratic formula:
  $$XP(N) = 50 \times (N - 1) \times N$$
  Titles are assigned from *Listener* (1) to *Zen Legend* (20).
- **Automatic achievements**: achievements are checked automatically when sessions and tasks are completed (for example: `first_tune_in`, `laser_focus`, and others).
- **Leaderboards**: global and in-room rankings across 4 metrics: `xp`, `focus_minutes`, `streak`, and `sessions`.

---

## 🛠 Running and Testing

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the server
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Interactive API Documentation (Swagger UI)
Open the following in your browser:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

For endpoints that require authorization (such as profile updates, pausing a session, or changing music), send the required header values described in the API.

### 4. Run automated tests
```bash
python3 tests/test_api.py
```

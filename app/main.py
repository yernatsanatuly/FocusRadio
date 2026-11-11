"""FocusRadio FastAPI application."""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.database import db, seed_demo_data
from app.core.exceptions import register_exception_handlers
from app.routers import leaderboard, rooms, sessions, tasks, tracks, users


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.seed_demo_data and not db.users:
        seed_demo_data(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="""
# 🎧 FocusRadio — Совместные комнаты для работы и учёбы (Coworking Space)

Интерактивный REST API виртуального коворкинга для совместной продуктивной работы.

### Ключевые возможности:
- **Coworking Rooms**: публичные и приватные комнаты с контролем вместимости, владельцем и общим аудио-стримом.
- **Focus Sessions (Pomodoro & Custom)**: таймеры с машиной состояний (active/paused/completed/ended_early/cancelled), защитой от перерывов и синхронизацией со статусом в комнате.
- **Adaptive Audio**: рекомендация треков под текущую фазу комнаты (фокус vs отдых) с учетом жанров и уровня энергии.
- **Personal Tasks**: трекинг задач с прогрессом по помидоркам и связкой с активными сессиями.
- **Gamification**: опыт (XP), система уровней, стрики дней, автоматические ачивки и глобальные/комнатные лидерборды.

Документация интерактивна: используйте кнопку **Authorize** или заголовок `X-User-Id` для действий от имени пользователя.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
register_exception_handlers(app)

# Include routers
app.include_router(users.router)
app.include_router(rooms.router)
app.include_router(sessions.router)
app.include_router(tasks.router)
app.include_router(tracks.router)
app.include_router(leaderboard.router)


@app.get("/", tags=["Health"])
def root():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "status": "online",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
    }

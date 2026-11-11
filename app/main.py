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
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
 )

register_exception_handlers(app)

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

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from app.models.enums import (
    Genre,
    Mood,
    SessionMode,
    SessionStatus,
    TaskPriority,
    TaskStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class User:
    id: int
    username: str
    display_name: str
    email: str
    bio: Optional[str] = None
    xp: int = 0
    total_focus_minutes: int = 0
    completed_sessions: int = 0
    completed_tasks: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    last_focus_date: Optional[date] = None
    achievements: dict[str, datetime] = field(default_factory=dict)  # code -> unlocked_at
    current_room_id: Optional[int] = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Room:
    id: int
    name: str
    owner_id: int
    capacity: int
    description: Optional[str] = None
    is_private: bool = False
    access_code: Optional[str] = None
    preferred_genre: Optional[Genre] = None
    tags: list[str] = field(default_factory=list)
    member_ids: list[int] = field(default_factory=list)  # ordered by join time
    current_track_id: Optional[int] = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Track:
    id: int
    title: str
    artist: str
    genre: Genre
    mood: Mood
    energy: int            # 1 (very calm) .. 10 (very energetic)
    duration_seconds: int
    bpm: Optional[int] = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Task:
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    estimated_pomodoros: int = 1
    completed_pomodoros: int = 0
    xp_awarded: bool = False
    created_at: datetime = field(default_factory=utcnow)
    completed_at: Optional[datetime] = None


@dataclass
class FocusSession:
    id: int
    user_id: int
    mode: SessionMode
    focus_minutes: int
    break_minutes: int
    room_id: Optional[int] = None
    task_id: Optional[int] = None
    notes: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    started_at: datetime = field(default_factory=utcnow)
    paused_at: Optional[datetime] = None
    total_paused_seconds: float = 0.0
    pause_count: int = 0
    ended_at: Optional[datetime] = None
    focused_seconds: int = 0
    xp_earned: int = 0
    unlocked_achievements: list[str] = field(default_factory=list)

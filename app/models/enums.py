
from enum import Enum


class SessionMode(str, Enum):

    POMODORO = "pomodoro"
    SHORT = "short"
    DEEP_WORK = "deep_work"
    CUSTOM = "custom"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ENDED_EARLY = "ended_early"
    CANCELLED = "cancelled"


class Genre(str, Enum):
    LOFI = "lofi"
    AMBIENT = "ambient"
    NATURE = "nature"
    CLASSICAL = "classical"
    WHITE_NOISE = "white_noise"
    SYNTHWAVE = "synthwave"


class Mood(str, Enum):
    FOCUS = "focus"
    BREAK = "break"
    ENERGIZE = "energize"
    CALM = "calm"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LeaderboardMetric(str, Enum):
    XP = "xp"
    FOCUS_MINUTES = "focus_minutes"
    STREAK = "streak"
    SESSIONS = "sessions"


ACTIVE_SESSION_STATUSES = {SessionStatus.ACTIVE, SessionStatus.PAUSED}
FINISHED_SESSION_STATUSES = {
    SessionStatus.COMPLETED,
    SessionStatus.ENDED_EARLY,
    SessionStatus.CANCELLED,
}

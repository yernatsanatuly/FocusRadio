"""Gamification rules: XP, levels, streaks, achievements and leaderboards."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Iterable, Optional

from app.config import settings
from app.models.entities import FocusSession, User, utcnow
from app.models.enums import LeaderboardMetric, SessionStatus
from app.schemas.leaderboard import LeaderboardEntry
from app.schemas.users import AchievementResponse, LevelInfo

# --------------------------------------------------------------------------- #
# Levels
# --------------------------------------------------------------------------- #
LEVEL_TITLES = [
    (1, "Listener"),
    (3, "Apprentice"),
    (5, "Focused Mind"),
    (8, "Deep Worker"),
    (12, "Flow Master"),
    (20, "Zen Legend"),
]


def xp_threshold(level: int) -> int:
    """Total XP needed to reach `level` (L1=0, L2=100, L3=300, L4=600, ...)."""
    return 50 * (level - 1) * level


def level_for_xp(xp: int) -> int:
    level = 1
    while xp >= xp_threshold(level + 1):
        level += 1
    return level


def level_title(level: int) -> str:
    title = LEVEL_TITLES[0][1]
    for min_level, name in LEVEL_TITLES:
        if level >= min_level:
            title = name
    return title


def level_info(xp: int) -> LevelInfo:
    level = level_for_xp(xp)
    current, nxt = xp_threshold(level), xp_threshold(level + 1)
    return LevelInfo(
        level=level,
        title=level_title(level),
        xp=xp,
        xp_current_level=current,
        xp_next_level=nxt,
        progress_percent=round((xp - current) / (nxt - current) * 100, 1),
    )


# --------------------------------------------------------------------------- #
# Achievements
# --------------------------------------------------------------------------- #
@dataclass
class AchievementContext:
    session: Optional[FocusSession] = None
    focusing_room_mates: int = 0


@dataclass(frozen=True)
class Achievement:
    code: str
    title: str
    description: str
    check: Callable[[User, AchievementContext], bool]


def _completed(ctx: AchievementContext) -> bool:
    return ctx.session is not None and ctx.session.status == SessionStatus.COMPLETED


ACHIEVEMENTS: dict[str, Achievement] = {a.code: a for a in [
    Achievement("first_tune_in", "First Tune-In", "Complete your first focus session",
                lambda u, c: u.completed_sessions >= 1),
    Achievement("in_the_groove", "In the Groove", "Complete 5 focus sessions",
                lambda u, c: u.completed_sessions >= 5),
    Achievement("focus_machine", "Focus Machine", "Complete 20 focus sessions",
                lambda u, c: u.completed_sessions >= 20),
    Achievement("hour_club", "Hour Club", "Accumulate 60 minutes of focus",
                lambda u, c: u.total_focus_minutes >= 60),
    Achievement("deep_diver", "Deep Diver", "Complete a single session of 50+ minutes",
                lambda u, c: _completed(c) and c.session.focus_minutes >= 50),
    Achievement("laser_focus", "Laser Focus", "Complete a 25+ minute session without pauses",
                lambda u, c: _completed(c) and c.session.focus_minutes >= 25
                and c.session.pause_count == 0),
    Achievement("better_together", "Better Together",
                "Complete a session while 2+ room mates are focusing too",
                lambda u, c: _completed(c) and c.focusing_room_mates >= 2),
    Achievement("on_fire", "On Fire", "Reach a 3-day focus streak",
                lambda u, c: u.current_streak >= 3),
    Achievement("unstoppable", "Unstoppable", "Reach a 7-day focus streak",
                lambda u, c: u.current_streak >= 7),
    Achievement("task_master", "Task Master", "Complete 5 tasks",
                lambda u, c: u.completed_tasks >= 5),
    Achievement("level_5", "Focused Mind", "Reach level 5",
                lambda u, c: level_for_xp(u.xp) >= 5),
]}


def unlock_achievements(user: User, ctx: AchievementContext) -> list[AchievementResponse]:
    """Unlock every achievement whose condition is now satisfied."""
    unlocked: list[AchievementResponse] = []
    for ach in ACHIEVEMENTS.values():
        if ach.code in user.achievements:
            continue
        if ach.check(user, ctx):
            now = utcnow()
            user.achievements[ach.code] = now
            unlocked.append(AchievementResponse(code=ach.code, title=ach.title,
                                                description=ach.description,
                                                unlocked=True, unlocked_at=now))
    return unlocked


def list_achievements(user: User) -> list[AchievementResponse]:
    return [
        AchievementResponse(
            code=a.code, title=a.title, description=a.description,
            unlocked=a.code in user.achievements,
            unlocked_at=user.achievements.get(a.code),
        )
        for a in ACHIEVEMENTS.values()
    ]


# --------------------------------------------------------------------------- #
# Streaks & rewards
# --------------------------------------------------------------------------- #
def update_streak(user: User, today: Optional[date] = None) -> None:
    today = today or utcnow().date()
    if user.last_focus_date == today:
        return
    if user.last_focus_date == today - timedelta(days=1):
        user.current_streak += 1
    else:
        user.current_streak = 1
    user.last_focus_date = today
    user.longest_streak = max(user.longest_streak, user.current_streak)


def reward_session(user: User, session: FocusSession,
                   focusing_room_mates: int) -> tuple[dict[str, int], list[AchievementResponse]]:
    """Apply XP/streak/achievement updates for a finished (completed/ended early) session.

    Returns the XP breakdown and newly unlocked achievements.
    """
    minutes = int(session.focused_seconds / settings.seconds_per_minute)  # timer minutes
    breakdown: dict[str, int] = {}

    if session.status == SessionStatus.COMPLETED:
        minutes = session.focus_minutes  # full planned time
        breakdown["focus_minutes"] = minutes * settings.xp_per_focus_minute
        breakdown["completion_bonus"] = settings.xp_full_completion_bonus
        if session.pause_count == 0:
            breakdown["no_pause_bonus"] = settings.xp_no_pause_bonus
        if focusing_room_mates > 0:
            breakdown["coworking_bonus"] = settings.xp_room_bonus * min(focusing_room_mates, 5)
        user.completed_sessions += 1
        update_streak(user)
        streak_days = min(user.current_streak, settings.xp_streak_bonus_cap_days)
        if streak_days > 1:
            breakdown["streak_bonus"] = streak_days * settings.xp_streak_bonus_per_day
    else:  # ENDED_EARLY: partial reward, no bonuses, streak not extended
        breakdown["partial_focus_minutes"] = minutes * settings.xp_per_early_minute

    user.total_focus_minutes += minutes
    total = sum(breakdown.values())
    user.xp += total
    session.xp_earned = total

    new = unlock_achievements(user, AchievementContext(session, focusing_room_mates))
    session.unlocked_achievements = [a.code for a in new]
    return breakdown, new


def reward_task_completion(user: User) -> list[AchievementResponse]:
    user.completed_tasks += 1
    user.xp += settings.xp_task_completed
    return unlock_achievements(user, AchievementContext())


# --------------------------------------------------------------------------- #
# Leaderboards
# --------------------------------------------------------------------------- #
_METRIC_GETTERS: dict[LeaderboardMetric, Callable[[User], int]] = {
    LeaderboardMetric.XP: lambda u: u.xp,
    LeaderboardMetric.FOCUS_MINUTES: lambda u: u.total_focus_minutes,
    LeaderboardMetric.STREAK: lambda u: u.current_streak,
    LeaderboardMetric.SESSIONS: lambda u: u.completed_sessions,
}


def build_leaderboard(users: Iterable[User], metric: LeaderboardMetric,
                      limit: int) -> list[LeaderboardEntry]:
    getter = _METRIC_GETTERS[metric]
    ranked = sorted(users, key=lambda u: (-getter(u), -u.xp, u.id))[:limit]
    entries: list[LeaderboardEntry] = []
    prev_value, prev_rank = None, 0
    for idx, user in enumerate(ranked, start=1):
        value = getter(user)
        rank = prev_rank if value == prev_value else idx   # ties share a rank
        entries.append(LeaderboardEntry(rank=rank, user_id=user.id, username=user.username,
                                        display_name=user.display_name,
                                        level=level_for_xp(user.xp), value=value))
        prev_value, prev_rank = value, rank
    return entries

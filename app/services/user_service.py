"""User management, statistics and achievements."""
from __future__ import annotations

from collections import Counter
from typing import Literal, Optional

from app.core.database import Database
from app.core.exceptions import ConflictError
from app.models.entities import User
from app.models.enums import FINISHED_SESSION_STATUSES, LeaderboardMetric, SessionStatus, TaskStatus
from app.schemas.leaderboard import Leaderboard
from app.schemas.users import AchievementResponse, UserCreate, UserResponse, UserStats, UserUpdate
from app.services import gamification
from app.services.common import (
    ensure_actor_exists,
    ensure_same_user,
    find_active_session,
    get_user,
    paginate,
)
from app.services.room_service import RoomService
from app.services.session_service import SessionService

UserSort = Literal["id", "username", "xp", "focus_minutes", "streak"]


def to_response(user: User) -> UserResponse:
    level = gamification.level_for_xp(user.xp)
    return UserResponse(
        id=user.id, username=user.username, display_name=user.display_name, email=user.email,
        bio=user.bio, xp=user.xp, level=level, level_title=gamification.level_title(level),
        current_streak=user.current_streak, longest_streak=user.longest_streak,
        total_focus_minutes=user.total_focus_minutes, completed_sessions=user.completed_sessions,
        completed_tasks=user.completed_tasks, current_room_id=user.current_room_id,
        created_at=user.created_at,
    )


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---------------------------------------------------------------- queries
    def list(self, *, search: Optional[str], sort_by: UserSort, limit: int, offset: int) -> dict:
        users = [u for u in self.db.users.values()
                 if not search or search.lower() in f"{u.username} {u.display_name}".lower()]
        keys = {
            "id": lambda u: u.id,
            "username": lambda u: u.username,
            "xp": lambda u: -u.xp,
            "focus_minutes": lambda u: -u.total_focus_minutes,
            "streak": lambda u: -u.current_streak,
        }
        users.sort(key=keys[sort_by])
        page = paginate(users, limit, offset)
        page["items"] = [to_response(u) for u in page["items"]]
        return page

    def get(self, user_id: int) -> UserResponse:
        return to_response(get_user(self.db, user_id))

    def achievements(self, user_id: int, unlocked_only: bool) -> list[AchievementResponse]:
        items = gamification.list_achievements(get_user(self.db, user_id))
        return [a for a in items if a.unlocked] if unlocked_only else items

    def stats(self, user_id: int) -> UserStats:
        user = get_user(self.db, user_id)
        sessions = [s for s in self.db.sessions.values() if s.user_id == user.id]
        by_status = Counter(s.status.value for s in sessions)
        finished = [s for s in sessions if s.status in FINISHED_SESSION_STATUSES]
        completed = by_status.get(SessionStatus.COMPLETED.value, 0)
        rewarded = [s for s in sessions
                    if s.status in (SessionStatus.COMPLETED, SessionStatus.ENDED_EARLY)]
        modes = Counter(s.mode.value for s in rewarded)
        tasks = [t for t in self.db.tasks.values() if t.user_id == user.id]
        active = find_active_session(self.db, user.id)
        return UserStats(
            user_id=user.id,
            level=gamification.level_info(user.xp),
            current_streak=user.current_streak,
            longest_streak=user.longest_streak,
            total_focus_minutes=user.total_focus_minutes,
            completed_sessions=user.completed_sessions,
            sessions_by_status={st.value: by_status.get(st.value, 0) for st in SessionStatus},
            completion_rate_percent=round(completed / len(finished) * 100, 1) if finished else 0.0,
            average_session_minutes=round(user.total_focus_minutes / len(rewarded), 1)
            if rewarded else 0.0,
            favorite_mode=modes.most_common(1)[0][0] if modes else None,
            tasks_open=sum(t.status != TaskStatus.DONE for t in tasks),
            tasks_done=sum(t.status == TaskStatus.DONE for t in tasks),
            achievements_unlocked=len(user.achievements),
            achievements_total=len(gamification.ACHIEVEMENTS),
            active_session_id=active.id if active else None,
        )

    def leaderboard(self, metric: LeaderboardMetric, limit: int) -> Leaderboard:
        return Leaderboard(metric=metric, scope="global",
                           entries=gamification.build_leaderboard(self.db.users.values(),
                                                                  metric, limit))

    # --------------------------------------------------------------- commands
    def create(self, data: UserCreate) -> UserResponse:
        self._ensure_unique(username=data.username, email=data.email)
        uid = self.db.next_id("users")
        user = User(id=uid, **data.model_dump())
        self.db.users[uid] = user
        return to_response(user)

    def update(self, user_id: int, acting_user_id: int, data: UserUpdate) -> UserResponse:
        ensure_actor_exists(self.db, acting_user_id)
        user = get_user(self.db, user_id)
        ensure_same_user(acting_user_id, user.id, "profile")
        changes = data.model_dump(exclude_unset=True)
        if changes.get("display_name", "x") is None:
            changes.pop("display_name")
        if "email" in changes:
            if changes["email"] is None:
                changes.pop("email")
            elif changes["email"] != user.email:
                self._ensure_unique(email=changes["email"])
        for key, value in changes.items():
            setattr(user, key, value)
        return to_response(user)

    def delete(self, user_id: int, acting_user_id: int) -> None:
        """Delete a user and keep every related resource consistent."""
        ensure_actor_exists(self.db, acting_user_id)
        user = get_user(self.db, user_id)
        ensure_same_user(acting_user_id, user.id, "account")

        # 1. leave the current room (transfers ownership / closes empty room)
        if user.current_room_id is not None:
            room = self.db.rooms[user.current_room_id]
            RoomService(self.db).detach_member(room, user.id)
        # 2. rooms owned but not joined → hand over to first member or close
        for room in [r for r in self.db.rooms.values() if r.owner_id == user.id]:
            if room.member_ids:
                room.owner_id = room.member_ids[0]
            else:
                RoomService(self.db).close_room(room)
        # 3. remove sessions and tasks
        active = find_active_session(self.db, user.id)
        if active:
            SessionService(self.db).force_cancel(active)
        for sid in [s.id for s in self.db.sessions.values() if s.user_id == user.id]:
            del self.db.sessions[sid]
        for tid in [t.id for t in self.db.tasks.values() if t.user_id == user.id]:
            del self.db.tasks[tid]
        del self.db.users[user.id]

    def _ensure_unique(self, username: Optional[str] = None, email: Optional[str] = None) -> None:
        for u in self.db.users.values():
            if username and u.username == username:
                raise ConflictError(f"Username '{username}' is already taken",
                                    code="USERNAME_TAKEN")
            if email and u.email == email:
                raise ConflictError(f"Email '{email}' is already registered",
                                    code="EMAIL_TAKEN")

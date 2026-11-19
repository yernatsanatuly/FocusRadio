"""User management, statistics and achievements backed by PostgreSQL."""
from __future__ import annotations

from collections import Counter
from typing import Literal, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError
from app.models import FocusSession, Room, Task, User, UserAchievement
from app.models.enums import FINISHED_SESSION_STATUSES, LeaderboardMetric, SessionStatus, TaskStatus
from app.schemas.leaderboard import Leaderboard
from app.schemas.users import AchievementResponse, UserCreate, UserResponse, UserStats, UserUpdate
from app.services import gamification
from app.services.common import (
    ensure_actor_exists,
    ensure_same_user,
    find_active_session,
    get_room,
    get_user,
    paginate_query,
)
from app.services.room_service import RoomService
from app.services.session_service import SessionService

UserSort = Literal["id", "username", "xp", "focus_minutes", "streak"]

_METRIC_COLUMNS = {
    LeaderboardMetric.XP: User.xp,
    LeaderboardMetric.FOCUS_MINUTES: User.total_focus_minutes,
    LeaderboardMetric.STREAK: User.current_streak,
    LeaderboardMetric.SESSIONS: User.completed_sessions,
}


def to_response(user: User) -> UserResponse:
    level = gamification.level_for_xp(user.xp)
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        bio=user.bio,
        xp=user.xp,
        level=level,
        level_title=gamification.level_title(level),
        current_streak=user.current_streak,
        longest_streak=user.longest_streak,
        total_focus_minutes=user.total_focus_minutes,
        completed_sessions=user.completed_sessions,
        completed_tasks=user.completed_tasks,
        current_room_id=user.current_room_id,
        created_at=user.created_at,
    )


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- queries
    def list(self, *, search: Optional[str], sort_by: UserSort, limit: int, offset: int) -> dict:
        stmt = select(User)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(User.username.ilike(pattern), User.display_name.ilike(pattern))
            )

        order_map = {
            "id": (User.id.asc(),),
            "username": (User.username.asc(),),
            "xp": (User.xp.desc(), User.id.asc()),
            "focus_minutes": (User.total_focus_minutes.desc(), User.id.asc()),
            "streak": (User.current_streak.desc(), User.id.asc()),
        }
        stmt = stmt.order_by(*order_map[sort_by])

        items, total = paginate_query(self.db, stmt, limit, offset)
        return {
            "items": [to_response(u) for u in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get(self, user_id: int) -> UserResponse:
        return to_response(get_user(self.db, user_id))

    def achievements(self, user_id: int, unlocked_only: bool) -> list[AchievementResponse]:
        items = gamification.list_achievements(self.db, get_user(self.db, user_id))
        return [a for a in items if a.unlocked] if unlocked_only else items

    def stats(self, user_id: int) -> UserStats:
        user = get_user(self.db, user_id)

        session_rows = self.db.execute(
            select(FocusSession.status, FocusSession.mode).where(FocusSession.user_id == user.id)
        ).all()
        by_status = Counter(status.value for status, _ in session_rows)
        finished_count = sum(1 for status, _ in session_rows if status in FINISHED_SESSION_STATUSES)
        completed = by_status.get(SessionStatus.COMPLETED.value, 0)
        rewarded_modes = [
            mode.value
            for status, mode in session_rows
            if status in (SessionStatus.COMPLETED, SessionStatus.ENDED_EARLY)
        ]
        modes = Counter(rewarded_modes)

        task_statuses = list(
            self.db.scalars(select(Task.status).where(Task.user_id == user.id))
        )
        achievements_unlocked = (
            self.db.scalar(
                select(func.count(UserAchievement.id)).where(UserAchievement.user_id == user.id)
            )
            or 0
        )
        active = find_active_session(self.db, user.id)

        return UserStats(
            user_id=user.id,
            level=gamification.level_info(user.xp),
            current_streak=user.current_streak,
            longest_streak=user.longest_streak,
            total_focus_minutes=user.total_focus_minutes,
            completed_sessions=user.completed_sessions,
            sessions_by_status={st.value: by_status.get(st.value, 0) for st in SessionStatus},
            completion_rate_percent=(
                round(completed / finished_count * 100, 1) if finished_count else 0.0
            ),
            average_session_minutes=(
                round(user.total_focus_minutes / len(rewarded_modes), 1)
                if rewarded_modes
                else 0.0
            ),
            favorite_mode=modes.most_common(1)[0][0] if modes else None,
            tasks_open=sum(st != TaskStatus.DONE for st in task_statuses),
            tasks_done=sum(st == TaskStatus.DONE for st in task_statuses),
            achievements_unlocked=achievements_unlocked,
            achievements_total=len(gamification.ACHIEVEMENTS),
            active_session_id=active.id if active else None,
        )

    def leaderboard(self, metric: LeaderboardMetric, limit: int) -> Leaderboard:
        col = _METRIC_COLUMNS[metric]
        top_users = list(
            self.db.scalars(
                select(User).order_by(col.desc(), User.xp.desc(), User.id.asc()).limit(limit)
            ).all()
        )
        return Leaderboard(
            metric=metric,
            scope="global",
            entries=gamification.build_leaderboard(top_users, metric, limit),
        )

    # --------------------------------------------------------------- commands
    def create(self, data: UserCreate) -> UserResponse:
        self._ensure_unique(username=data.username, email=data.email)
        user = User(**data.model_dump())
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
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
                self._ensure_unique(email=changes["email"], exclude_id=user.id)

        for key, value in changes.items():
            setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return to_response(user)

    def delete(self, user_id: int, acting_user_id: int) -> None:
        ensure_actor_exists(self.db, acting_user_id)
        user = get_user(self.db, user_id)
        ensure_same_user(acting_user_id, user.id, "account")

        room_service = RoomService(self.db)
        if user.current_room_id is not None:
            room = get_room(self.db, user.current_room_id, load_relations=True)
            room_service.detach_member(room, user.id)

        owned_rooms = list(
            self.db.scalars(
                select(Room)
                .where(Room.owner_id == user.id)
                .options(selectinload(Room.members))
            ).all()
        )
        for room in owned_rooms:
            if room.members:
                room.owner_id = room.members[0].user_id
                self.db.flush()
            else:
                room_service.close_room(room)

        active = find_active_session(self.db, user.id)
        if active is not None:
            SessionService(self.db).force_cancel(active)

        self.db.refresh(user)
        self.db.delete(user)
        self.db.commit()

    def _ensure_unique(
        self,
        username: Optional[str] = None,
        email: Optional[str] = None,
        *,
        exclude_id: Optional[int] = None,
    ) -> None:
        if username:
            stmt = select(User.id).where(User.username == username)
            if exclude_id is not None:
                stmt = stmt.where(User.id != exclude_id)
            if self.db.scalar(stmt) is not None:
                raise ConflictError(
                    f"Username '{username}' is already taken", code="USERNAME_TAKEN"
                )
        if email:
            stmt = select(User.id).where(User.email == email)
            if exclude_id is not None:
                stmt = stmt.where(User.id != exclude_id)
            if self.db.scalar(stmt) is not None:
                raise ConflictError(
                    f"Email '{email}' is already registered", code="EMAIL_TAKEN"
                )

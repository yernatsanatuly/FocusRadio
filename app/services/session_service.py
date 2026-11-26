"""Focus session (timer) workflow backed by PostgreSQL.

State machine:

    ACTIVE ──pause──▶ PAUSED ──resume──▶ ACTIVE
      │                 │
      ├──complete──▶ COMPLETED      (planned time reached → full XP + bonuses)
      ├──complete?force=true──▶ ENDED_EARLY (partial XP, no streak)
      └──cancel───▶ CANCELLED       (no XP)
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError
from app.models import FocusSession, RoomMember, Task, User, utcnow
from app.models.enums import (
    ACTIVE_SESSION_STATUSES,
    SessionMode,
    SessionStatus,
    TaskStatus,
)
from app.schemas.sessions import (
    SessionCreate,
    SessionFinishResult,
    SessionResponse,
    SessionUpdate,
)
from app.services import gamification
from app.services.common import (
    ensure_owner_or_admin,
    find_active_session,
    get_session,
    get_task,
    get_user,
    paginate_query,
)

PRESETS: dict[SessionMode, tuple[int, int]] = {
    SessionMode.POMODORO: (25, 5),
    SessionMode.SHORT: (15, 3),
    SessionMode.DEEP_WORK: (50, 10),
}


def planned_seconds(session: FocusSession) -> float:
    return session.focus_minutes * settings.seconds_per_minute


def elapsed_focus_seconds(session: FocusSession, now: Optional[datetime] = None) -> float:
    if session.status not in ACTIVE_SESSION_STATUSES:
        return float(session.focused_seconds)
    now = now or utcnow()
    end = session.paused_at if session.status == SessionStatus.PAUSED else now
    return max(0.0, (end - session.started_at).total_seconds() - session.total_paused_seconds)


def remaining_seconds(session: FocusSession) -> int:
    if session.status not in ACTIVE_SESSION_STATUSES:
        return 0
    return max(0, math.ceil(planned_seconds(session) - elapsed_focus_seconds(session)))


def to_response(session: FocusSession) -> SessionResponse:
    elapsed = elapsed_focus_seconds(session)
    planned = planned_seconds(session)
    paused = session.total_paused_seconds
    if session.status == SessionStatus.PAUSED and session.paused_at:
        paused += (utcnow() - session.paused_at).total_seconds()
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        room_id=session.room_id,
        task_id=session.task_id,
        mode=session.mode,
        status=session.status,
        focus_minutes=session.focus_minutes,
        break_minutes=session.break_minutes,
        started_at=session.started_at,
        ended_at=session.ended_at,
        pause_count=session.pause_count,
        paused_seconds=int(paused),
        elapsed_focus_seconds=int(min(elapsed, planned)),
        remaining_seconds=remaining_seconds(session),
        progress_percent=round(min(elapsed / planned, 1.0) * 100, 1) if planned else 0.0,
        is_time_up=session.status in ACTIVE_SESSION_STATUSES and elapsed >= planned,
        xp_earned=session.xp_earned,
        notes=session.notes,
    )


class SessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        actor: User,
        user_id: Optional[int],
        room_id: Optional[int],
        status: Optional[SessionStatus],
        mode: Optional[SessionMode],
        limit: int,
        offset: int,
    ) -> dict:
        if not actor.is_admin:
            if user_id is not None and user_id != actor.id:
                raise ForbiddenError(
                    "You can only view your own focus sessions",
                    code="NOT_RESOURCE_OWNER",
                    details={"owner_id": user_id, "acting_user_id": actor.id},
                )
            user_id = actor.id

        stmt = select(FocusSession)
        if user_id is not None:
            stmt = stmt.where(FocusSession.user_id == user_id)
        if room_id is not None:
            stmt = stmt.where(FocusSession.room_id == room_id)
        if status is not None:
            stmt = stmt.where(FocusSession.status == status)
        if mode is not None:
            stmt = stmt.where(FocusSession.mode == mode)
        stmt = stmt.order_by(FocusSession.started_at.desc(), FocusSession.id.desc())

        items, total = paginate_query(self.db, stmt, limit, offset)
        return {
            "items": [to_response(s) for s in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get(self, session_id: int, actor: User) -> SessionResponse:
        return to_response(self._owned(session_id, actor))

    def start(self, actor: User, data: SessionCreate) -> SessionResponse:
        user = actor

        active = find_active_session(self.db, user.id)
        if active:
            raise ConflictError(
                "User already has a running focus session",
                code="SESSION_ALREADY_RUNNING",
                details={"active_session_id": active.id, "status": active.status.value},
            )

        task = self._validate_task(data.task_id, user.id) if data.task_id else None

        if data.mode == SessionMode.CUSTOM:
            focus = data.focus_minutes
            brk = data.break_minutes if data.break_minutes is not None else max(1, focus // 5)
        else:
            focus, brk = PRESETS[data.mode]

        session = FocusSession(
            user_id=user.id,
            mode=data.mode,
            focus_minutes=focus,
            break_minutes=brk,
            room_id=user.current_room_id,
            task_id=task.id if task else None,
            notes=data.notes,
        )
        self.db.add(session)
        if task and task.status == TaskStatus.TODO:
            task.status = TaskStatus.IN_PROGRESS
        self.db.commit()
        self.db.refresh(session)
        return to_response(session)

    def update(self, session_id: int, actor: User, data: SessionUpdate) -> SessionResponse:
        session = self._owned(session_id, actor)
        if "task_id" in data.model_fields_set:
            if session.status not in ACTIVE_SESSION_STATUSES:
                raise ConflictError(
                    "Task can only be changed while the session is running",
                    code="SESSION_ALREADY_FINISHED",
                )
            if data.task_id is None:
                session.task_id = None
            else:
                task = self._validate_task(data.task_id, session.user_id)
                session.task_id = task.id
                if task.status == TaskStatus.TODO:
                    task.status = TaskStatus.IN_PROGRESS
        if "notes" in data.model_fields_set:
            session.notes = data.notes
        self.db.commit()
        self.db.refresh(session)
        return to_response(session)

    def pause(self, session_id: int, actor: User) -> SessionResponse:
        session = self._owned(session_id, actor)
        self._require_status(session, SessionStatus.ACTIVE, "pause")
        if elapsed_focus_seconds(session) >= planned_seconds(session):
            raise ConflictError(
                "Focus time is already over — complete the session instead",
                code="FOCUS_TIME_OVER",
            )
        if session.pause_count >= settings.max_pauses_per_session:
            raise BusinessRuleError(
                f"A session can be paused at most {settings.max_pauses_per_session} times",
                code="PAUSE_LIMIT_REACHED",
                details={"pause_count": session.pause_count},
            )
        session.status = SessionStatus.PAUSED
        session.paused_at = utcnow()
        session.pause_count += 1
        self.db.commit()
        self.db.refresh(session)
        return to_response(session)

    def resume(self, session_id: int, actor: User) -> SessionResponse:
        session = self._owned(session_id, actor)
        self._require_status(session, SessionStatus.PAUSED, "resume")
        self._close_pause(session)
        session.status = SessionStatus.ACTIVE
        self.db.commit()
        self.db.refresh(session)
        return to_response(session)

    def complete(self, session_id: int, actor: User, force: bool) -> SessionFinishResult:
        session = self._owned(session_id, actor)
        self._require_running(session, "complete")

        elapsed = elapsed_focus_seconds(session)
        planned = planned_seconds(session)
        if elapsed < planned and not force:
            raise ConflictError(
                "Planned focus time has not been reached yet. "
                "Wait for the timer or use force=true to end early with partial XP.",
                code="FOCUS_TIME_NOT_REACHED",
                details={"remaining_seconds": math.ceil(planned - elapsed)},
            )

        user = get_user(self.db, session.user_id)
        level_before = gamification.level_for_xp(user.xp)
        self._close_pause(session)
        session.ended_at = utcnow()

        if elapsed >= planned:
            session.status = SessionStatus.COMPLETED
            session.focused_seconds = int(planned)
        else:
            session.status = SessionStatus.ENDED_EARLY
            session.focused_seconds = int(elapsed)

        mates = self._focusing_room_mates(user.id, user.current_room_id)
        breakdown, new_achievements = gamification.reward_session(self.db, user, session, mates)

        if session.status == SessionStatus.COMPLETED and session.task_id is not None:
            task = self.db.get(Task, session.task_id)
            if task is not None:
                task.completed_pomodoros += 1

        self.db.commit()
        self.db.refresh(session)
        self.db.refresh(user)

        level_after = gamification.level_info(user.xp)
        return SessionFinishResult(
            session=to_response(session),
            xp_breakdown=breakdown,
            total_xp=session.xp_earned,
            level=level_after,
            leveled_up=level_after.level > level_before,
            current_streak=user.current_streak,
            new_achievements=new_achievements,
            suggested_break_minutes=(
                session.break_minutes if session.status == SessionStatus.COMPLETED else 0
            ),
        )

    def cancel(self, session_id: int, actor: User) -> SessionResponse:
        session = self._owned(session_id, actor)
        self._require_running(session, "cancel")
        self.force_cancel(session)
        self.db.commit()
        self.db.refresh(session)
        return to_response(session)

    def delete(self, session_id: int, actor: User) -> None:
        session = self._owned(session_id, actor)
        if session.status in ACTIVE_SESSION_STATUSES:
            raise ConflictError(
                "A running session cannot be deleted; cancel or complete it first",
                code="SESSION_STILL_RUNNING",
            )
        self.db.delete(session)
        self.db.commit()

    def force_cancel(self, session: FocusSession) -> None:
        elapsed = elapsed_focus_seconds(session)
        self._close_pause(session)
        session.status = SessionStatus.CANCELLED
        session.ended_at = utcnow()
        session.focused_seconds = int(elapsed)
        self.db.flush()

    def _owned(self, session_id: int, actor: User) -> FocusSession:
        session = get_session(self.db, session_id)
        ensure_owner_or_admin(actor, session.user_id, "session")
        return session

    @staticmethod
    def _close_pause(session: FocusSession) -> None:
        if session.status == SessionStatus.PAUSED and session.paused_at:
            session.total_paused_seconds += (utcnow() - session.paused_at).total_seconds()
            session.paused_at = None

    @staticmethod
    def _require_status(session: FocusSession, expected: SessionStatus, action: str) -> None:
        if session.status != expected:
            raise ConflictError(
                f"Cannot {action} a session with status '{session.status.value}'",
                code="INVALID_SESSION_STATE",
                details={
                    "current_status": session.status.value,
                    "required_status": expected.value,
                },
            )

    @staticmethod
    def _require_running(session: FocusSession, action: str) -> None:
        if session.status not in ACTIVE_SESSION_STATUSES:
            raise ConflictError(
                f"Cannot {action} a session with status '{session.status.value}'",
                code="INVALID_SESSION_STATE",
                details={"current_status": session.status.value},
            )

    def _validate_task(self, task_id: int, user_id: int) -> Task:
        task = get_task(self.db, task_id)
        if task.user_id != user_id:
            raise ForbiddenError(
                "You can only focus on your own tasks",
                code="TASK_NOT_OWNED",
                details={"task_id": task_id},
            )
        if task.status == TaskStatus.DONE:
            raise ConflictError(
                "Task is already done",
                code="TASK_ALREADY_DONE",
                details={"task_id": task_id},
            )
        return task

    def _focusing_room_mates(self, user_id: int, room_id: Optional[int]) -> int:
        if room_id is None:
            return 0
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

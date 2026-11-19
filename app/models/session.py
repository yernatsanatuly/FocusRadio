from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pg_enum, utcnow
from app.models.enums import SessionMode, SessionStatus

if TYPE_CHECKING:
    from app.models.room import Room
    from app.models.task import Task
    from app.models.user import User, UserAchievement


class FocusSession(Base):
    __tablename__ = "focus_sessions"
    __table_args__ = (
        CheckConstraint("focus_minutes >= 1 AND focus_minutes <= 180", name="focus_minutes_range"),
        CheckConstraint("break_minutes >= 0 AND break_minutes <= 60", name="break_minutes_range"),
        CheckConstraint("pause_count >= 0 AND pause_count <= 3", name="pause_count_range"),
        CheckConstraint(
            "total_paused_seconds >= 0", name="total_paused_seconds_non_negative"
        ),
        CheckConstraint("focused_seconds >= 0", name="focused_seconds_non_negative"),
        CheckConstraint("xp_earned >= 0", name="xp_earned_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mode: Mapped[SessionMode] = mapped_column(pg_enum(SessionMode, "session_mode_enum"), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        pg_enum(SessionStatus, "session_status_enum"),
        nullable=False,
        default=SessionStatus.ACTIVE,
        server_default=SessionStatus.ACTIVE.value,
        index=True,
    )
    focus_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_paused_seconds: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    pause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    focused_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    xp_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    user: Mapped["User"] = relationship(back_populates="sessions")
    room: Mapped[Optional["Room"]] = relationship(back_populates="sessions")
    task: Mapped[Optional["Task"]] = relationship(back_populates="sessions")
    unlocked_achievements: Mapped[list["UserAchievement"]] = relationship(back_populates="session")


Index(
    "uq_focus_sessions_one_active_per_user",
    FocusSession.user_id,
    unique=True,
    postgresql_where=text("status IN ('active', 'paused')"),
)

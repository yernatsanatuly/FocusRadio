from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pg_enum, utcnow
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.room import Room, RoomMember
    from app.models.session import FocusSession
    from app.models.task import Task


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("xp >= 0", name="xp_non_negative"),
        CheckConstraint("total_focus_minutes >= 0", name="total_focus_minutes_non_negative"),
        CheckConstraint("completed_sessions >= 0", name="completed_sessions_non_negative"),
        CheckConstraint("completed_tasks >= 0", name="completed_tasks_non_negative"),
        CheckConstraint("current_streak >= 0", name="current_streak_non_negative"),
        CheckConstraint("longest_streak >= 0", name="longest_streak_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role_enum"),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        index=True,
    )
    bio: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_focus_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    completed_sessions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    completed_tasks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    current_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    longest_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_focus_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    owned_rooms: Mapped[list["Room"]] = relationship(back_populates="owner")
    room_membership: Mapped[Optional["RoomMember"]] = relationship(
        back_populates="user",
        uselist=False,
        lazy="joined",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list["FocusSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    achievements: Mapped[list["UserAchievement"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def current_room_id(self) -> Optional[int]:
        return self.room_membership.room_id if self.room_membership else None

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uq_user_achievements_user_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("focus_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="achievements")
    session: Mapped[Optional["FocusSession"]] = relationship(
        back_populates="unlocked_achievements"
    )

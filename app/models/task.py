from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pg_enum, utcnow
from app.models.enums import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from app.models.session import FocusSession
    from app.models.user import User


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "estimated_pomodoros >= 1 AND estimated_pomodoros <= 20",
            name="estimated_pomodoros_range",
        ),
        CheckConstraint(
            "completed_pomodoros >= 0",
            name="completed_pomodoros_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    priority: Mapped[TaskPriority] = mapped_column(
        pg_enum(TaskPriority, "task_priority_enum"),
        nullable=False,
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
    )
    status: Mapped[TaskStatus] = mapped_column(
        pg_enum(TaskStatus, "task_status_enum"),
        nullable=False,
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
        index=True,
    )
    estimated_pomodoros: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    completed_pomodoros: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    xp_awarded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="tasks")
    sessions: Mapped[list["FocusSession"]] = relationship(back_populates="task")


Index(
    "uq_tasks_open_user_title_lower",
    Task.user_id,
    func.lower(Task.title),
    unique=True,
    postgresql_where=text("status != 'done'"),
)

"""Personal task list linked to focus sessions, backed by PostgreSQL."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError
from app.models import FocusSession, Task, User, utcnow
from app.models.enums import ACTIVE_SESSION_STATUSES, TaskPriority, TaskStatus
from app.schemas.tasks import TaskCreate, TaskResponse, TaskUpdate, TaskUpdateResult
from app.services import gamification
from app.services.common import (
    ensure_owner_or_admin,
    get_task,
    get_user,
    paginate_query,
)

MAX_OPEN_TASKS = 50


def to_response(task: Task) -> TaskResponse:
    progress = (
        100.0
        if task.status == TaskStatus.DONE
        else round(min(task.completed_pomodoros / task.estimated_pomodoros, 1.0) * 100, 1)
    )
    return TaskResponse(
        id=task.id,
        user_id=task.user_id,
        title=task.title,
        description=task.description,
        priority=task.priority,
        status=task.status,
        estimated_pomodoros=task.estimated_pomodoros,
        completed_pomodoros=task.completed_pomodoros,
        progress_percent=progress,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        actor: User,
        user_id: Optional[int],
        status: Optional[TaskStatus],
        priority: Optional[TaskPriority],
        limit: int,
        offset: int,
    ) -> dict:
        if not actor.is_admin:
            if user_id is not None and user_id != actor.id:
                raise ForbiddenError(
                    "You can only view your own tasks",
                    code="NOT_RESOURCE_OWNER",
                    details={"owner_id": user_id, "acting_user_id": actor.id},
                )
            user_id = actor.id
        elif user_id is not None:
            get_user(self.db, user_id)

        stmt = select(Task)
        if user_id is not None:
            stmt = stmt.where(Task.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)

        is_done_order = case((Task.status == TaskStatus.DONE, 1), else_=0)
        priority_order = case(
            (Task.priority == TaskPriority.HIGH, 0),
            (Task.priority == TaskPriority.MEDIUM, 1),
            else_=2,
        )
        stmt = stmt.order_by(is_done_order, priority_order, Task.id.asc())

        items, total = paginate_query(self.db, stmt, limit, offset)
        return {
            "items": [to_response(t) for t in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get(self, task_id: int, actor: User) -> TaskResponse:
        return to_response(self._owned(task_id, actor))

    def create(self, actor: User, data: TaskCreate) -> TaskResponse:
        open_count = (
            self.db.scalar(
                select(func.count(Task.id)).where(
                    Task.user_id == actor.id,
                    Task.status != TaskStatus.DONE,
                )
            )
            or 0
        )
        if open_count >= MAX_OPEN_TASKS:
            raise BusinessRuleError(
                f"A user can have at most {MAX_OPEN_TASKS} open tasks",
                code="TOO_MANY_OPEN_TASKS",
            )
        self._ensure_open_title_unique(actor.id, data.title)

        task = Task(user_id=actor.id, **data.model_dump())
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return to_response(task)

    def update(self, task_id: int, actor: User, data: TaskUpdate) -> TaskUpdateResult:
        task = self._owned(task_id, actor)
        changes = data.model_dump(exclude_unset=True)
        new_status = changes.pop("status", None)

        if task.status == TaskStatus.DONE and changes and new_status in (None, TaskStatus.DONE):
            raise ConflictError(
                "Completed tasks are read-only; reopen the task first "
                "(status=todo or in_progress)",
                code="TASK_COMPLETED_LOCKED",
            )
        if (
            "estimated_pomodoros" in changes
            and changes["estimated_pomodoros"] < task.completed_pomodoros
        ):
            raise BusinessRuleError(
                "estimated_pomodoros cannot be lower than already completed pomodoros",
                code="ESTIMATE_BELOW_PROGRESS",
                details={"completed_pomodoros": task.completed_pomodoros},
            )

        effective_title = changes.get("title", task.title)
        effective_status = new_status if new_status is not None else task.status
        reopening = task.status == TaskStatus.DONE and effective_status != TaskStatus.DONE
        title_changed = "title" in changes and changes["title"].lower() != task.title.lower()
        if effective_status != TaskStatus.DONE and (title_changed or reopening):
            self._ensure_open_title_unique(task.user_id, effective_title, exclude_id=task.id)

        for key, value in changes.items():
            setattr(task, key, value)

        new_achievements = []
        if new_status is not None and new_status != task.status:
            if new_status == TaskStatus.DONE:
                task.status = TaskStatus.DONE
                task.completed_at = utcnow()
                if not task.xp_awarded:
                    task.xp_awarded = True
                    owner = get_user(self.db, task.user_id)
                    new_achievements = gamification.reward_task_completion(self.db, owner)
            else:
                task.status = new_status
                task.completed_at = None

        self.db.commit()
        self.db.refresh(task)
        return TaskUpdateResult(task=to_response(task), new_achievements=new_achievements)

    def delete(self, task_id: int, actor: User) -> None:
        task = self._owned(task_id, actor)
        active_session_id = self.db.scalar(
            select(FocusSession.id).where(
                FocusSession.task_id == task.id,
                FocusSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
        )
        if active_session_id is not None:
            raise ConflictError(
                "Task is linked to a running focus session",
                code="TASK_IN_ACTIVE_SESSION",
                details={"session_id": active_session_id},
            )
        self.db.execute(
            update(FocusSession).where(FocusSession.task_id == task.id).values(task_id=None)
        )
        self.db.delete(task)
        self.db.commit()

    def _owned(self, task_id: int, actor: User) -> Task:
        task = get_task(self.db, task_id)
        ensure_owner_or_admin(actor, task.user_id, "task")
        return task

    def _ensure_open_title_unique(
        self, user_id: int, title: str, *, exclude_id: Optional[int] = None
    ) -> None:
        stmt = select(Task.id).where(
            Task.user_id == user_id,
            Task.status != TaskStatus.DONE,
            func.lower(Task.title) == title.lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(Task.id != exclude_id)
        if self.db.scalar(stmt) is not None:
            raise ConflictError(
                "You already have an open task with this title",
                code="DUPLICATE_TASK",
            )

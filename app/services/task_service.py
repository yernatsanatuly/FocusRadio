"""Personal task list linked to focus sessions."""
from __future__ import annotations

from typing import Optional

from app.core.database import Database
from app.core.exceptions import BusinessRuleError, ConflictError
from app.models.entities import Task, utcnow
from app.models.enums import ACTIVE_SESSION_STATUSES, TaskPriority, TaskStatus
from app.schemas.tasks import TaskCreate, TaskResponse, TaskUpdate, TaskUpdateResult
from app.services import gamification
from app.services.common import (
    ensure_actor_exists,
    ensure_same_user,
    get_task,
    get_user,
    paginate,
)

MAX_OPEN_TASKS = 50
_PRIORITY_ORDER = {TaskPriority.HIGH: 0, TaskPriority.MEDIUM: 1, TaskPriority.LOW: 2}


def to_response(task: Task) -> TaskResponse:
    progress = 100.0 if task.status == TaskStatus.DONE else round(
        min(task.completed_pomodoros / task.estimated_pomodoros, 1.0) * 100, 1)
    return TaskResponse(
        id=task.id, user_id=task.user_id, title=task.title, description=task.description,
        priority=task.priority, status=task.status,
        estimated_pomodoros=task.estimated_pomodoros,
        completed_pomodoros=task.completed_pomodoros, progress_percent=progress,
        created_at=task.created_at, completed_at=task.completed_at,
    )


class TaskService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self, *, user_id: Optional[int], status: Optional[TaskStatus],
             priority: Optional[TaskPriority], limit: int, offset: int) -> dict:
        if user_id is not None:
            get_user(self.db, user_id)
        tasks = [
            t for t in self.db.tasks.values()
            if (user_id is None or t.user_id == user_id)
            and (status is None or t.status == status)
            and (priority is None or t.priority == priority)
        ]
        # open tasks first, then by priority, then oldest first
        tasks.sort(key=lambda t: (t.status == TaskStatus.DONE, _PRIORITY_ORDER[t.priority], t.id))
        page = paginate(tasks, limit, offset)
        page["items"] = [to_response(t) for t in page["items"]]
        return page

    def get(self, task_id: int) -> TaskResponse:
        return to_response(get_task(self.db, task_id))

    def create(self, data: TaskCreate) -> TaskResponse:
        user = get_user(self.db, data.user_id)
        open_tasks = [t for t in self.db.tasks.values()
                      if t.user_id == user.id and t.status != TaskStatus.DONE]
        if len(open_tasks) >= MAX_OPEN_TASKS:
            raise BusinessRuleError(f"A user can have at most {MAX_OPEN_TASKS} open tasks",
                                    code="TOO_MANY_OPEN_TASKS")
        if any(t.title.lower() == data.title.lower() for t in open_tasks):
            raise ConflictError("You already have an open task with this title",
                                code="DUPLICATE_TASK")
        tid = self.db.next_id("tasks")
        task = Task(id=tid, **data.model_dump())
        self.db.tasks[tid] = task
        return to_response(task)

    def update(self, task_id: int, acting_user_id: int, data: TaskUpdate) -> TaskUpdateResult:
        task = self._owned(task_id, acting_user_id)
        changes = data.model_dump(exclude_unset=True)
        new_status = changes.pop("status", None)

        if task.status == TaskStatus.DONE and changes and new_status in (None, TaskStatus.DONE):
            raise ConflictError("Completed tasks are read-only; reopen the task first "
                                "(status=todo or in_progress)", code="TASK_COMPLETED_LOCKED")
        if "estimated_pomodoros" in changes and changes["estimated_pomodoros"] < task.completed_pomodoros:
            raise BusinessRuleError(
                "estimated_pomodoros cannot be lower than already completed pomodoros",
                code="ESTIMATE_BELOW_PROGRESS",
                details={"completed_pomodoros": task.completed_pomodoros},
            )
        if "title" in changes and changes["title"].lower() != task.title.lower():
            if any(t.id != task.id and t.user_id == task.user_id and t.status != TaskStatus.DONE
                   and t.title.lower() == changes["title"].lower() for t in self.db.tasks.values()):
                raise ConflictError("You already have an open task with this title",
                                    code="DUPLICATE_TASK")

        for key, value in changes.items():
            setattr(task, key, value)

        new_achievements = []
        if new_status is not None and new_status != task.status:
            if new_status == TaskStatus.DONE:
                task.status = TaskStatus.DONE
                task.completed_at = utcnow()
                if not task.xp_awarded:  # XP is granted only once per task
                    task.xp_awarded = True
                    new_achievements = gamification.reward_task_completion(
                        self.db.users[task.user_id])
            else:  # reopen or move between todo/in_progress
                task.status = new_status
                task.completed_at = None

        return TaskUpdateResult(task=to_response(task), new_achievements=new_achievements)

    def delete(self, task_id: int, acting_user_id: int) -> None:
        task = self._owned(task_id, acting_user_id)
        for s in self.db.sessions.values():
            if s.task_id == task.id and s.status in ACTIVE_SESSION_STATUSES:
                raise ConflictError("Task is linked to a running focus session",
                                    code="TASK_IN_ACTIVE_SESSION", details={"session_id": s.id})
        for s in self.db.sessions.values():
            if s.task_id == task.id:
                s.task_id = None
        del self.db.tasks[task.id]

    def _owned(self, task_id: int, acting_user_id: int) -> Task:
        ensure_actor_exists(self.db, acting_user_id)
        task = get_task(self.db, task_id)
        ensure_same_user(acting_user_id, task.user_id, "task")
        return task

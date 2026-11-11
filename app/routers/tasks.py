"""/tasks endpoints — user tasks integrated with focus timer."""
from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.dependencies import ActingUserId, Limit, Offset, Tasks
from app.models.enums import TaskPriority, TaskStatus
from app.schemas.common import Page, error_responses
from app.schemas.tasks import TaskCreate, TaskResponse, TaskUpdate, TaskUpdateResult

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED,
             responses=error_responses(404, 409, 422), summary="Create a task")
def create_task(data: TaskCreate, service: Tasks):
    return service.create(data)


@router.get("", response_model=Page[TaskResponse], summary="List tasks")
def list_tasks(
    service: Tasks,
    user_id: Optional[int] = Query(None, ge=1),
    status_: Optional[TaskStatus] = Query(None, alias="status"),
    priority: Optional[TaskPriority] = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return service.list(user_id=user_id, status=status_, priority=priority,
                        limit=limit, offset=offset)


@router.get("/{task_id}", response_model=TaskResponse, responses=error_responses(404),
            summary="Get a task")
def get_task(task_id: int, service: Tasks):
    return service.get(task_id)


@router.patch("/{task_id}", response_model=TaskUpdateResult,
              responses=error_responses(403, 404, 409, 422), summary="Update or complete a task")
def update_task(task_id: int, data: TaskUpdate, acting_user_id: ActingUserId, service: Tasks):
    return service.update(task_id, acting_user_id, data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=error_responses(403, 404, 409), summary="Delete a task")
def delete_task(task_id: int, acting_user_id: ActingUserId, service: Tasks):
    service.delete(task_id, acting_user_id)

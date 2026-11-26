from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentUser, Limit, Offset, Tasks
from app.models.enums import TaskPriority, TaskStatus
from app.schemas.common import Page, error_responses
from app.schemas.tasks import TaskCreate, TaskResponse, TaskUpdate, TaskUpdateResult

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 409, 422),
    summary="Create a personal task",
)
def create_task(data: TaskCreate, current_user: CurrentUser, service: Tasks):
    return service.create(current_user, data)


@router.get(
    "",
    response_model=Page[TaskResponse],
    responses=error_responses(401, 403, 404),
    summary="List tasks (own tasks for regular users; all/filtered for admins)",
)
def list_tasks(
    current_user: CurrentUser,
    service: Tasks,
    user_id: Optional[int] = Query(None, ge=1),
    status_: Optional[TaskStatus] = Query(None, alias="status"),
    priority: Optional[TaskPriority] = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return service.list(
        actor=current_user,
        user_id=user_id,
        status=status_,
        priority=priority,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses=error_responses(401, 403, 404),
    summary="Get a task (owner or admin)",
)
def get_task(task_id: int, current_user: CurrentUser, service: Tasks):
    return service.get(task_id, current_user)


@router.patch(
    "/{task_id}",
    response_model=TaskUpdateResult,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Update or complete a task (owner or admin)",
)
def update_task(task_id: int, data: TaskUpdate, current_user: CurrentUser, service: Tasks):
    return service.update(task_id, current_user, data)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
    summary="Delete a task (owner or admin)",
)
def delete_task(task_id: int, current_user: CurrentUser, service: Tasks):
    service.delete(task_id, current_user)

from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.dependencies import AdminUser, CurrentUser, Limit, Offset, Users
from app.schemas.common import Page, error_responses
from app.schemas.users import (
    AchievementResponse,
    UserCreate,
    UserResponse,
    UserRoleUpdate,
    UserStats,
    UserUpdate,
)
from app.services.user_service import UserSort

router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 409, 422),
    summary="Create a user (admin only; public registration uses POST /auth/register)",
)
def create_user(data: UserCreate, _admin: AdminUser, service: Users):
    return service.create(data)


@router.get(
    "",
    response_model=Page[UserResponse],
    responses=error_responses(401),
    summary="List users",
)
def list_users(
    _current_user: CurrentUser,
    service: Users,
    search: Optional[str] = Query(
        None,
        min_length=1,
        max_length=50,
        description="Search in username / display name",
    ),
    sort_by: UserSort = Query("id"),
    limit: Limit = 20,
    offset: Offset = 0,
):
    return service.list(search=search, sort_by=sort_by, limit=limit, offset=offset)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses=error_responses(401, 404),
    summary="Get a user",
)
def get_user(user_id: int, _current_user: CurrentUser, service: Users):
    return service.get(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Update profile (self or admin)",
)
def update_user(user_id: int, data: UserUpdate, current_user: CurrentUser, service: Users):
    return service.update(user_id, current_user, data)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Change a user's role (admin only)",
)
def update_user_role(user_id: int, data: UserRoleUpdate, _admin: AdminUser, service: Users):
    return service.update_role(user_id, data.role)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
    summary="Delete account (self or admin; leaves room, transfers ownership, removes data)",
)
def delete_user(user_id: int, current_user: CurrentUser, service: Users):
    service.delete(user_id, current_user)


@router.get(
    "/{user_id}/stats",
    response_model=UserStats,
    responses=error_responses(401, 404),
    summary="Productivity statistics and level progress",
)
def user_stats(user_id: int, _current_user: CurrentUser, service: Users):
    return service.stats(user_id)


@router.get(
    "/{user_id}/achievements",
    response_model=list[AchievementResponse],
    responses=error_responses(401, 404),
    summary="Achievements (locked and unlocked)",
)
def user_achievements(
    user_id: int, _current_user: CurrentUser, service: Users, unlocked_only: bool = False
):
    return service.achievements(user_id, unlocked_only)

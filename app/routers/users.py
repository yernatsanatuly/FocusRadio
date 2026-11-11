"""/users endpoints."""
from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.dependencies import ActingUserId, Limit, Offset, Users
from app.schemas.common import Page, error_responses
from app.schemas.users import AchievementResponse, UserCreate, UserResponse, UserStats, UserUpdate
from app.services.user_service import UserSort

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             responses=error_responses(409, 422), summary="Register a user")
def create_user(data: UserCreate, service: Users):
    return service.create(data)


@router.get("", response_model=Page[UserResponse], summary="List users")
def list_users(
    service: Users,
    search: Optional[str] = Query(None, min_length=1, max_length=50,
                                  description="Search in username / display name"),
    sort_by: UserSort = Query("id"),
    limit: Limit = 20,
    offset: Offset = 0,
):
    return service.list(search=search, sort_by=sort_by, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserResponse, responses=error_responses(404),
            summary="Get a user")
def get_user(user_id: int, service: Users):
    return service.get(user_id)


@router.patch("/{user_id}", response_model=UserResponse,
              responses=error_responses(403, 404, 409, 422), summary="Update own profile")
def update_user(user_id: int, data: UserUpdate, acting_user_id: ActingUserId, service: Users):
    return service.update(user_id, acting_user_id, data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=error_responses(403, 404),
               summary="Delete own account (leaves room, transfers ownership, removes data)")
def delete_user(user_id: int, acting_user_id: ActingUserId, service: Users):
    service.delete(user_id, acting_user_id)


@router.get("/{user_id}/stats", response_model=UserStats, responses=error_responses(404),
            summary="Productivity statistics and level progress")
def user_stats(user_id: int, service: Users):
    return service.stats(user_id)


@router.get("/{user_id}/achievements", response_model=list[AchievementResponse],
            responses=error_responses(404), summary="Achievements (locked and unlocked)")
def user_achievements(user_id: int, service: Users, unlocked_only: bool = False):
    return service.achievements(user_id, unlocked_only)

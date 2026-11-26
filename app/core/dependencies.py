from typing import Annotated, Optional

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models import User
from app.services.auth_service import AuthService
from app.services.room_service import RoomService
from app.services.session_service import SessionService
from app.services.task_service import TaskService
from app.services.track_service import TrackService
from app.services.user_service import UserService

DB = Annotated[Session, Depends(get_db)]

Limit = Annotated[int, Query(ge=1, le=100, description="Page size")]
Offset = Annotated[int, Query(ge=0, description="Number of items to skip")]

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="JWT Bearer access token obtained from POST /auth/login",
)


def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: DB,
) -> User:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise UnauthorizedError("Missing Bearer access token", code="NOT_AUTHENTICATED")

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedError("Invalid token subject", code="INVALID_TOKEN") from exc

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Authenticated user no longer exists", code="USER_NOT_FOUND")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    if not current_user.is_admin:
        raise ForbiddenError(
            "Administrator privileges are required for this action",
            code="ADMIN_REQUIRED",
        )
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


def get_auth_service(db: DB) -> AuthService:
    return AuthService(db)


def get_user_service(db: DB) -> UserService:
    return UserService(db)


def get_room_service(db: DB) -> RoomService:
    return RoomService(db)


def get_session_service(db: DB) -> SessionService:
    return SessionService(db)


def get_track_service(db: DB) -> TrackService:
    return TrackService(db)


def get_task_service(db: DB) -> TaskService:
    return TaskService(db)


Auth = Annotated[AuthService, Depends(get_auth_service)]
Users = Annotated[UserService, Depends(get_user_service)]
Rooms = Annotated[RoomService, Depends(get_room_service)]
Sessions = Annotated[SessionService, Depends(get_session_service)]
Tracks = Annotated[TrackService, Depends(get_track_service)]
Tasks = Annotated[TaskService, Depends(get_task_service)]

from typing import Annotated

from fastapi import Depends, Header, Query

from app.core.database import Database, get_db
from app.services.room_service import RoomService
from app.services.session_service import SessionService
from app.services.task_service import TaskService
from app.services.track_service import TrackService
from app.services.user_service import UserService

ActingUserId = Annotated[
    int,
    Header(
        alias="X-User-Id",
        ge=1,
        description="ID of the user performing the action (simplified authentication).",
    ),
]

DB = Annotated[Database, Depends(get_db)]

Limit = Annotated[int, Query(ge=1, le=100, description="Page size")]
Offset = Annotated[int, Query(ge=0, description="Number of items to skip")]


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


Users = Annotated[UserService, Depends(get_user_service)]
Rooms = Annotated[RoomService, Depends(get_room_service)]
Sessions = Annotated[SessionService, Depends(get_session_service)]
Tracks = Annotated[TrackService, Depends(get_track_service)]
Tasks = Annotated[TaskService, Depends(get_task_service)]

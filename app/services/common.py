"""Shared lookup helpers used by several services."""
from typing import Optional

from app.core.database import Database
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.entities import FocusSession, Room, Task, Track, User
from app.models.enums import ACTIVE_SESSION_STATUSES


def get_user(db: Database, user_id: int) -> User:
    user = db.users.get(user_id)
    if user is None:
        raise NotFoundError("User", user_id)
    return user


def get_room(db: Database, room_id: int) -> Room:
    room = db.rooms.get(room_id)
    if room is None:
        raise NotFoundError("Room", room_id)
    return room


def get_track(db: Database, track_id: int) -> Track:
    track = db.tracks.get(track_id)
    if track is None:
        raise NotFoundError("Track", track_id)
    return track


def get_task(db: Database, task_id: int) -> Task:
    task = db.tasks.get(task_id)
    if task is None:
        raise NotFoundError("Task", task_id)
    return task


def get_session(db: Database, session_id: int) -> FocusSession:
    session = db.sessions.get(session_id)
    if session is None:
        raise NotFoundError("Session", session_id)
    return session


def find_active_session(db: Database, user_id: int) -> Optional[FocusSession]:
    """Return the running (active or paused) session of a user, if any."""
    for session in db.sessions.values():
        if session.user_id == user_id and session.status in ACTIVE_SESSION_STATUSES:
            return session
    return None


def ensure_actor_exists(db: Database, acting_user_id: int) -> User:
    """The X-User-Id header must reference an existing user."""
    user = db.users.get(acting_user_id)
    if user is None:
        raise ForbiddenError(f"Acting user id={acting_user_id} does not exist",
                             code="UNKNOWN_ACTING_USER")
    return user


def ensure_same_user(acting_user_id: int, owner_id: int, what: str) -> None:
    if acting_user_id != owner_id:
        raise ForbiddenError(f"Only the owner can modify this {what}",
                             code="NOT_RESOURCE_OWNER",
                             details={"owner_id": owner_id, "acting_user_id": acting_user_id})


def paginate(items: list, limit: int, offset: int) -> dict:
    return {"items": items[offset: offset + limit], "total": len(items),
            "limit": limit, "offset": offset}

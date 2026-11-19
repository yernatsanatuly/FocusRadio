"""Shared SQL lookup and pagination helpers used by several services."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import FocusSession, Room, RoomMember, Task, Track, User
from app.models.enums import ACTIVE_SESSION_STATUSES


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User", user_id)
    return user


def get_room(db: Session, room_id: int, *, load_relations: bool = False) -> Room:
    if load_relations:
        stmt = (
            select(Room)
            .where(Room.id == room_id)
            .options(
                joinedload(Room.current_track),
                selectinload(Room.members).joinedload(RoomMember.user),
            )
            .execution_options(populate_existing=True)
        )
        room = db.scalar(stmt)
    else:
        room = db.get(Room, room_id)
    if room is None:
        raise NotFoundError("Room", room_id)
    return room


def get_track(db: Session, track_id: int) -> Track:
    track = db.get(Track, track_id)
    if track is None:
        raise NotFoundError("Track", track_id)
    return track


def get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task", task_id)
    return task


def get_session(db: Session, session_id: int) -> FocusSession:
    session = db.get(FocusSession, session_id)
    if session is None:
        raise NotFoundError("Session", session_id)
    return session


def find_active_session(db: Session, user_id: int) -> Optional[FocusSession]:
    """Return the running (active or paused) session of a user, if any."""
    return db.scalar(
        select(FocusSession).where(
            FocusSession.user_id == user_id,
            FocusSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
    )


def ensure_actor_exists(db: Session, acting_user_id: int) -> User:
    """The X-User-Id header must reference an existing user."""
    user = db.get(User, acting_user_id)
    if user is None:
        raise ForbiddenError(
            f"Acting user id={acting_user_id} does not exist",
            code="UNKNOWN_ACTING_USER",
        )
    return user


def ensure_same_user(acting_user_id: int, owner_id: int, what: str) -> None:
    if acting_user_id != owner_id:
        raise ForbiddenError(
            f"Only the owner can modify this {what}",
            code="NOT_RESOURCE_OWNER",
            details={"owner_id": owner_id, "acting_user_id": acting_user_id},
        )


def paginate_query(
    db: Session,
    stmt: Select[Any],
    limit: int,
    offset: int,
    *,
    options: Sequence[Any] = (),
) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    query = stmt.options(*options) if options else stmt
    items = list(db.scalars(query.limit(limit).offset(offset)).unique().all())
    return items, total

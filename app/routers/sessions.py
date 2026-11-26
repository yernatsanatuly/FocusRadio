from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.dependencies import CurrentUser, Limit, Offset, Sessions
from app.models.enums import SessionMode, SessionStatus
from app.schemas.common import Page, error_responses
from app.schemas.sessions import (
    SessionCreate,
    SessionFinishResult,
    SessionResponse,
    SessionUpdate,
)

router = APIRouter(prefix="/sessions", tags=["Focus sessions"])


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Start a focus timer (one running session per user)",
)
def start_session(data: SessionCreate, current_user: CurrentUser, service: Sessions):
    return service.start(current_user, data)


@router.get(
    "",
    response_model=Page[SessionResponse],
    responses=error_responses(401, 403),
    summary="List sessions (own history for regular users; all/filtered for admins)",
)
def list_sessions(
    current_user: CurrentUser,
    service: Sessions,
    user_id: Optional[int] = Query(None, ge=1),
    room_id: Optional[int] = Query(None, ge=1),
    status_: Optional[SessionStatus] = Query(None, alias="status"),
    mode: Optional[SessionMode] = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return service.list(
        actor=current_user,
        user_id=user_id,
        room_id=room_id,
        status=status_,
        mode=mode,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    responses=error_responses(401, 403, 404),
    summary="Get a session with live timer state (owner or admin)",
)
def get_session(session_id: int, current_user: CurrentUser, service: Sessions):
    return service.get(session_id, current_user)


@router.patch(
    "/{session_id}",
    response_model=SessionResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Update notes / attached task (owner or admin)",
)
def update_session(
    session_id: int,
    data: SessionUpdate,
    current_user: CurrentUser,
    service: Sessions,
):
    return service.update(session_id, current_user, data)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
    summary="Delete a finished session from history (owner or admin)",
)
def delete_session(session_id: int, current_user: CurrentUser, service: Sessions):
    service.delete(session_id, current_user)


@router.post(
    "/{session_id}/pause",
    response_model=SessionResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Pause the timer (owner or admin)",
)
def pause_session(session_id: int, current_user: CurrentUser, service: Sessions):
    return service.pause(session_id, current_user)


@router.post(
    "/{session_id}/resume",
    response_model=SessionResponse,
    responses=error_responses(401, 403, 404, 409),
    summary="Resume the timer (owner or admin)",
)
def resume_session(session_id: int, current_user: CurrentUser, service: Sessions):
    return service.resume(session_id, current_user)


@router.post(
    "/{session_id}/complete",
    response_model=SessionFinishResult,
    responses=error_responses(401, 403, 404, 409),
    summary="Finish the session and collect XP / achievements (owner or admin)",
)
def complete_session(
    session_id: int,
    current_user: CurrentUser,
    service: Sessions,
    force: bool = Query(
        False,
        description="End before the planned time (partial XP, no bonuses)",
    ),
):
    return service.complete(session_id, current_user, force)


@router.post(
    "/{session_id}/cancel",
    response_model=SessionResponse,
    responses=error_responses(401, 403, 404, 409),
    summary="Abandon the session (no XP; owner or admin)",
)
def cancel_session(session_id: int, current_user: CurrentUser, service: Sessions):
    return service.cancel(session_id, current_user)

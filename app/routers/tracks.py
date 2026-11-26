from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.dependencies import AdminUser, Limit, Offset, Tracks
from app.models.enums import Genre, Mood
from app.schemas.common import Page, error_responses
from app.schemas.tracks import TrackCreate, TrackResponse, TrackUpdate

router = APIRouter(prefix="/tracks", tags=["Tracks"])


@router.post(
    "",
    response_model=TrackResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 409, 422),
    summary="Add track to catalogue (admin only)",
)
def create_track(data: TrackCreate, _admin: AdminUser, service: Tracks):
    return service.create(data)


@router.get("", response_model=Page[TrackResponse], summary="Browse track catalogue")
def list_tracks(
    service: Tracks,
    genre: Optional[Genre] = None,
    mood: Optional[Mood] = None,
    min_energy: Optional[int] = Query(None, ge=1, le=10),
    max_energy: Optional[int] = Query(None, ge=1, le=10),
    search: Optional[str] = Query(None, min_length=1, max_length=50),
    limit: Limit = 20,
    offset: Offset = 0,
):
    return service.list(
        genre=genre,
        mood=mood,
        min_energy=min_energy,
        max_energy=max_energy,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{track_id}",
    response_model=TrackResponse,
    responses=error_responses(404),
    summary="Get track details",
)
def get_track(track_id: int, service: Tracks):
    return service.get(track_id)


@router.patch(
    "/{track_id}",
    response_model=TrackResponse,
    responses=error_responses(401, 403, 404, 409, 422),
    summary="Update track details (admin only)",
)
def update_track(track_id: int, data: TrackUpdate, _admin: AdminUser, service: Tracks):
    return service.update(track_id, data)


@router.delete(
    "/{track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
    summary="Remove track from catalogue (admin only)",
)
def delete_track(track_id: int, _admin: AdminUser, service: Tracks, force: bool = False):
    service.delete(track_id, force=force)

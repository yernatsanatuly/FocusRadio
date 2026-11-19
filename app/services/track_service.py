"""Audio track catalogue backed by PostgreSQL."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models import Room, Track
from app.models.enums import Genre, Mood
from app.schemas.tracks import TrackCreate, TrackResponse, TrackUpdate
from app.services.common import get_track, paginate_query


class TrackService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        genre: Optional[Genre],
        mood: Optional[Mood],
        min_energy: Optional[int],
        max_energy: Optional[int],
        search: Optional[str],
        limit: int,
        offset: int,
    ) -> dict:
        stmt = select(Track)
        if genre is not None:
            stmt = stmt.where(Track.genre == genre)
        if mood is not None:
            stmt = stmt.where(Track.mood == mood)
        if min_energy is not None:
            stmt = stmt.where(Track.energy >= min_energy)
        if max_energy is not None:
            stmt = stmt.where(Track.energy <= max_energy)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(or_(Track.title.ilike(pattern), Track.artist.ilike(pattern)))
        stmt = stmt.order_by(Track.id.asc())

        items, total = paginate_query(self.db, stmt, limit, offset)
        return {
            "items": [TrackResponse.model_validate(t) for t in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get(self, track_id: int) -> TrackResponse:
        return TrackResponse.model_validate(get_track(self.db, track_id))

    def create(self, data: TrackCreate) -> TrackResponse:
        self._ensure_unique(data.title, data.artist)
        track = Track(**data.model_dump())
        self.db.add(track)
        self.db.commit()
        self.db.refresh(track)
        return TrackResponse.model_validate(track)

    def update(self, track_id: int, data: TrackUpdate) -> TrackResponse:
        track = get_track(self.db, track_id)
        changes = data.model_dump(exclude_unset=True)
        title = changes.get("title", track.title)
        artist = changes.get("artist", track.artist)
        if (title.lower(), artist.lower()) != (track.title.lower(), track.artist.lower()):
            self._ensure_unique(title, artist, exclude_id=track.id)
        for key, value in changes.items():
            setattr(track, key, value)
        self.db.commit()
        self.db.refresh(track)
        return TrackResponse.model_validate(track)

    def delete(self, track_id: int, force: bool) -> None:
        track = get_track(self.db, track_id)
        playing_in = list(
            self.db.scalars(
                select(Room.id).where(Room.current_track_id == track.id).order_by(Room.id.asc())
            )
        )
        if playing_in and not force:
            raise ConflictError(
                "Track is currently playing in one or more rooms. "
                "Use force=true to stop it everywhere and delete.",
                code="TRACK_IN_USE",
                details={"room_ids": playing_in},
            )
        if playing_in:
            self.db.execute(
                update(Room).where(Room.id.in_(playing_in)).values(current_track_id=None)
            )
        self.db.delete(track)
        self.db.commit()

    def _ensure_unique(
        self, title: str, artist: str, *, exclude_id: Optional[int] = None
    ) -> None:
        stmt = select(Track.id).where(
            func.lower(Track.title) == title.lower(),
            func.lower(Track.artist) == artist.lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(Track.id != exclude_id)
        existing_id = self.db.scalar(stmt)
        if existing_id is not None:
            raise ConflictError(
                f"Track '{title}' by '{artist}' already exists",
                code="TRACK_ALREADY_EXISTS",
                details={"track_id": existing_id},
            )

"""Audio track catalogue."""
from __future__ import annotations

from typing import Optional

from app.core.database import Database
from app.core.exceptions import ConflictError
from app.models.entities import Track
from app.models.enums import Genre, Mood
from app.schemas.tracks import TrackCreate, TrackResponse, TrackUpdate
from app.services.common import get_track, paginate


class TrackService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list(self, *, genre: Optional[Genre], mood: Optional[Mood],
             min_energy: Optional[int], max_energy: Optional[int],
             search: Optional[str], limit: int, offset: int) -> dict:
        tracks = [
            t for t in self.db.tracks.values()
            if (genre is None or t.genre == genre)
            and (mood is None or t.mood == mood)
            and (min_energy is None or t.energy >= min_energy)
            and (max_energy is None or t.energy <= max_energy)
            and (not search or search.lower() in f"{t.title} {t.artist}".lower())
        ]
        tracks.sort(key=lambda t: t.id)
        page = paginate(tracks, limit, offset)
        page["items"] = [TrackResponse.model_validate(t) for t in page["items"]]
        return page

    def get(self, track_id: int) -> TrackResponse:
        return TrackResponse.model_validate(get_track(self.db, track_id))

    def create(self, data: TrackCreate) -> TrackResponse:
        self._ensure_unique(data.title, data.artist)
        tid = self.db.next_id("tracks")
        track = Track(id=tid, **data.model_dump())
        self.db.tracks[tid] = track
        return TrackResponse.model_validate(track)

    def update(self, track_id: int, data: TrackUpdate) -> TrackResponse:
        track = get_track(self.db, track_id)
        changes = data.model_dump(exclude_unset=True)
        title, artist = changes.get("title", track.title), changes.get("artist", track.artist)
        if (title.lower(), artist.lower()) != (track.title.lower(), track.artist.lower()):
            self._ensure_unique(title, artist)
        for key, value in changes.items():
            setattr(track, key, value)
        return TrackResponse.model_validate(track)

    def delete(self, track_id: int, force: bool) -> None:
        track = get_track(self.db, track_id)
        playing_in = [r.id for r in self.db.rooms.values() if r.current_track_id == track.id]
        if playing_in and not force:
            raise ConflictError(
                "Track is currently playing in one or more rooms. "
                "Use force=true to stop it everywhere and delete.",
                code="TRACK_IN_USE", details={"room_ids": playing_in},
            )
        for rid in playing_in:
            self.db.rooms[rid].current_track_id = None
        del self.db.tracks[track.id]

    def _ensure_unique(self, title: str, artist: str) -> None:
        for t in self.db.tracks.values():
            if t.title.lower() == title.lower() and t.artist.lower() == artist.lower():
                raise ConflictError(f"Track '{title}' by '{artist}' already exists",
                                    code="TRACK_ALREADY_EXISTS", details={"track_id": t.id})

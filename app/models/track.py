from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pg_enum, utcnow
from app.models.enums import Genre, Mood

if TYPE_CHECKING:
    from app.models.room import Room


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        CheckConstraint("energy >= 1 AND energy <= 10", name="energy_range"),
        CheckConstraint(
            "duration_seconds >= 30 AND duration_seconds <= 7200", name="duration_range"
        ),
        CheckConstraint("bpm IS NULL OR (bpm >= 40 AND bpm <= 220)", name="bpm_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    artist: Mapped[str] = mapped_column(String(100), nullable=False)
    genre: Mapped[Genre] = mapped_column(pg_enum(Genre, "genre_enum"), nullable=False, index=True)
    mood: Mapped[Mood] = mapped_column(pg_enum(Mood, "mood_enum"), nullable=False, index=True)
    energy: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    bpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    rooms: Mapped[list["Room"]] = relationship(back_populates="current_track")


Index(
    "uq_tracks_title_artist_lower",
    func.lower(Track.title),
    func.lower(Track.artist),
    unique=True,
)

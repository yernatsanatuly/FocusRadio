from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pg_enum, utcnow
from app.models.enums import Genre

if TYPE_CHECKING:
    from app.models.session import FocusSession
    from app.models.track import Track
    from app.models.user import User


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("capacity >= 2 AND capacity <= 50", name="capacity_range"),
        CheckConstraint(
            "(is_private = true AND access_code IS NOT NULL) "
            "OR (is_private = false AND access_code IS NULL)",
            name="privacy_access_code_consistency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default="8")
    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    access_code: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    preferred_genre: Mapped[Optional[Genre]] = mapped_column(
        pg_enum(Genre, "genre_enum"), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, default=list, server_default=text("'{}'::varchar[]")
    )
    current_track_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="owned_rooms")
    current_track: Mapped[Optional["Track"]] = relationship(back_populates="rooms")
    members: Mapped[list["RoomMember"]] = relationship(
        back_populates="room",
        order_by="RoomMember.joined_at, RoomMember.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list["FocusSession"]] = relationship(back_populates="room")


Index("uq_rooms_name_lower", func.lower(Room.name), unique=True)


class RoomMember(Base):
    __tablename__ = "room_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    room: Mapped["Room"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="room_membership")

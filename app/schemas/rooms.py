from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import Genre, Mood
from app.schemas.tracks import TrackResponse

ACCESS_CODE_PATTERN = r"^[A-Za-z0-9]{4,12}$"


def _normalize_tags(tags: Optional[list[str]]) -> Optional[list[str]]:
    if tags is None:
        return None
    cleaned: list[str] = []
    for tag in tags:
        t = tag.strip().lower()
        if not 2 <= len(t) <= 20:
            raise ValueError("Each tag must be 2-20 characters long")
        if t not in cleaned:
            cleaned.append(t)
    return cleaned


class RoomCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"example": {
            "name": "Night Owls Coding",
            "description": "Late-night deep work for developers",
            "owner_id": 2,
            "capacity": 5,
            "is_private": True,
            "access_code": "owl2026",
            "preferred_genre": "synthwave",
            "tags": ["coding", "night"],
        }},
    )

    name: str = Field(min_length=3, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    owner_id: int = Field(ge=1)
    capacity: int = Field(default=8, ge=2, le=50)
    is_private: bool = False
    access_code: Optional[str] = Field(default=None, pattern=ACCESS_CODE_PATTERN,
                                       description="Required for private rooms (4-12 letters/digits)")
    preferred_genre: Optional[Genre] = None
    tags: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        return _normalize_tags(v)

    @model_validator(mode="after")
    def check_privacy(self) -> "RoomCreate":
        if self.is_private and not self.access_code:
            raise ValueError("Private rooms require an access_code")
        if not self.is_private and self.access_code:
            raise ValueError("Public rooms must not have an access_code")
        return self


class RoomUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"capacity": 12,
                                                             "tags": ["study", "exam"]}})

    name: Optional[str] = Field(default=None, min_length=3, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    capacity: Optional[int] = Field(default=None, ge=2, le=50)
    is_private: Optional[bool] = None
    access_code: Optional[str] = Field(default=None, pattern=ACCESS_CODE_PATTERN)
    preferred_genre: Optional[Genre] = None
    tags: Optional[list[str]] = Field(default=None, max_length=5)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        return _normalize_tags(v)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "RoomUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for name in self.model_fields_set & {"name", "capacity", "is_private", "tags"}:
            if getattr(self, name) is None:
                raise ValueError(f"'{name}' cannot be null")
        return self


class RoomResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    owner_id: int
    capacity: int
    member_count: int
    available_spots: int
    is_private: bool
    preferred_genre: Optional[Genre]
    tags: list[str]
    current_track: Optional[TrackResponse]
    created_at: datetime


class JoinRoomRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"user_id": 2, "access_code": None}})

    user_id: int = Field(ge=1)
    access_code: Optional[str] = Field(default=None, max_length=12)


class SetTrackRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"track_id": 4}})

    track_id: int = Field(ge=1)


class RoomMember(BaseModel):
    user_id: int
    username: str
    display_name: str
    level: int
    is_owner: bool
    focus_status: Literal["focusing", "paused", "idle"]
    session_id: Optional[int]
    remaining_seconds: Optional[int]


class RoomActivity(BaseModel):
    room_id: int
    member_count: int
    focusing: int
    paused: int
    idle: int
    room_phase: Literal["focus", "break"] = Field(
        description="'focus' when at least half of the members are focusing")
    members: list[RoomMember]


class TrackRecommendation(BaseModel):
    room_id: int
    room_phase: Literal["focus", "break"]
    target_mood: Mood
    max_energy: int
    reason: str
    tracks: list[TrackResponse]


class LeaveRoomResult(BaseModel):
    room_id: int
    user_id: int
    kicked: bool = Field(description="True if the member was removed by the owner")
    new_owner_id: Optional[int] = Field(description="Set when ownership was transferred")
    room_deleted: bool = Field(description="True if the room became empty and was closed")

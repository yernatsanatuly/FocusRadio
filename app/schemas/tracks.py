from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Genre, Mood


class TrackCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"example": {
            "title": "Library Rain", "artist": "LoFi Owl", "genre": "lofi",
            "mood": "focus", "energy": 3, "duration_seconds": 190, "bpm": 75,
        }},
    )

    title: str = Field(min_length=1, max_length=100)
    artist: str = Field(min_length=1, max_length=100)
    genre: Genre
    mood: Mood
    energy: int = Field(ge=1, le=10, description="1 = very calm, 10 = very energetic")
    duration_seconds: int = Field(ge=30, le=7200)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)


class TrackUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"energy": 4, "mood": "calm"}})

    title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    artist: Optional[str] = Field(default=None, min_length=1, max_length=100)
    genre: Optional[Genre] = None
    mood: Optional[Mood] = None
    energy: Optional[int] = Field(default=None, ge=1, le=10)
    duration_seconds: Optional[int] = Field(default=None, ge=30, le=7200)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "TrackUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for name in self.model_fields_set - {"bpm"}:
            if getattr(self, name) is None:
                raise ValueError(f"'{name}' cannot be null")
        return self


class TrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    artist: str
    genre: Genre
    mood: Mood
    energy: int
    duration_seconds: int
    bpm: Optional[int]
    created_at: datetime

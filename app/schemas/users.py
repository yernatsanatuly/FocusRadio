from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMAIL_PATTERN = r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"


class UserCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "username": "dana_codes",
                "display_name": "Dana",
                "email": "dana@example.com",
                "bio": "CS student, pomodoro addict",
            }
        },
    )

    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$",
                          description="Unique login: letters, digits and underscores")
    display_name: str = Field(min_length=1, max_length=50)
    email: str = Field(max_length=120, pattern=EMAIL_PATTERN)
    bio: Optional[str] = Field(default=None, max_length=200)

    @field_validator("username", "email")
    @classmethod
    def lowercase(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"display_name": "Dana K.",
                                                             "bio": "Now deep-working daily"}})

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    email: Optional[str] = Field(default=None, max_length=120, pattern=EMAIL_PATTERN)
    bio: Optional[str] = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def lowercase(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if v else v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self


class LevelInfo(BaseModel):
    level: int
    title: str
    xp: int
    xp_current_level: int = Field(description="XP threshold of the current level")
    xp_next_level: int = Field(description="XP threshold of the next level")
    progress_percent: float


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    email: str
    bio: Optional[str]
    xp: int
    level: int
    level_title: str
    current_streak: int
    longest_streak: int
    total_focus_minutes: int
    completed_sessions: int
    completed_tasks: int
    current_room_id: Optional[int]
    created_at: datetime


class AchievementResponse(BaseModel):
    code: str
    title: str
    description: str
    unlocked: bool
    unlocked_at: Optional[datetime] = None


class UserStats(BaseModel):
    user_id: int
    level: LevelInfo
    current_streak: int
    longest_streak: int
    total_focus_minutes: int
    completed_sessions: int
    sessions_by_status: dict[str, int]
    completion_rate_percent: float = Field(
        description="Share of finished sessions that reached the full planned time")
    average_session_minutes: float
    favorite_mode: Optional[str]
    tasks_open: int
    tasks_done: int
    achievements_unlocked: int
    achievements_total: int
    active_session_id: Optional[int]

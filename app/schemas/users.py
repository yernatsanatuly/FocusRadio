from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.security import MAX_BCRYPT_PASSWORD_BYTES
from app.models.enums import UserRole

EMAIL_PATTERN = r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"
USERNAME_PATTERN = r"^[A-Za-z0-9_]+$"


def validate_password_bytes(password: str) -> str:
    if len(password.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_BCRYPT_PASSWORD_BYTES} bytes")
    return password


class UserCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "dana_codes",
                "display_name": "Dana",
                "email": "dana@example.com",
                "password": "securepassword123",
                "role": "user",
                "bio": "CS student, pomodoro addict",
            }
        },
    )

    username: str = Field(
        min_length=3,
        max_length=30,
        pattern=USERNAME_PATTERN,
        description="Unique login: letters, digits and underscores",
    )
    display_name: str = Field(min_length=1, max_length=50)
    email: str = Field(max_length=120, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=72)
    role: UserRole = UserRole.USER
    bio: Optional[str] = Field(default=None, max_length=200)

    @field_validator("username", "email", mode="before")
    @classmethod
    def strip_and_lowercase(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("display_name", "bio", mode="before")
    @classmethod
    def strip_text(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("password")
    @classmethod
    def check_password_length(cls, v: str) -> str:
        return validate_password_bytes(v)


class UserUpdate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {"display_name": "Dana K.", "bio": "Now deep-working daily"}
        },
    )

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


class UserRoleUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"role": "admin"}})

    role: UserRole


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
    role: UserRole
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
        description="Share of finished sessions that reached the full planned time"
    )
    average_session_minutes: float
    favorite_mode: Optional[str]
    tasks_open: int
    tasks_done: int
    achievements_unlocked: int
    achievements_total: int
    active_session_id: Optional[int]

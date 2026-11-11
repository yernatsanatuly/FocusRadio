"""Focus session (timer) schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SessionMode, SessionStatus
from app.schemas.users import AchievementResponse, LevelInfo


class SessionCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"examples": [
            {"user_id": 1, "mode": "pomodoro", "task_id": None, "notes": "Chapter 3"},
            {"user_id": 2, "mode": "custom", "focus_minutes": 2, "break_minutes": 1},
        ]},
    )

    user_id: int = Field(ge=1)
    mode: SessionMode = SessionMode.POMODORO
    focus_minutes: Optional[int] = Field(default=None, ge=1, le=180,
                                         description="Only for mode=custom")
    break_minutes: Optional[int] = Field(default=None, ge=0, le=60,
                                         description="Only for mode=custom")
    task_id: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def check_mode(self) -> "SessionCreate":
        if self.mode == SessionMode.CUSTOM:
            if self.focus_minutes is None:
                raise ValueError("focus_minutes is required for custom mode")
            if self.break_minutes is not None and self.break_minutes > self.focus_minutes:
                raise ValueError("break_minutes cannot be longer than focus_minutes")
        elif self.focus_minutes is not None or self.break_minutes is not None:
            raise ValueError(
                f"Durations are fixed for preset mode '{self.mode.value}'; use mode=custom"
            )
        return self


class SessionUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"notes": "Solved 5 tasks"}})

    notes: Optional[str] = Field(default=None, max_length=300)
    task_id: Optional[int] = Field(default=None, ge=1,
                                   description="Attach/replace task (only while running)")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "SessionUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self


class SessionResponse(BaseModel):
    id: int
    user_id: int
    room_id: Optional[int]
    task_id: Optional[int]
    mode: SessionMode
    status: SessionStatus
    focus_minutes: int
    break_minutes: int
    started_at: datetime
    ended_at: Optional[datetime]
    pause_count: int
    paused_seconds: int
    elapsed_focus_seconds: int
    remaining_seconds: int
    progress_percent: float
    is_time_up: bool = Field(description="Planned focus time reached; session can be completed")
    xp_earned: int
    notes: Optional[str]


class SessionFinishResult(BaseModel):
    session: SessionResponse
    xp_breakdown: dict[str, int]
    total_xp: int
    level: LevelInfo
    leveled_up: bool
    current_streak: int
    new_achievements: list[AchievementResponse]
    suggested_break_minutes: int

"""Personal task (to-do) schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TaskPriority, TaskStatus
from app.schemas.users import AchievementResponse


class TaskCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"example": {
            "user_id": 1, "title": "Finish FastAPI assignment",
            "description": "Routers, schemas, services", "priority": "high",
            "estimated_pomodoros": 4,
        }},
    )

    user_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    priority: TaskPriority = TaskPriority.MEDIUM
    estimated_pomodoros: int = Field(default=1, ge=1, le=20)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"status": "done"}})

    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    priority: Optional[TaskPriority] = None
    estimated_pomodoros: Optional[int] = Field(default=None, ge=1, le=20)
    status: Optional[TaskStatus] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "TaskUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for name in self.model_fields_set - {"description"}:
            if getattr(self, name) is None:
                raise ValueError(f"'{name}' cannot be null")
        return self


class TaskResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str]
    priority: TaskPriority
    status: TaskStatus
    estimated_pomodoros: int
    completed_pomodoros: int
    progress_percent: float
    created_at: datetime
    completed_at: Optional[datetime]


class TaskUpdateResult(BaseModel):
    task: TaskResponse
    new_achievements: list[AchievementResponse] = []

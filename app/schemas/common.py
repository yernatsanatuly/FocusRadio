from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Total number of items matching the filters")
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    code: str = Field(examples=["ROOM_FULL"])
    message: str = Field(examples=["Room is full"])
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class MessageResponse(BaseModel):
    message: str

def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        400: "Bad request",
        403: "Action not allowed for this user",
        404: "Resource not found",
        409: "Conflict with the current state of a resource",
        422: "Validation error or business rule violation",
    }
    return {c: {"model": ErrorResponse, "description": descriptions.get(c, "Error")} for c in codes}

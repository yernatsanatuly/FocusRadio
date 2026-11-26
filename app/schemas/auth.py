from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.users import (
    EMAIL_PATTERN,
    USERNAME_PATTERN,
    UserResponse,
    validate_password_bytes,
)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "dana_codes",
                "display_name": "Dana",
                "email": "dana@example.com",
                "password": "securepassword123",
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
    password: str = Field(
        min_length=8,
        max_length=72,
        description="Plain-text password (at least 8 characters; stored as a bcrypt hash)",
    )
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


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"username": "alice", "password": "password123"},
                {"email": "bob@focusradio.dev", "password": "password123"},
            ]
        },
    )

    username: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Username or email address",
    )
    email: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Email address (alternative to username)",
    )
    password: str = Field(min_length=1, max_length=72)

    @field_validator("username", "email", mode="before")
    @classmethod
    def strip_and_lowercase(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = v.strip().lower()
            return cleaned or None
        return v

    @model_validator(mode="after")
    def require_identifier(self) -> "LoginRequest":
        if not self.username and not self.email:
            raise ValueError("Provide either 'username' or 'email'")
        return self

    @property
    def identifier(self) -> str:
        return self.username or self.email or ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    user: UserResponse

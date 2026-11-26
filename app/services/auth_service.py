"""User registration and JWT authentication service."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.users import UserResponse
from app.services.user_service import to_response


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, data: RegisterRequest) -> UserResponse:
        if self.db.scalar(select(User.id).where(User.username == data.username)) is not None:
            raise ConflictError(
                f"Username '{data.username}' is already taken",
                code="USERNAME_TAKEN",
            )
        if self.db.scalar(select(User.id).where(User.email == data.email)) is not None:
            raise ConflictError(
                f"Email '{data.email}' is already registered",
                code="EMAIL_TAKEN",
            )

        user = User(
            username=data.username,
            display_name=data.display_name,
            email=data.email,
            hashed_password=hash_password(data.password),
            role=UserRole.USER,
            bio=data.bio,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return to_response(user)

    def login(self, data: LoginRequest) -> TokenResponse:
        ident = data.identifier
        user = self.db.scalar(
            select(User).where(or_(User.username == ident, User.email == ident))
        )
        if user is None or not verify_password(data.password, user.hashed_password):
            raise UnauthorizedError(
                "Invalid username/email or password",
                code="INVALID_CREDENTIALS",
            )

        token, expires_in = create_access_token(user.id, user.role)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in,
            user=to_response(user),
        )

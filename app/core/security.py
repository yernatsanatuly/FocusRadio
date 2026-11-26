"""Password hashing (bcrypt) and JWT access token utilities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt

from app.config import settings
from app.core.exceptions import UnauthorizedError
from app.models.enums import UserRole

MAX_BCRYPT_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a plain-text password with a random bcrypt salt."""
    raw = password.encode("utf-8")
    if len(raw) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_BCRYPT_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    if not plain_password or not hashed_password or not hashed_password.startswith("$2"):
        return False
    raw = plain_password.encode("utf-8")
    if len(raw) > MAX_BCRYPT_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    user_id: int,
    role: UserRole,
    *,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, int]:
    """Generate a signed JWT access token and return (token, expires_in_seconds)."""
    delta = expires_delta if expires_delta is not None else timedelta(
        minutes=settings.access_token_expire_minutes
    )
    now = datetime.now(timezone.utc)
    expire = now + delta
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, max(0, int(delta.total_seconds()))


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate signature, expiration, and claims of a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token", code="INVALID_TOKEN") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type", code="INVALID_TOKEN")

    return payload

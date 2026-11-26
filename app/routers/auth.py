from fastapi import APIRouter, status

from app.core.dependencies import Auth, CurrentUser
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.common import error_responses
from app.schemas.users import UserResponse
from app.services.user_service import to_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(409, 422),
    summary="Register a new user account",
)
def register(data: RegisterRequest, service: Auth):
    return service.register(data)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=error_responses(401, 422),
    summary="Authenticate and receive a JWT Bearer access token",
)
def login(data: LoginRequest, service: Auth):
    return service.login(data)


@router.get(
    "/me",
    response_model=UserResponse,
    responses=error_responses(401),
    summary="Get the currently authenticated user's profile",
)
def me(current_user: CurrentUser):
    return to_response(current_user)

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import require_current_user
from app.db.models import User
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request) -> AuthResponse:
    return await request.app.state.auth_service.register(payload)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request) -> AuthResponse:
    return await request.app.state.auth_service.login(payload)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest, request: Request) -> ForgotPasswordResponse:
    return await request.app.state.auth_service.request_password_reset(payload)


@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(payload: ResetPasswordRequest, request: Request) -> AuthResponse:
    return await request.app.state.auth_service.reset_password(payload)


@router.get("/me", response_model=UserResponse)
async def current_user(current_user: User = Depends(require_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        created_at=current_user.created_at,
    )

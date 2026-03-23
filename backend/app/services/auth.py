from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
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

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class AuthService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings

    def _user_to_response(self, user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at,
        )

    def _create_access_token(self, user_id: str) -> str:
        expires_at = datetime.now(UTC) + timedelta(minutes=self._settings.access_token_expire_minutes)
        payload = {"sub": user_id, "exp": expires_at}
        return jwt.encode(
            payload,
            self._settings.auth_secret_key,
            algorithm=self._settings.auth_algorithm,
        )

    def _create_password_reset_token(self, user_id: str) -> str:
        expires_at = datetime.now(UTC) + timedelta(
            minutes=self._settings.password_reset_token_expire_minutes,
        )
        payload = {"sub": user_id, "exp": expires_at, "scope": "password_reset"}
        return jwt.encode(
            payload,
            self._settings.auth_secret_key,
            algorithm=self._settings.auth_algorithm,
        )

    def _verify_password_reset_token(self, token: str) -> str | None:
        try:
            payload = jwt.decode(
                token,
                self._settings.auth_secret_key,
                algorithms=[self._settings.auth_algorithm],
            )
        except jwt.PyJWTError:
            return None

        if payload.get("scope") != "password_reset":
            return None

        user_id = payload.get("sub")
        if not isinstance(user_id, str):
            return None
        return user_id

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def _verify_password(self, plain_password: str, password_hash: str) -> bool:
        if password_hash.startswith("$pbkdf2-sha256$"):
            return pwd_context.verify(plain_password, password_hash)

        if password_hash.startswith("$2"):
            try:
                return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
            except ValueError:
                return False

        return False

    async def register(self, payload: RegisterRequest) -> AuthResponse:
        normalized_email = payload.email.lower().strip()
        user = User(
            id=str(uuid4()),
            email=normalized_email,
            full_name=payload.full_name.strip(),
            password_hash=self._hash_password(payload.password),
        )

        async with self._session_factory() as session:
            session.add(user)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with that email already exists.",
                ) from None
            await session.refresh(user)

        return AuthResponse(access_token=self._create_access_token(user.id), user=self._user_to_response(user))

    async def login(self, payload: LoginRequest) -> AuthResponse:
        normalized_email = payload.email.lower().strip()

        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.email == normalized_email))
            user = result.scalar_one_or_none()

        if user is None or not self._verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        return AuthResponse(access_token=self._create_access_token(user.id), user=self._user_to_response(user))

    async def request_password_reset(
        self,
        payload: ForgotPasswordRequest,
    ) -> ForgotPasswordResponse:
        normalized_email = payload.email.lower().strip()

        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.email == normalized_email))
            user = result.scalar_one_or_none()

        response = ForgotPasswordResponse(
            message="If an account exists for that email, a reset link is ready.",
        )
        if user is None:
            return response

        reset_token = self._create_password_reset_token(user.id)
        if self._settings.environment != "production":
            frontend_base = self._settings.public_frontend_url.rstrip("/")
            response.reset_token = reset_token
            response.reset_url = f"{frontend_base}/auth?reset_token={reset_token}"
        return response

    async def reset_password(self, payload: ResetPasswordRequest) -> AuthResponse:
        user_id = self._verify_password_reset_token(payload.token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token.",
            )

        async with self._session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired reset token.",
                )
            user.password_hash = self._hash_password(payload.new_password)
            await session.commit()
            await session.refresh(user)

        return AuthResponse(access_token=self._create_access_token(user.id), user=self._user_to_response(user))

    async def get_user_from_token(self, token: str) -> User | None:
        try:
            payload = jwt.decode(
                token,
                self._settings.auth_secret_key,
                algorithms=[self._settings.auth_algorithm],
            )
        except jwt.PyJWTError:
            return None

        user_id = payload.get("sub")
        if not isinstance(user_id, str):
            return None

        async with self._session_factory() as session:
            return await session.get(User, user_id)

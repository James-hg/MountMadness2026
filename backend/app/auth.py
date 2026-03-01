from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field

from .config import settings
from .database import get_db_connection

http_bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_TTL_MINUTES = 15
REFRESH_TOKEN_TTL_DAYS = 7


class AuthUserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    created_at: datetime


class AuthTokensResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: AuthUserResponse


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


def _issue_token(user_id: UUID, token_type: str, ttl: timedelta) -> tuple[str, UUID, datetime]:
    now = datetime.now(timezone.utc)
    jti = uuid4()
    exp_at = now + ttl
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(jti),
        "iat": int(now.timestamp()),
        "exp": int(exp_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, exp_at


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _decode_token(token: str, *, expected_type: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "jti"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")

    return payload


async def _fetch_user(connection: AsyncConnection, user_id: UUID) -> dict | None:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, email, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        return await cursor.fetchone()


async def _save_refresh_token(
    connection: AsyncConnection,
    *,
    user_id: UUID,
    refresh_token: str,
    jti: UUID,
    expires_at: datetime,
    request: Request,
) -> None:
    token_hash = _hash_token(refresh_token)
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else None

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO auth_refresh_tokens (user_id, jti, token_hash, expires_at, user_agent, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, jti, token_hash, expires_at, user_agent, client_ip),
        )


async def _issue_auth_tokens(
    connection: AsyncConnection,
    *,
    user: AuthUserResponse,
    request: Request,
) -> AuthTokensResponse:
    access_token, _, _ = _issue_token(
        user.id,
        "access",
        timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    )
    refresh_token, refresh_jti, refresh_expires_at = _issue_token(
        user.id,
        "refresh",
        timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    )

    await _save_refresh_token(
        connection,
        user_id=user.id,
        refresh_token=refresh_token,
        jti=refresh_jti,
        expires_at=refresh_expires_at,
        request=request,
    )

    return AuthTokensResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user,
    )


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise HTTPException(status_code=422, detail="Invalid email")
    return normalized


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> UUID:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = credentials.credentials

    payload = _decode_token(token, expected_type="access")

    subject = payload.get("sub")
    try:
        return UUID(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401, detail="Invalid token subject") from exc


@router.post("/register", response_model=AuthTokensResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthTokensResponse:
    email = _normalize_email(payload.email)
    name = payload.name.strip()

    if not name:
        raise HTTPException(status_code=422, detail="Name is required")

    async with connection.cursor() as cursor:
        try:
            await cursor.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, crypt(%s, gen_salt('bf', 12)))
                RETURNING id, name, email, created_at
                """,
                (name, email, payload.password),
            )
        except UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="An account with this email already exists") from exc

        user_row = await cursor.fetchone()

    user = AuthUserResponse.model_validate(user_row)
    return await _issue_auth_tokens(connection, user=user, request=request)


@router.post("/login", response_model=AuthTokensResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthTokensResponse:
    email = _normalize_email(payload.email)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, email, created_at
            FROM users
            WHERE LOWER(email) = LOWER(%s)
              AND password_hash = crypt(%s, password_hash)
            """,
            (email, payload.password),
        )
        user_row = await cursor.fetchone()

    if user_row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = AuthUserResponse.model_validate(user_row)
    return await _issue_auth_tokens(connection, user=user, request=request)


@router.post("/refresh", response_model=AuthTokensResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthTokensResponse:
    decoded = _decode_token(payload.refresh_token, expected_type="refresh")

    subject = decoded.get("sub")
    jti_raw = decoded.get("jti")
    try:
        user_id = UUID(subject)
        refresh_jti = UUID(jti_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token subject") from exc

    now = datetime.now(timezone.utc)
    provided_hash = _hash_token(payload.refresh_token)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT token_hash, expires_at, revoked_at
            FROM auth_refresh_tokens
            WHERE user_id = %s AND jti = %s
            """,
            (user_id, refresh_jti),
        )
        token_row = await cursor.fetchone()

    if token_row is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_row["revoked_at"] is not None or token_row["expires_at"] <= now:
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")

    if not hmac.compare_digest(token_row["token_hash"], provided_hash):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_row = await _fetch_user(connection, user_id)
    if user_row is None:
        raise HTTPException(status_code=401, detail="User not found")

    user = AuthUserResponse.model_validate(user_row)
    tokens = await _issue_auth_tokens(connection, user=user, request=request)
    new_decoded = _decode_token(tokens.refresh_token, expected_type="refresh")
    new_jti_raw = new_decoded.get("jti")

    try:
        new_jti = UUID(new_jti_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Failed to rotate refresh token") from exc

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE auth_refresh_tokens
            SET revoked_at = %s, replaced_by_jti = %s
            WHERE user_id = %s AND jti = %s AND revoked_at IS NULL
            """,
            (now, new_jti, user_id, refresh_jti),
        )

    return tokens


@router.get("/me", response_model=AuthUserResponse)
async def me(
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthUserResponse:
    user_row = await _fetch_user(connection, user_id)

    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return AuthUserResponse.model_validate(user_row)


@router.patch("/me", response_model=AuthUserResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthUserResponse:
    if payload.name is None and payload.email is None:
        raise HTTPException(status_code=422, detail="No fields to update")

    updates = []
    params = []

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name is required")
        updates.append("name = %s")
        params.append(name)

    if payload.email is not None:
        email = _normalize_email(payload.email)
        updates.append("email = %s")
        params.append(email)

    params.append(user_id)

    async with connection.cursor() as cursor:
        try:
            await cursor.execute(
                f"""
                UPDATE users
                SET {', '.join(updates)}
                WHERE id = %s
                RETURNING id, name, email, created_at
                """,
                tuple(params),
            )
        except UniqueViolation as exc:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists",
            ) from exc

        user_row = await cursor.fetchone()

    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return AuthUserResponse.model_validate(user_row)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> dict:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id FROM users
            WHERE id = %s
              AND password_hash = crypt(%s, password_hash)
            """,
            (user_id, payload.current_password),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=403, detail="Current password is incorrect")

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE users
            SET password_hash = crypt(%s, gen_salt('bf', 12))
            WHERE id = %s
            """,
            (payload.new_password, user_id),
        )

    return {"message": "Password updated successfully"}


@router.post("/logout", status_code=204)
async def logout(
    payload: LogoutRequest | None = None,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> Response:
    if payload and payload.refresh_token:
        decoded = _decode_token(payload.refresh_token, expected_type="refresh")
        jti_raw = decoded.get("jti")

        try:
            subject = UUID(decoded.get("sub"))
            refresh_jti = UUID(jti_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

        if subject != user_id:
            raise HTTPException(status_code=403, detail="Refresh token does not belong to user")

        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE auth_refresh_tokens
                SET revoked_at = %s
                WHERE user_id = %s AND jti = %s AND revoked_at IS NULL
                """,
                (datetime.now(timezone.utc), user_id, refresh_jti),
            )

    return Response(status_code=204)

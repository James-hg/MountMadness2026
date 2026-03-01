from uuid import UUID

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
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


def _issue_token(user_id: UUID, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


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

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    subject = payload.get("sub")
    try:
        return UUID(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401, detail="Invalid token subject") from exc


@router.post("/register", response_model=AuthTokensResponse, status_code=201)
async def register(
    payload: RegisterRequest,
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
    return AuthTokensResponse(
        access_token=_issue_token(user.id, "access", timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)),
        refresh_token=_issue_token(user.id, "refresh", timedelta(days=REFRESH_TOKEN_TTL_DAYS)),
        user=user,
    )


@router.post("/login", response_model=AuthTokensResponse)
async def login(
    payload: LoginRequest,
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
    return AuthTokensResponse(
        access_token=_issue_token(user.id, "access", timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)),
        refresh_token=_issue_token(user.id, "refresh", timedelta(days=REFRESH_TOKEN_TTL_DAYS)),
        user=user,
    )


@router.get("/me", response_model=AuthUserResponse)
async def me(
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthUserResponse:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, email, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        user_row = await cursor.fetchone()

    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return AuthUserResponse.model_validate(user_row)


@router.post("/logout", status_code=204)
async def logout(_: UUID = Depends(get_current_user_id)) -> Response:
    return Response(status_code=204)

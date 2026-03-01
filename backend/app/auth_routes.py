from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from pydantic import BaseModel, EmailStr

from .config import settings
from .database import get_db_connection

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str


class AuthResponse(BaseModel):
    access_token: str
    user: UserOut


def _create_access_token(user_id: UUID) -> str:
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthResponse:
    async with connection.cursor() as cur:
        await cur.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE LOWER(email) = LOWER(%s)
              AND password_hash = crypt(%s, password_hash)
            """,
            (body.email, body.password),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_access_token(row["id"])
    return AuthResponse(
        access_token=token,
        user=UserOut(id=str(row["id"]), name=row["name"], email=row["email"]),
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest,
    connection: AsyncConnection = Depends(get_db_connection),
) -> AuthResponse:
    async with connection.cursor() as cur:
        # Check if email already exists
        await cur.execute(
            "SELECT 1 FROM users WHERE LOWER(email) = LOWER(%s)",
            (body.email,),
        )
        if await cur.fetchone():
            raise HTTPException(status_code=409, detail="An account with this email already exists")

        await cur.execute(
            """
            INSERT INTO users (name, email, password_hash)
            VALUES (%s, LOWER(%s), crypt(%s, gen_salt('bf', 12)))
            RETURNING id, name, email
            """,
            (body.name, body.email, body.password),
        )
        row = await cur.fetchone()

    token = _create_access_token(row["id"])
    return AuthResponse(
        access_token=token,
        user=UserOut(id=str(row["id"]), name=row["name"], email=row["email"]),
    )

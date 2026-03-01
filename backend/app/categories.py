from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field
from typing import Optional, Literal

from .database import get_db_connection
from .auth import get_current_user_id
from .utils import slugify

router = APIRouter(prefix="/categories", tags=["categories"])

Kind = Literal["income", "expense"]


class CategoryOut(BaseModel):
    id: UUID
    user_id: UUID | None = None
    name: str
    slug: str
    kind: Kind
    icon: str | None = None
    color: str | None = None
    is_system: bool
    created_at: datetime


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Kind = "expense"
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=20)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=20)


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    kind: Kind | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    sql = """
    SELECT id, user_id, name, slug, kind, icon, color, is_system, created_at
    FROM categories
    WHERE (user_id IS NULL OR user_id = %s)
      AND (%s::text IS NULL OR kind = %s)
    ORDER BY is_system DESC, kind, name;
    """
    async with connection.cursor() as cur:
        await cur.execute(sql, (user_id, kind, kind))
        return await cur.fetchall()


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    try:
        slug = slugify(payload.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    sql = """
    INSERT INTO categories (user_id, name, slug, kind, icon, color, is_system)
    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
    RETURNING id, user_id, name, slug, kind, icon, color, is_system, created_at;
    """
    async with connection.cursor() as cur:
        try:
            await cur.execute(sql, (
                user_id, payload.name.strip(), slug, payload.kind,
                payload.icon.strip() if payload.icon else None,
                payload.color.strip() if payload.color else None,
            ))
            return await cur.fetchone()
        except UniqueViolation:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category with the same name already exists.")


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    new_slug = None
    if payload.name is not None:
        try:
            new_slug = slugify(payload.name)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    sql = """
    UPDATE categories
    SET name = COALESCE(%s, name),
        slug = COALESCE(%s, slug),
        icon = COALESCE(%s, icon),
        color = COALESCE(%s, color)
    WHERE id = %s AND user_id = %s AND is_system = FALSE
    RETURNING id, user_id, name, slug, kind, icon, color, is_system, created_at;
    """
    async with connection.cursor() as cur:
        try:
            await cur.execute(sql, (
                payload.name.strip() if payload.name else None,
                new_slug,
                payload.icon.strip() if payload.icon else None,
                payload.color.strip() if payload.color else None,
                category_id, user_id,
            ))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or cannot be updated.")
            return row
        except UniqueViolation:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category with the same name already exists.")


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    sql = """
    DELETE FROM categories
    WHERE id = %s AND user_id = %s AND is_system = FALSE
    RETURNING id;
    """
    async with connection.cursor() as cur:
        await cur.execute(sql, (category_id, user_id))
        if not await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or cannot be deleted.")
    return None

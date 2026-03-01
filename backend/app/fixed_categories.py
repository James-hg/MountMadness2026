from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from pydantic import BaseModel

from .database import get_db_connection
from .auth import get_current_user_id

router = APIRouter(prefix="/fixed-categories", tags=["fixed-categories"])


class FixedCategoryOut(BaseModel):
    category_id: UUID
    category_name: str


class FixedCategoryCreate(BaseModel):
    category_id: UUID


@router.get("", response_model=list[FixedCategoryOut])
async def list_fixed_categories(
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    sql = """
    SELECT ufc.category_id, c.name AS category_name
    FROM user_fixed_categories ufc
    JOIN categories c ON c.id = ufc.category_id
    WHERE ufc.user_id = %s
    ORDER BY c.name ASC;
    """
    async with connection.cursor() as cur:
        await cur.execute(sql, (user_id,))
        return await cur.fetchall()


@router.post("", response_model=FixedCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_fixed_category(
    payload: FixedCategoryCreate,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    async with connection.cursor() as cur:
        await cur.execute(
            """
            SELECT id, name FROM categories
            WHERE id = %s AND (is_system = TRUE OR user_id = %s)
            """,
            (payload.category_id, user_id),
        )
        cat = await cur.fetchone()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")

        await cur.execute(
            """
            INSERT INTO user_fixed_categories (user_id, category_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, category_id) DO NOTHING
            """,
            (user_id, payload.category_id),
        )

    return FixedCategoryOut(category_id=cat["id"], category_name=cat["name"])


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fixed_category(
    category_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    async with connection.cursor() as cur:
        await cur.execute(
            "DELETE FROM user_fixed_categories WHERE user_id = %s AND category_id = %s RETURNING id",
            (user_id, category_id),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Fixed category not found")
    return None

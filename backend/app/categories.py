from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
import psycopg2

from app.database import get_db_connection
from app.auth import get_current_user_id
from app.utils import slugify

router = APIRouter(prefix="/categories", tags=["categories"])

Kind = Literal["income", "expense"]


"""Category models for request and response validation. Map with the database schema for categories table."""
class CategoryOut(BaseModel):
    id: int
    user_id: Optional[int]
    name: str
    slug: str
    kind: Kind
    icon: Optional[str] = None
    color: Optional[str] = None
    is_system: bool
    created_at: str 

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Kind = "expense"
    icon: Optional[str] = Field(default=None, max_length=40)
    color: Optional[str] = Field(default=None, max_length=20)

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    icon: Optional[str] = Field(default=None, max_length=40)
    color: Optional[str] = Field(default=None, max_length=20)

@router.get("", response_model=list[CategoryOut])
def list_categories(
    kind: Optional[Kind] = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """
    Returns: (system categories) + (this user's categories)
    """
    sql = """
    SELECT id, user_id, name, slug, kind, icon, color, is_system, created_at
    FROM categories
    WHERE (user_id IS NULL OR user_id = %s)
      AND (%s::text IS NULL OR kind = %s)
    ORDER BY is_system DESC, kind, name;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, kind, kind))
            return cur.fetchall()
        
@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, user_id: str = Depends(get_current_user_id)):
    """
    Create user category. System categories cannot be created by users.
    Slug is generated server-side and must satisfy chk_categories_slug.
    Uniqueness enforced by ux_categories_user_kind_slug.
    """

    try: 
        slug = slugify(payload.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    sql = """
    INSERT INTO categories (user_id, name, slug, kind, icon, color, is_system)
    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
    RETURNING id, user_id, name, slug, kind, icon, color, is_system, created_at;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, 
                            (user_id, payload.name.strip(), 
                             slug, 
                             payload.kind, 
                             payload.icon.strip() if payload.icon else None, 
                             payload.color.strip() if payload.color else None))
                return cur.fetchone()
            except psycopg2.errors.UniqueViolation:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category with the same name already exists.")
            

@router.put("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, payload: CategoryUpdate, user_id: str = Depends(get_current_user_id)):
    """
    Update user category. System categories cannot be updated by users.
    Slug is updated server-side if name is updated and must satisfy chk_categories_slug.
    Uniqueness enforced by ux_categories_user_kind_slug.
    """
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
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, 
                            (payload.name.strip() if payload.name else None, 
                             new_slug, 
                             payload.icon.strip() if payload.icon else None, 
                             payload.color.strip() if payload.color else None, 
                             category_id, user_id))
                updated_category = cur.fetchone()
                if not updated_category:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or cannot be updated.")
                return updated_category
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category with the same name already exists.")
    
@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, user_id: str = Depends(get_current_user_id)):
    """
    Delete user category. System categories cannot be deleted by users.
    """
    sql = """
    DELETE FROM categories
    WHERE id = %s AND user_id = %s AND is_system = FALSE
    RETURNING id;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (category_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found or cannot be deleted.")
    
    return None
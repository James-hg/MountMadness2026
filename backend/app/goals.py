"""Goals router with tool-friendly CRUD endpoints and computed planning fields."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
try:
    from pydantic import BaseModel, Field, field_serializer
except ImportError:  # pragma: no cover - local compatibility for pydantic v1 tests
    from pydantic import BaseModel, Field

    def field_serializer(*args, **kwargs):
        def _decorator(fn):
            return fn
        return _decorator

from .auth import get_current_user_id
from .database import get_db_connection
from .services.goals_service import (
    create_goal,
    delete_goal,
    get_goal,
    list_goals,
    update_goal,
)

GoalStatus = Literal["active", "paused", "completed", "cancelled"]
GoalStatusFilter = Literal["active", "paused", "completed", "cancelled", "all"]

router = APIRouter(prefix="/goals", tags=["goals"])


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _dump_model(model: BaseModel, **kwargs) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


class GoalCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    saved_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"), max_digits=12, decimal_places=2)
    deadline_date: date


class GoalUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: Decimal | None = Field(default=None, gt=Decimal("0"), max_digits=12, decimal_places=2)
    saved_amount: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=2)
    deadline_date: date | None = None
    status: GoalStatus | None = None


class GoalResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    deadline_date: date
    status: GoalStatus
    created_at: datetime
    updated_at: datetime
    remaining_amount: Decimal
    months_left: int
    recommended_monthly_save_amount: Decimal
    progress_pct: int
    on_track: bool | None
    shortfall_amount: Decimal

    @field_serializer(
        "target_amount",
        "saved_amount",
        "remaining_amount",
        "recommended_monthly_save_amount",
        "shortfall_amount",
    )
    def serialize_decimal(self, value: Decimal) -> str:
        return _money(value)


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal_endpoint(
    payload: GoalCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: Any = Depends(get_db_connection),
) -> GoalResponse:
    """
    Create one savings goal for the current user.

    Toolable action: `create_goal`.
    """
    try:
        result = await create_goal(
            connection,
            user_id,
            _dump_model(payload),
        )
        return GoalResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[GoalResponse])
async def list_goals_endpoint(
    status: GoalStatusFilter = Query(default="active"),
    user_id: UUID = Depends(get_current_user_id),
    connection: Any = Depends(get_db_connection),
) -> list[GoalResponse]:
    """
    List current user's goals, optionally filtered by status.

    Toolable action: `list_goals`.
    """
    try:
        rows = await list_goals(connection, user_id, status=status)
        return [GoalResponse(**row) for row in rows]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal_endpoint(
    goal_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: Any = Depends(get_db_connection),
) -> GoalResponse:
    """
    Get one goal with computed monthly plan/progress values.

    Toolable action: `get_goal_plan`.
    """
    try:
        row = await get_goal(connection, user_id, goal_id)
        return GoalResponse(**row)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal_endpoint(
    goal_id: UUID,
    payload: GoalUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: Any = Depends(get_db_connection),
) -> GoalResponse:
    """
    Partially update one goal.

    Toolable action: `update_goal_saved` (via `saved_amount`) and generic goal updates.
    """
    patch_data = _dump_model(payload, exclude_unset=True)
    if not patch_data:
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    try:
        row = await update_goal(connection, user_id, goal_id, patch_data)
        return GoalResponse(**row)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal_endpoint(
    goal_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: Any = Depends(get_db_connection),
):
    """Delete one goal for the current user."""
    try:
        await delete_goal(connection, user_id, goal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

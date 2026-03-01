"""Service layer for goal CRUD and computed planning metrics."""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    AsyncConnection = Any

GoalStatus = Literal["active", "paused", "completed", "cancelled"]
VALID_STATUSES: set[str] = {"active", "paused", "completed", "cancelled"}
MONEY_QUANT = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    """Normalize money values to NUMERIC(12,2) precision."""
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _ceil_to_cent(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_CEILING)


def _floor_to_cent(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_FLOOR)


def _normalize_amount(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return quantize_amount(value)


def _today() -> date:
    """Wrapper for deterministic tests."""
    return date.today()


def _created_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _validate_goal_state(goal_data: dict[str, Any], today: date) -> dict[str, Any]:
    """
    Validate merged goal state and apply status normalization.

    Rules:
    - target_amount > 0
    - 0 <= saved_amount <= target_amount
    - deadline_date strictly in the future
    - completed requires saved_amount >= target_amount
    - saved_amount >= target_amount always forces status=completed
    """
    name = str(goal_data.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")

    target_amount = _normalize_amount(Decimal(str(goal_data["target_amount"])))
    saved_amount = _normalize_amount(Decimal(str(goal_data["saved_amount"])))
    deadline_date = goal_data["deadline_date"]
    status = str(goal_data.get("status") or "active").strip().lower()

    if status not in VALID_STATUSES:
        raise ValueError("status must be one of: active, paused, completed, cancelled")

    if target_amount <= Decimal("0.00"):
        raise ValueError("target_amount must be greater than 0")

    if saved_amount < Decimal("0.00"):
        raise ValueError("saved_amount must be >= 0")

    if saved_amount > target_amount:
        raise ValueError("saved_amount must be <= target_amount")

    if deadline_date <= today:
        raise ValueError("deadline_date must be in the future")

    if status == "completed" and saved_amount < target_amount:
        raise ValueError("Cannot set status to completed before reaching target_amount")

    if saved_amount >= target_amount:
        status = "completed"

    return {
        "name": name,
        "target_amount": target_amount,
        "saved_amount": saved_amount,
        "deadline_date": deadline_date,
        "status": status,
    }


def _compute_goal_metrics(goal_row: dict[str, Any], today: date) -> dict[str, Any]:
    """Compute progress and monthly plan fields for one goal row."""
    target_amount = _normalize_amount(goal_row["target_amount"])
    saved_amount = _normalize_amount(goal_row["saved_amount"])
    deadline_date: date = goal_row["deadline_date"]
    status = str(goal_row["status"])
    created_at_date = _created_date(goal_row["created_at"])

    remaining_amount = quantize_amount(max(target_amount - saved_amount, Decimal("0.00")))

    days_left = max((deadline_date - today).days, 0)
    months_left = max(int(math.ceil(days_left / 30)) if days_left > 0 else 0, 0)

    if status != "active" or remaining_amount == Decimal("0.00"):
        recommended_monthly_save_amount = Decimal("0.00")
    elif months_left <= 0:
        recommended_monthly_save_amount = remaining_amount
    else:
        recommended_monthly_save_amount = _ceil_to_cent(remaining_amount / Decimal(months_left))

    progress_pct = 0
    if target_amount > Decimal("0.00"):
        progress_pct = int(((saved_amount / target_amount) * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))
        progress_pct = max(0, min(progress_pct, 100))

    expected_saved = Decimal("0.00")
    on_track: bool | None
    shortfall_amount: Decimal

    if status != "active":
        on_track = None
        shortfall_amount = Decimal("0.00")
    else:
        total_days = max((deadline_date - created_at_date).days, 1)
        elapsed_days = (today - created_at_date).days
        elapsed_days = max(0, min(elapsed_days, total_days))

        expected_saved = _floor_to_cent(target_amount * Decimal(elapsed_days) / Decimal(total_days))
        on_track = saved_amount >= expected_saved
        shortfall_amount = quantize_amount(max(expected_saved - saved_amount, Decimal("0.00")))

    return {
        **goal_row,
        "target_amount": target_amount,
        "saved_amount": saved_amount,
        "remaining_amount": remaining_amount,
        "months_left": months_left,
        "recommended_monthly_save_amount": quantize_amount(recommended_monthly_save_amount),
        "progress_pct": progress_pct,
        "on_track": on_track,
        "shortfall_amount": quantize_amount(shortfall_amount),
    }


async def _fetch_goal_row(
    connection: AsyncConnection,
    user_id: UUID,
    goal_id: UUID,
) -> dict[str, Any] | None:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, user_id, name, target_amount, saved_amount, deadline_date, status, created_at, updated_at
            FROM goals
            WHERE id = %s
              AND user_id = %s
            """,
            (goal_id, user_id),
        )
        return await cursor.fetchone()


async def create_goal(
    connection: AsyncConnection,
    user_id: UUID,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Create one goal for the authenticated user and return computed fields."""
    normalized = _validate_goal_state(
        {
            "name": data["name"],
            "target_amount": data["target_amount"],
            "saved_amount": data.get("saved_amount", Decimal("0.00")),
            "deadline_date": data["deadline_date"],
            "status": "active",
        },
        _today(),
    )

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO goals (user_id, name, target_amount, saved_amount, deadline_date, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, name, target_amount, saved_amount, deadline_date, status, created_at, updated_at
            """,
            (
                user_id,
                normalized["name"],
                normalized["target_amount"],
                normalized["saved_amount"],
                normalized["deadline_date"],
                normalized["status"],
            ),
        )
        row = await cursor.fetchone()

    return _compute_goal_metrics(row, _today())


async def list_goals(
    connection: AsyncConnection,
    user_id: UUID,
    status: str = "active",
) -> list[dict[str, Any]]:
    """List goals for the user, optionally filtered by one status."""
    query_status = status.strip().lower()
    if query_status != "all" and query_status not in VALID_STATUSES:
        raise ValueError("status must be one of: active, paused, completed, cancelled, all")

    sql = """
    SELECT id, user_id, name, target_amount, saved_amount, deadline_date, status, created_at, updated_at
    FROM goals
    WHERE user_id = %s
    """
    params: list[Any] = [user_id]

    if query_status != "all":
        sql += " AND status = %s"
        params.append(query_status)

    sql += " ORDER BY deadline_date ASC, created_at DESC"

    async with connection.cursor() as cursor:
        await cursor.execute(sql, tuple(params))
        rows = await cursor.fetchall()

    today = _today()
    return [_compute_goal_metrics(row, today) for row in rows]


async def get_goal(
    connection: AsyncConnection,
    user_id: UUID,
    goal_id: UUID,
) -> dict[str, Any]:
    """Fetch one user-scoped goal, including computed fields."""
    row = await _fetch_goal_row(connection, user_id, goal_id)
    if row is None:
        raise LookupError("Goal not found")

    return _compute_goal_metrics(row, _today())


async def update_goal(
    connection: AsyncConnection,
    user_id: UUID,
    goal_id: UUID,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Apply partial goal update and return computed fields."""
    existing = await _fetch_goal_row(connection, user_id, goal_id)
    if existing is None:
        raise LookupError("Goal not found")

    merged = {
        "name": patch.get("name", existing["name"]),
        "target_amount": patch.get("target_amount", existing["target_amount"]),
        "saved_amount": patch.get("saved_amount", existing["saved_amount"]),
        "deadline_date": patch.get("deadline_date", existing["deadline_date"]),
        "status": patch.get("status", existing["status"]),
    }

    normalized = _validate_goal_state(merged, _today())

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE goals
            SET name = %s,
                target_amount = %s,
                saved_amount = %s,
                deadline_date = %s,
                status = %s
            WHERE id = %s
              AND user_id = %s
            RETURNING id, user_id, name, target_amount, saved_amount, deadline_date, status, created_at, updated_at
            """,
            (
                normalized["name"],
                normalized["target_amount"],
                normalized["saved_amount"],
                normalized["deadline_date"],
                normalized["status"],
                goal_id,
                user_id,
            ),
        )
        row = await cursor.fetchone()

    if row is None:
        raise LookupError("Goal not found")

    return _compute_goal_metrics(row, _today())


async def delete_goal(
    connection: AsyncConnection,
    user_id: UUID,
    goal_id: UUID,
) -> None:
    """Hard-delete one goal scoped to the authenticated user."""
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            DELETE FROM goals
            WHERE id = %s
              AND user_id = %s
            RETURNING id
            """,
            (goal_id, user_id),
        )
        row = await cursor.fetchone()

    if row is None:
        raise LookupError("Goal not found")

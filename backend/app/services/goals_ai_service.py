"""Goals chatbot service helpers (compact reads + safe goal write wrappers)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.services.budget_dates import validate_month_start
from app.services.goals_service import (
    _compute_goal_metrics,
    _today,
    _validate_goal_state,
    create_goal,
    delete_goal,
    get_goal,
    list_goals,
    update_goal,
)
from app.services.insights_service import get_financial_health_snapshot_tool
from app.services.reports_dates import month_label

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    AsyncConnection = Any

MONEY_QUANT = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _normalize_amount(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return quantize_amount(value)


def get_current_month_start() -> date:
    today = _today()
    return date(today.year, today.month, 1)


def _resolve_month_start(month_start: date | None) -> date:
    if month_start is None:
        return get_current_month_start()
    return validate_month_start(month_start)


async def get_goal_by_id_or_name(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    goal_id: UUID | None = None,
    goal_name: str | None = None,
) -> dict[str, Any]:
    """Resolve one goal by id or by exact case-insensitive name for this user."""
    if goal_id is not None:
        return await get_goal(connection, user_id, goal_id)

    normalized_name = (goal_name or "").strip()
    if not normalized_name:
        raise ValueError("Provide goal_id or goal_name")

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id
            FROM goals
            WHERE user_id = %s
              AND LOWER(name) = LOWER(%s)
            ORDER BY created_at DESC
            LIMIT 2
            """,
            (user_id, normalized_name),
        )
        rows = await cursor.fetchall()

    if not rows:
        raise ValueError("Goal not found for this user")
    if len(rows) > 1:
        raise ValueError("Goal name is ambiguous. Please use goal_id.")

    return await get_goal(connection, user_id, rows[0]["id"])


async def get_compact_financial_snapshot(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date | None = None,
) -> dict[str, Any]:
    """Load compact monthly snapshot for affordability checks."""
    target_month_start = _resolve_month_start(month_start)
    snapshot = await get_financial_health_snapshot_tool(
        connection,
        user_id,
        month_start=target_month_start,
    )
    return {
        "month": snapshot["month"],
        "month_start": target_month_start,
        "currency": snapshot["currency"],
        "balance_amount": _normalize_amount(snapshot["balance_amount"]),
        "monthly_spend_amount": _normalize_amount(snapshot["monthly_spend_amount"]),
        "burn_rate_amount_per_month": _normalize_amount(snapshot["burn_rate_amount_per_month"]),
        "runway_days": snapshot["runway_days"],
    }


async def get_top_expense_categories_compact(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    target_month_start = _resolve_month_start(month_start)
    month_end = date(
        target_month_start.year + (1 if target_month_start.month == 12 else 0),
        (target_month_start.month % 12) + 1,
        1,
    )

    safe_limit = max(1, min(int(limit), 10))
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                t.category_id,
                COALESCE(c.name, 'Uncategorized') AS category_name,
                COALESCE(SUM(t.amount), 0) AS spent_amount
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = %s
              AND t.type = 'expense'
              AND t.deleted_at IS NULL
              AND t.occurred_on >= %s
              AND t.occurred_on < %s
            GROUP BY t.category_id, COALESCE(c.name, 'Uncategorized')
            ORDER BY spent_amount DESC, category_name ASC
            LIMIT %s
            """,
            (user_id, target_month_start, month_end, safe_limit),
        )
        rows = await cursor.fetchall()

    return [
        {
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "spent_amount": _normalize_amount(row["spent_amount"]),
        }
        for row in rows
    ]


def build_goal_budget_suggestions(
    goal: dict[str, Any],
    snapshot: dict[str, Any],
    top_categories: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build a compact, deterministic suggestion package.

    Uses existing goal metrics and a conservative cut heuristic.
    """
    required = _normalize_amount(goal["recommended_monthly_save_amount"])
    if required <= Decimal("0.00"):
        affordability = "on_track_or_completed"
    else:
        # Conservative monthly cut capacity: 20% of top-category spend.
        cut_capacity = quantize_amount(
            sum((row["spent_amount"] * Decimal("0.20") for row in top_categories), Decimal("0.00"))
        )
        affordability = "feasible" if cut_capacity >= required else "at_risk"

    suggestions: list[dict[str, Any]] = []
    remaining = required
    for row in top_categories[:3]:
        if remaining <= Decimal("0.00"):
            break
        cut = quantize_amount(min(row["spent_amount"] * Decimal("0.20"), remaining))
        if cut <= Decimal("0.00"):
            continue
        suggestions.append(
            {
                "category_name": row["category_name"],
                "suggested_monthly_cut_amount": cut,
            }
        )
        remaining = quantize_amount(max(Decimal("0.00"), remaining - cut))

    return {
        "goal_id": goal["id"],
        "goal_name": goal["name"],
        "currency": snapshot["currency"],
        "month": snapshot["month"],
        "remaining_amount": _normalize_amount(goal["remaining_amount"]),
        "months_left": int(goal["months_left"]),
        "required_monthly_save_amount": required,
        "current_balance_amount": _normalize_amount(snapshot["balance_amount"]),
        "burn_rate_amount_per_month": _normalize_amount(snapshot["burn_rate_amount_per_month"]),
        "runway_days": snapshot["runway_days"],
        "affordability": affordability,
        "suggested_cuts": suggestions,
        "remaining_gap_after_suggestions_amount": quantize_amount(max(Decimal("0.00"), remaining)),
    }


async def goal_create_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    name: str,
    target_amount: Decimal,
    deadline_date: date,
    saved_amount: Decimal = Decimal("0.00"),
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        normalized = _validate_goal_state(
            {
                "name": name,
                "target_amount": target_amount,
                "saved_amount": saved_amount,
                "deadline_date": deadline_date,
                "status": "active",
            },
            _today(),
        )
        preview = _compute_goal_metrics(
            {
                "id": UUID("00000000-0000-0000-0000-000000000000"),
                "user_id": user_id,
                "name": normalized["name"],
                "target_amount": normalized["target_amount"],
                "saved_amount": normalized["saved_amount"],
                "deadline_date": normalized["deadline_date"],
                "status": normalized["status"],
                "created_at": _today(),
                "updated_at": _today(),
            },
            _today(),
        )
        return {"dry_run": True, "goal": preview}

    created = await create_goal(
        connection,
        user_id,
        {
            "name": name,
            "target_amount": target_amount,
            "saved_amount": saved_amount,
            "deadline_date": deadline_date,
        },
    )
    return {"dry_run": False, "goal": created}


async def goal_add_saved_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    goal_id: UUID | None,
    goal_name: str | None,
    add_amount: Decimal,
    dry_run: bool = False,
) -> dict[str, Any]:
    goal = await get_goal_by_id_or_name(connection, user_id, goal_id=goal_id, goal_name=goal_name)
    next_saved = quantize_amount(_normalize_amount(goal["saved_amount"]) + quantize_amount(add_amount))
    if next_saved > _normalize_amount(goal["target_amount"]):
        raise ValueError("add_amount would exceed target_amount")

    if dry_run:
        existing = {
            "name": goal["name"],
            "target_amount": goal["target_amount"],
            "saved_amount": next_saved,
            "deadline_date": goal["deadline_date"],
            "status": goal["status"],
        }
        normalized = _validate_goal_state(existing, _today())
        preview = _compute_goal_metrics(
            {
                **goal,
                "saved_amount": normalized["saved_amount"],
                "status": normalized["status"],
            },
            _today(),
        )
        return {"dry_run": True, "goal": preview}

    updated = await update_goal(
        connection,
        user_id,
        goal["id"],
        {"saved_amount": next_saved},
    )
    return {"dry_run": False, "goal": updated}


async def goal_update_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    goal_id: UUID | None,
    goal_name: str | None,
    patch: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    goal = await get_goal_by_id_or_name(connection, user_id, goal_id=goal_id, goal_name=goal_name)

    if dry_run:
        existing = {
            "name": patch.get("name", goal["name"]),
            "target_amount": patch.get("target_amount", goal["target_amount"]),
            "saved_amount": patch.get("saved_amount", goal["saved_amount"]),
            "deadline_date": patch.get("deadline_date", goal["deadline_date"]),
            "status": patch.get("status", goal["status"]),
        }
        normalized = _validate_goal_state(existing, _today())
        preview = _compute_goal_metrics(
            {
                **goal,
                "name": normalized["name"],
                "target_amount": normalized["target_amount"],
                "saved_amount": normalized["saved_amount"],
                "deadline_date": normalized["deadline_date"],
                "status": normalized["status"],
            },
            _today(),
        )
        return {"dry_run": True, "goal": preview}

    updated = await update_goal(connection, user_id, goal["id"], patch)
    return {"dry_run": False, "goal": updated}


async def goal_delete_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    goal_id: UUID | None,
    goal_name: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    goal = await get_goal_by_id_or_name(connection, user_id, goal_id=goal_id, goal_name=goal_name)
    if dry_run:
        return {"dry_run": True, "goal": {"id": goal["id"], "name": goal["name"]}}

    await delete_goal(connection, user_id, goal["id"])
    return {"dry_run": False, "deleted": True, "goal": {"id": goal["id"], "name": goal["name"]}}


async def goals_list_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    status: str = "active",
) -> dict[str, Any]:
    rows = await list_goals(connection, user_id, status=status)
    return {"items": rows, "count": len(rows)}


async def goal_plan_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    goal_id: UUID | None,
    goal_name: str | None,
    month_start: date | None = None,
) -> dict[str, Any]:
    goal = await get_goal_by_id_or_name(connection, user_id, goal_id=goal_id, goal_name=goal_name)
    snapshot = await get_compact_financial_snapshot(connection, user_id, month_start=month_start)
    top_categories = await get_top_expense_categories_compact(connection, user_id, month_start=month_start, limit=3)
    suggestion = build_goal_budget_suggestions(goal, snapshot, top_categories)
    return {
        "goal": goal,
        "snapshot": snapshot,
        "suggestion": suggestion,
    }

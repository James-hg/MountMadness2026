"""Trip-aware planning services for AI assistant tool calls."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.services.budget_dates import validate_month_start
from app.services.reports_dates import month_label
from app.services.insights_service import get_financial_health_snapshot_tool

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


def _resolve_month_start(month_start: date | None) -> date:
    if month_start is None:
        today = date.today()
        return date(today.year, today.month, 1)
    return validate_month_start(month_start)


async def _month_expense_by_category(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> list[dict[str, Any]]:
    month_end_exclusive = date(month_start.year + (1 if month_start.month == 12 else 0), (month_start.month % 12) + 1, 1)

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
            LIMIT 10
            """,
            (user_id, month_start, month_end_exclusive),
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


def _build_suggested_cuts(
    spend_rows: list[dict[str, Any]],
    required_monthly_savings_amount: Decimal,
) -> tuple[list[dict[str, Any]], Decimal]:
    """Build practical monthly cuts from top expense categories."""
    remaining = quantize_amount(required_monthly_savings_amount)
    if remaining <= Decimal("0.00"):
        return [], Decimal("0.00")

    suggested: list[dict[str, Any]] = []
    total_cut = Decimal("0.00")

    for row in spend_rows:
        if remaining <= Decimal("0.00"):
            break

        max_reasonable_cut = quantize_amount(row["spent_amount"] * Decimal("0.30"))
        cut_amount = min(max_reasonable_cut, remaining)
        if cut_amount <= Decimal("0.00"):
            continue

        suggested.append(
            {
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "suggested_monthly_cut_amount": quantize_amount(cut_amount),
            }
        )
        total_cut = quantize_amount(total_cut + cut_amount)
        remaining = quantize_amount(remaining - cut_amount)

    return suggested, total_cut


async def plan_trip_budget_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    trip_budget_amount: Decimal,
    months_until_trip: int,
    trip_days: int,
    buffer_months: Decimal,
    month_start: date | None = None,
) -> dict[str, Any]:
    """Plan trip affordability and monthly savings need using conservative assumptions."""
    if trip_budget_amount <= Decimal("0.00"):
        raise ValueError("trip_budget_amount must be greater than 0")
    if months_until_trip < 1:
        raise ValueError("months_until_trip must be at least 1")
    if trip_days < 1:
        raise ValueError("trip_days must be at least 1")
    if buffer_months <= Decimal("0.00"):
        raise ValueError("buffer_months must be greater than 0")

    target_month_start = _resolve_month_start(month_start)

    health = await get_financial_health_snapshot_tool(
        connection,
        user_id,
        month_start=target_month_start,
    )

    current_balance_amount = _normalize_amount(health["balance_amount"])
    burn_rate_amount_per_month = _normalize_amount(health["burn_rate_amount_per_month"])
    trip_budget = quantize_amount(trip_budget_amount)

    buffer_amount = quantize_amount(burn_rate_amount_per_month * buffer_months)
    amount_available_for_trip_now = quantize_amount(max(Decimal("0.00"), current_balance_amount - buffer_amount))

    funding_gap_amount = quantize_amount(max(Decimal("0.00"), trip_budget - amount_available_for_trip_now))
    required_monthly_savings_amount = quantize_amount(funding_gap_amount / Decimal(months_until_trip))
    trip_daily_budget_amount = quantize_amount(trip_budget / Decimal(trip_days))

    spend_rows = await _month_expense_by_category(connection, user_id, target_month_start)
    suggested_cuts, suggested_monthly_total = _build_suggested_cuts(
        spend_rows,
        required_monthly_savings_amount,
    )

    total_cut_over_timeline = quantize_amount(suggested_monthly_total * Decimal(months_until_trip))
    remaining_gap_after_cuts_amount = quantize_amount(max(Decimal("0.00"), funding_gap_amount - total_cut_over_timeline))

    if funding_gap_amount == Decimal("0.00"):
        status = "affordable_now"
    elif remaining_gap_after_cuts_amount == Decimal("0.00"):
        status = "feasible_with_cuts"
    else:
        status = "at_risk"

    return {
        "month": month_label(target_month_start),
        "month_start": target_month_start,
        "currency": health["currency"],
        "current_balance_amount": current_balance_amount,
        "burn_rate_amount_per_month": burn_rate_amount_per_month,
        "buffer_months": quantize_amount(buffer_months),
        "buffer_amount": buffer_amount,
        "trip_budget_amount": trip_budget,
        "trip_days": trip_days,
        "trip_daily_budget_amount": trip_daily_budget_amount,
        "months_until_trip": months_until_trip,
        "amount_available_for_trip_now": amount_available_for_trip_now,
        "funding_gap_amount": funding_gap_amount,
        "required_monthly_savings_amount": required_monthly_savings_amount,
        "status": status,
        "suggested_cuts": suggested_cuts,
        "remaining_gap_after_cuts_amount": remaining_gap_after_cuts_amount,
    }


async def _get_user_currency(connection: AsyncConnection, user_id: UUID) -> str:
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT base_currency FROM users WHERE id = %s", (user_id,))
        row = await cursor.fetchone()

    if row is None:
        return "CAD"
    return row["base_currency"]


async def _validate_expense_categories(
    connection: AsyncConnection,
    user_id: UUID,
    category_ids: list[UUID],
) -> dict[UUID, dict[str, Any]]:
    if not category_ids:
        return {}

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, kind, user_id, is_system
            FROM categories
            WHERE id = ANY(%s)
            """,
            (category_ids,),
        )
        rows = await cursor.fetchall()

    row_by_id = {row["id"]: row for row in rows}

    for category_id in category_ids:
        row = row_by_id.get(category_id)
        if row is None:
            raise ValueError(f"Category not found: {category_id}")

        if row["kind"] != "expense":
            raise ValueError(f"Category must be expense-kind: {category_id}")

        if not row["is_system"] and row["user_id"] != user_id:
            raise ValueError(f"Forbidden category access: {category_id}")

    return row_by_id


async def _fetch_month_budget_limits(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> dict[UUID, Decimal]:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT category_id, limit_amount
            FROM budgets
            WHERE user_id = %s
              AND month_start = %s
            """,
            (user_id, month_start),
        )
        rows = await cursor.fetchall()

    return {row["category_id"]: _normalize_amount(row["limit_amount"]) for row in rows}


async def apply_trip_budget_adjustments_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
    adjustments: list[dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply category budget adjustments for trip funding, with optional dry-run."""
    target_month_start = validate_month_start(month_start)

    if not adjustments:
        raise ValueError("adjustments must include at least one item")

    parsed: list[tuple[UUID, Decimal]] = []
    seen: set[UUID] = set()

    for item in adjustments:
        raw_category_id = item.get("category_id")
        raw_amount = item.get("new_limit_amount")

        if raw_category_id is None:
            raise ValueError("category_id is required in adjustments")
        if raw_amount is None:
            raise ValueError("new_limit_amount is required in adjustments")

        try:
            category_id = UUID(str(raw_category_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid category_id in adjustments") from exc

        amount = quantize_amount(Decimal(str(raw_amount)))
        if amount < Decimal("0.00"):
            raise ValueError("new_limit_amount must be >= 0")

        if category_id in seen:
            raise ValueError("Duplicate category_id in adjustments")
        seen.add(category_id)

        parsed.append((category_id, amount))

    categories = await _validate_expense_categories(
        connection,
        user_id,
        [category_id for category_id, _ in parsed],
    )
    currency = await _get_user_currency(connection, user_id)

    existing_limits = await _fetch_month_budget_limits(connection, user_id, target_month_start)
    projected_limits = dict(existing_limits)
    for category_id, amount in parsed:
        projected_limits[category_id] = amount

    projected_total = quantize_amount(sum(projected_limits.values(), Decimal("0.00")))

    applied_rows = [
        {
            "category_id": category_id,
            "category_name": categories[category_id]["name"],
            "new_limit_amount": amount,
        }
        for category_id, amount in parsed
    ]

    response_payload = {
        "month_start": target_month_start,
        "currency": currency,
        "dry_run": dry_run,
        "applied": applied_rows,
        "monthly_total_summary": {
            "total_budget_amount": projected_total,
            "allocation_strategy": "ai_trip_adjustment_v1",
        },
    }

    if dry_run:
        return response_payload

    async with connection.transaction():
        async with connection.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO budgets (user_id, category_id, month_start, limit_amount, currency, is_user_modified)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (user_id, category_id, month_start)
                DO UPDATE SET
                    limit_amount = EXCLUDED.limit_amount,
                    currency = EXCLUDED.currency,
                    is_user_modified = TRUE
                """,
                [
                    (user_id, category_id, target_month_start, amount, currency)
                    for category_id, amount in parsed
                ],
            )

            await cursor.execute(
                """
                SELECT COALESCE(SUM(limit_amount), 0) AS total_budget_amount
                FROM budgets
                WHERE user_id = %s
                  AND month_start = %s
                """,
                (user_id, target_month_start),
            )
            total_row = await cursor.fetchone()
            total_budget_amount = _normalize_amount(total_row["total_budget_amount"])

            await cursor.execute(
                """
                INSERT INTO monthly_budget_totals (user_id, month_start, total_budget_amount, currency, allocation_strategy)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, month_start)
                DO UPDATE SET
                    total_budget_amount = EXCLUDED.total_budget_amount,
                    currency = EXCLUDED.currency,
                    allocation_strategy = EXCLUDED.allocation_strategy
                """,
                (user_id, target_month_start, total_budget_amount, currency, "ai_trip_adjustment_v1"),
            )

    response_payload["monthly_total_summary"]["total_budget_amount"] = total_budget_amount
    return response_payload

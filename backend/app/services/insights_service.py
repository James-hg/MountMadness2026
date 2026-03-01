"""AI read/simulation insight tools using aggregate SQL only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from app.services.budget_dates import validate_month_start
from app.services.dashboard_insights import get_month_total_budget
from app.services.reports_dates import list_month_starts, month_label, month_start_end_exclusive, shift_months
from app.services.reports_service import compute_runway_days, get_summary

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


def _percentage_floor(numerator: Decimal, denominator: Decimal) -> int:
    if denominator <= Decimal("0.00"):
        return 0
    return int(((numerator * Decimal("100")) / denominator).to_integral_value(rounding=ROUND_FLOOR))


async def _month_expense_by_category(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    month_end_exclusive: date,
) -> list[dict[str, Any]]:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                t.category_id,
                COALESCE(c.name, 'Uncategorized') AS category_name,
                COALESCE(c.slug, 'uncategorized') AS category_slug,
                COALESCE(SUM(t.amount), 0) AS spent_amount
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = %s
              AND t.type = 'expense'
              AND t.deleted_at IS NULL
              AND t.occurred_on >= %s
              AND t.occurred_on < %s
            GROUP BY t.category_id, COALESCE(c.name, 'Uncategorized'), COALESCE(c.slug, 'uncategorized')
            ORDER BY spent_amount DESC
            """,
            (user_id, month_start, month_end_exclusive),
        )
        rows = await cursor.fetchall()

    return [
        {
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "category_slug": row["category_slug"],
            "spent_amount": _normalize_amount(row["spent_amount"]),
        }
        for row in rows
    ]


async def _month_expense_total(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    month_end_exclusive: date,
) -> Decimal:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS expense_total
            FROM transactions
            WHERE user_id = %s
              AND type = 'expense'
              AND deleted_at IS NULL
              AND occurred_on >= %s
              AND occurred_on < %s
            """,
            (user_id, month_start, month_end_exclusive),
        )
        row = await cursor.fetchone()

    return _normalize_amount(row["expense_total"])


async def compare_category_trend_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
    lookback_months: int = 3,
) -> dict[str, Any]:
    """Compare current-month category spend against previous N complete months average."""
    month_start = validate_month_start(month_start)
    lookback = max(1, min(12, lookback_months))
    month_end_exclusive = shift_months(month_start, 1)

    current_rows = await _month_expense_by_category(connection, user_id, month_start, month_end_exclusive)

    lookback_start = shift_months(month_start, -lookback)
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                t.category_id,
                COALESCE(c.name, 'Uncategorized') AS category_name,
                COALESCE(c.slug, 'uncategorized') AS category_slug,
                COALESCE(SUM(t.amount), 0) AS total_amount
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = %s
              AND t.type = 'expense'
              AND t.deleted_at IS NULL
              AND t.occurred_on >= %s
              AND t.occurred_on < %s
            GROUP BY t.category_id, COALESCE(c.name, 'Uncategorized'), COALESCE(c.slug, 'uncategorized')
            """,
            (user_id, lookback_start, month_start),
        )
        lookback_rows = await cursor.fetchall()

    lookback_map = {
        row["category_id"]: {
            "category_name": row["category_name"],
            "category_slug": row["category_slug"],
            "avg_amount": quantize_amount(_normalize_amount(row["total_amount"]) / Decimal(lookback)),
        }
        for row in lookback_rows
    }

    deltas: list[dict[str, Any]] = []
    for current in current_rows:
        baseline = lookback_map.get(current["category_id"])
        avg_amount = baseline["avg_amount"] if baseline else Decimal("0.00")
        delta_amount = quantize_amount(current["spent_amount"] - avg_amount)
        pct_change = None
        if avg_amount > Decimal("0.00"):
            pct_change = _percentage_floor(abs(delta_amount), avg_amount)

        deltas.append(
            {
                "category_id": current["category_id"],
                "category_name": current["category_name"],
                "category_slug": current["category_slug"],
                "current_amount": current["spent_amount"],
                "average_amount": avg_amount,
                "delta_amount": delta_amount,
                "direction": "up" if delta_amount >= Decimal("0.00") else "down",
                "pct_change": pct_change,
            }
        )

    deltas.sort(key=lambda item: (-item["delta_amount"], item["category_name"].lower()))

    return {
        "month": month_label(month_start),
        "lookback_months": lookback,
        "items": deltas[:10],
    }


async def get_financial_health_snapshot_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
) -> dict[str, Any]:
    """Return compact dashboard health snapshot for one month."""
    month_start = validate_month_start(month_start)
    month_end_exclusive = shift_months(month_start, 1)

    summary = await get_summary(connection, user_id, month_start, month_end_exclusive)
    month_budget = await get_month_total_budget(connection, user_id, month_start)
    top_categories = await _month_expense_by_category(connection, user_id, month_start, month_end_exclusive)

    monthly_spend = summary["monthly_spend_amount"]
    budget_used_pct = 0
    if month_budget is not None and month_budget > Decimal("0.00"):
        budget_used_pct = _percentage_floor(monthly_spend, month_budget)

    top_category = top_categories[0] if top_categories else None

    return {
        "month": month_label(month_start),
        "currency": summary["currency"],
        "balance_amount": summary["balance_amount"],
        "monthly_spend_amount": monthly_spend,
        "burn_rate_amount_per_month": summary["burn_rate_amount_per_month"],
        "runway_days": summary["runway_days"],
        "total_budget_amount": month_budget,
        "budget_used_pct": budget_used_pct,
        "top_category": top_category,
    }


async def project_future_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    months_ahead: int,
) -> dict[str, Any]:
    """Project ending balance and runway if current burn rate continues."""
    months = max(1, min(24, months_ahead))
    today = date.today()
    current_month_start = date(today.year, today.month, 1)
    month_end_exclusive = shift_months(current_month_start, 1)

    summary = await get_summary(connection, user_id, current_month_start, month_end_exclusive)
    balance_amount = summary["balance_amount"]
    burn = summary["burn_rate_amount_per_month"]

    projected_spend = quantize_amount(burn * Decimal(months))
    projected_balance = quantize_amount(balance_amount - projected_spend)

    projected_runway_days = compute_runway_days(projected_balance, burn)

    return {
        "months_ahead": months,
        "currency": summary["currency"],
        "starting_balance_amount": balance_amount,
        "burn_rate_amount_per_month": burn,
        "projected_spend_amount": projected_spend,
        "projected_balance_amount": projected_balance,
        "projected_runway_days": projected_runway_days,
    }


async def get_fixed_variable_breakdown_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
    fixed_categories: list[str],
) -> dict[str, Any]:
    """Break monthly expense into fixed vs variable buckets by category slug."""
    month_start = validate_month_start(month_start)
    month_end_exclusive = shift_months(month_start, 1)

    slugs = [fixed_slug.strip().lower() for fixed_slug in fixed_categories if fixed_slug.strip()]

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                COALESCE(c.slug, 'uncategorized') AS slug,
                COALESCE(SUM(t.amount), 0) AS spent_amount
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = %s
              AND t.type = 'expense'
              AND t.deleted_at IS NULL
              AND t.occurred_on >= %s
              AND t.occurred_on < %s
            GROUP BY COALESCE(c.slug, 'uncategorized')
            """,
            (user_id, month_start, month_end_exclusive),
        )
        rows = await cursor.fetchall()

    fixed_total = Decimal("0.00")
    variable_total = Decimal("0.00")

    for row in rows:
        amount = _normalize_amount(row["spent_amount"])
        if row["slug"] in slugs:
            fixed_total += amount
        else:
            variable_total += amount

    fixed_total = quantize_amount(fixed_total)
    variable_total = quantize_amount(variable_total)
    total = quantize_amount(fixed_total + variable_total)

    return {
        "month": month_label(month_start),
        "fixed_total_amount": fixed_total,
        "variable_total_amount": variable_total,
        "fixed_pct": _percentage_floor(fixed_total, total),
        "variable_pct": _percentage_floor(variable_total, total),
    }


async def detect_anomalies_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
    compare_to: Literal["last_month", "avg_3m"],
) -> dict[str, Any]:
    """Detect category spend spikes using a deterministic threshold rule."""
    month_start = validate_month_start(month_start)
    month_end_exclusive = shift_months(month_start, 1)

    current_rows = await _month_expense_by_category(connection, user_id, month_start, month_end_exclusive)
    current_map = {row["category_id"]: row for row in current_rows}

    baseline_map: dict[UUID | None, Decimal] = {}

    if compare_to == "last_month":
        prev_start = shift_months(month_start, -1)
        prev_rows = await _month_expense_by_category(connection, user_id, prev_start, month_start)
        baseline_map = {row["category_id"]: row["spent_amount"] for row in prev_rows}
    else:
        start = shift_months(month_start, -3)
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT
                    t.category_id,
                    COALESCE(SUM(t.amount), 0) AS total_amount
                FROM transactions t
                WHERE t.user_id = %s
                  AND t.type = 'expense'
                  AND t.deleted_at IS NULL
                  AND t.occurred_on >= %s
                  AND t.occurred_on < %s
                GROUP BY t.category_id
                """,
                (user_id, start, month_start),
            )
            rows = await cursor.fetchall()

        baseline_map = {
            row["category_id"]: quantize_amount(_normalize_amount(row["total_amount"]) / Decimal("3"))
            for row in rows
        }

    anomalies: list[dict[str, Any]] = []

    for category_id, current in current_map.items():
        baseline = baseline_map.get(category_id, Decimal("0.00"))
        current_amount = current["spent_amount"]
        if baseline <= Decimal("0.00"):
            continue

        delta = quantize_amount(current_amount - baseline)
        pct_increase = _percentage_floor(delta, baseline)

        # Threshold guardrail keeps anomalies meaningful.
        if delta >= Decimal("20.00") and pct_increase >= 30:
            anomalies.append(
                {
                    "category_id": category_id,
                    "category_name": current["category_name"],
                    "current_amount": current_amount,
                    "baseline_amount": baseline,
                    "delta_amount": delta,
                    "pct_increase": pct_increase,
                }
            )

    anomalies.sort(key=lambda item: (-item["pct_increase"], -item["delta_amount"], item["category_name"].lower()))

    return {
        "month": month_label(month_start),
        "compare_to": compare_to,
        "items": anomalies[:10],
    }


async def plan_savings_goal_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    target_amount: Decimal,
    months: int,
    month_start: date | None,
) -> dict[str, Any]:
    """Build a simple savings plan and suggested category reductions."""
    if target_amount <= Decimal("0.00"):
        raise ValueError("target_amount must be greater than 0")

    horizon_months = max(1, min(36, months))

    if month_start is None:
        today = date.today()
        month_start = date(today.year, today.month, 1)
    else:
        month_start = validate_month_start(month_start)

    month_end_exclusive = shift_months(month_start, 1)
    current_rows = await _month_expense_by_category(connection, user_id, month_start, month_end_exclusive)
    total_spend = await _month_expense_total(connection, user_id, month_start, month_end_exclusive)

    monthly_required = quantize_amount(target_amount / Decimal(horizon_months))

    # Generate practical category-cut suggestions from highest spend categories.
    suggested_cuts: list[dict[str, Any]] = []
    remaining_cut = monthly_required

    for row in current_rows[:5]:
        if remaining_cut <= Decimal("0.00"):
            break

        max_reasonable_cut = quantize_amount(row["spent_amount"] * Decimal("0.30"))
        cut_amount = min(max_reasonable_cut, remaining_cut)
        if cut_amount <= Decimal("0.00"):
            continue

        suggested_cuts.append(
            {
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "suggested_cut_amount": cut_amount,
            }
        )
        remaining_cut = quantize_amount(remaining_cut - cut_amount)

    feasible = remaining_cut <= Decimal("0.00")

    health = await get_financial_health_snapshot_tool(
        connection,
        user_id,
        month_start=month_start,
    )

    return {
        "month": month_label(month_start),
        "target_amount": quantize_amount(target_amount),
        "months": horizon_months,
        "required_monthly_savings_amount": monthly_required,
        "current_monthly_spend_amount": total_spend,
        "suggested_cuts": suggested_cuts,
        "fully_covered_by_suggestions": feasible,
        "remaining_gap_amount": max(Decimal("0.00"), remaining_cut),
        "current_balance_amount": health["balance_amount"],
        "current_runway_days": health["runway_days"],
    }

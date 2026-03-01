"""AI budget tool services: suggest, apply, and simulate monthly plan changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.services.budget_allocation import AllocationCategory, allocate_default_weights_v1
from app.services.budget_dates import validate_month_start
from app.services.reports_dates import list_month_starts, shift_months
from app.utils import slugify

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


def _rebalance_to_total(allocations: dict[UUID, Decimal], total: Decimal) -> dict[UUID, Decimal]:
    """Quantize + deterministic remainder distribution so sum equals target total."""
    if not allocations:
        return {}

    rounded = {key: quantize_amount(value) for key, value in allocations.items()}
    current = sum(rounded.values(), Decimal("0.00"))
    diff = quantize_amount(total - current)

    if diff == Decimal("0.00"):
        return rounded

    step = MONEY_QUANT if diff > Decimal("0.00") else -MONEY_QUANT
    steps = int((abs(diff) / MONEY_QUANT).to_integral_value(rounding=ROUND_FLOOR))

    ordered_ids = sorted(
        rounded.keys(),
        key=lambda cid: (-allocations[cid], str(cid)),
    )

    for index in range(steps):
        category_id = ordered_ids[index % len(ordered_ids)]
        rounded[category_id] = quantize_amount(rounded[category_id] + step)

    return rounded


async def _get_user_currency(connection: AsyncConnection, user_id: UUID) -> str:
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT base_currency FROM users WHERE id = %s", (user_id,))
        row = await cursor.fetchone()

    if row is None:
        return "CAD"
    return row["base_currency"]


async def _get_visible_expense_categories(connection: AsyncConnection, user_id: UUID) -> list[dict[str, Any]]:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, slug, is_system, user_id
            FROM categories
            WHERE kind = 'expense'
              AND (is_system = TRUE OR user_id = %s)
            ORDER BY name ASC
            """,
            (user_id,),
        )
        return await cursor.fetchall()


async def _resolve_expense_category(
    connection: AsyncConnection,
    user_id: UUID,
    category_id: UUID | None,
    category_name: str | None,
) -> dict[str, Any]:
    visible = await _get_visible_expense_categories(connection, user_id)
    by_id = {row["id"]: row for row in visible}

    if category_id is not None:
        row = by_id.get(category_id)
        if row is None:
            raise ValueError("Category not found or not visible to user")
        return row

    if not category_name:
        raise ValueError("Provide category_id or category_name")

    normalized_name = category_name.strip()
    if not normalized_name:
        raise ValueError("category_name cannot be empty")

    try:
        category_slug = slugify(normalized_name)
    except ValueError as exc:
        raise ValueError("Invalid category_name") from exc

    for row in visible:
        if row["slug"] == category_slug or row["name"].lower() == normalized_name.lower():
            return row

    raise ValueError("Category not found or not visible to user")


async def _derive_total_budget_amount(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> Decimal:
    """Derive default total budget from recent spending history."""
    prev_month_starts = list_month_starts(shift_months(month_start, -1), 3)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                date_trunc('month', occurred_on)::date AS month_start,
                COALESCE(SUM(amount), 0) AS expense_total
            FROM transactions
            WHERE user_id = %s
              AND type = 'expense'
              AND deleted_at IS NULL
              AND occurred_on >= %s
              AND occurred_on < %s
            GROUP BY month_start
            """,
            (user_id, shift_months(month_start, -3), month_start),
        )
        rows = await cursor.fetchall()

    totals_by_month = {
        row["month_start"]: _normalize_amount(row["expense_total"])
        for row in rows
    }

    covered = [totals_by_month.get(m, Decimal("0.00")) for m in prev_month_starts]
    if any(amount > Decimal("0.00") for amount in covered):
        avg = sum(covered, Decimal("0.00")) / Decimal(len(covered))
        return quantize_amount(avg)

    # 30-day fallback before target month.
    fallback_start = month_start - timedelta(days=30)
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
            (user_id, fallback_start, month_start),
        )
        row = await cursor.fetchone()

    fallback = _normalize_amount(row["expense_total"])
    if fallback > Decimal("0.00"):
        return fallback

    # Deterministic base fallback for new users with no spend history.
    return Decimal("1000.00")


async def suggest_budget_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
    total_budget_amount: Decimal | None,
    fixed_overrides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Suggest monthly category allocations without writing to DB."""
    month_start = validate_month_start(month_start)

    if total_budget_amount is not None:
        total = quantize_amount(total_budget_amount)
        if total <= Decimal("0.00"):
            raise ValueError("total_budget_amount must be greater than 0")
    else:
        total = await _derive_total_budget_amount(connection, user_id, month_start)

    category_rows = await _get_visible_expense_categories(connection, user_id)
    if not category_rows:
        raise ValueError("No expense categories available")

    allocation_categories = [
        AllocationCategory(category_id=row["id"], slug=row["slug"])
        for row in category_rows
    ]

    base_allocations = allocate_default_weights_v1(total, allocation_categories)

    overrides: dict[UUID, Decimal] = {}
    if fixed_overrides:
        for item in fixed_overrides:
            resolved = await _resolve_expense_category(
                connection,
                user_id,
                item.get("category_id"),
                item.get("category_name"),
            )
            amount = quantize_amount(Decimal(str(item["limit_amount"])))
            if amount < Decimal("0.00"):
                raise ValueError("Override amount must be >= 0")
            overrides[resolved["id"]] = amount

    if overrides:
        remaining_total = quantize_amount(total - sum(overrides.values(), Decimal("0.00")))
        adjusted: dict[UUID, Decimal] = {key: Decimal("0.00") for key in base_allocations}
        adjusted.update(overrides)

        regenerable_ids = [cid for cid in base_allocations if cid not in overrides]
        base_remaining = sum((base_allocations[cid] for cid in regenerable_ids), Decimal("0.00"))

        if remaining_total > Decimal("0.00") and regenerable_ids:
            if base_remaining > Decimal("0.00"):
                for cid in regenerable_ids:
                    adjusted[cid] = remaining_total * (base_allocations[cid] / base_remaining)
            else:
                equal = remaining_total / Decimal(len(regenerable_ids))
                for cid in regenerable_ids:
                    adjusted[cid] = equal

        base_allocations = _rebalance_to_total(adjusted, total)

    by_id = {row["id"]: row for row in category_rows}
    allocations = [
        {
            "category_id": category_id,
            "category_name": by_id[category_id]["name"],
            "category_slug": by_id[category_id]["slug"],
            "limit_amount": quantize_amount(amount),
        }
        for category_id, amount in base_allocations.items()
    ]
    allocations.sort(key=lambda item: item["category_name"].lower())

    return {
        "month_start": month_start,
        "strategy": "default_weights_v1",
        "total_budget_amount": total,
        "currency": await _get_user_currency(connection, user_id),
        "allocations": allocations,
    }


@dataclass
class ResolvedAllocation:
    category_id: UUID
    category_name: str
    category_slug: str
    limit_amount: Decimal


async def apply_budget_plan_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
    allocations: list[dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply one full monthly budget plan (upsert total + per-category rows)."""
    month_start = validate_month_start(month_start)

    if not allocations:
        raise ValueError("allocations must include at least one category")

    resolved_allocations: list[ResolvedAllocation] = []
    seen: set[UUID] = set()

    for item in allocations:
        resolved_category = await _resolve_expense_category(
            connection,
            user_id,
            item.get("category_id"),
            item.get("category_name"),
        )
        limit_amount = quantize_amount(Decimal(str(item["limit_amount"])))

        if limit_amount < Decimal("0.00"):
            raise ValueError("limit_amount must be >= 0")

        if resolved_category["id"] in seen:
            raise ValueError("Duplicate category in allocations")
        seen.add(resolved_category["id"])

        resolved_allocations.append(
            ResolvedAllocation(
                category_id=resolved_category["id"],
                category_name=resolved_category["name"],
                category_slug=resolved_category["slug"],
                limit_amount=limit_amount,
            )
        )

    total_budget_amount = quantize_amount(
        sum((item.limit_amount for item in resolved_allocations), Decimal("0.00"))
    )
    currency = await _get_user_currency(connection, user_id)

    response_payload = {
        "month_start": month_start,
        "currency": currency,
        "total_budget_amount": total_budget_amount,
        "applied": [
            {
                "category_id": item.category_id,
                "category_name": item.category_name,
                "category_slug": item.category_slug,
                "limit_amount": item.limit_amount,
            }
            for item in resolved_allocations
        ],
        "dry_run": dry_run,
    }

    if dry_run:
        return response_payload

    async with connection.transaction():
        async with connection.cursor() as cursor:
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
                (user_id, month_start, total_budget_amount, currency, "ai_manual_plan_v1"),
            )

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
                    (
                        user_id,
                        item.category_id,
                        month_start,
                        item.limit_amount,
                        currency,
                    )
                    for item in resolved_allocations
                ],
            )

    return response_payload


def _runway_days(balance_amount: Decimal, burn_rate_per_month: Decimal) -> int | None:
    if burn_rate_per_month <= Decimal("0.00"):
        return None

    daily = burn_rate_per_month / Decimal("30")
    if daily <= Decimal("0.00"):
        return None

    days = (balance_amount / daily).to_integral_value(rounding=ROUND_FLOOR)
    return max(0, int(days))


async def _all_time_balance(connection: AsyncConnection, user_id: UUID) -> Decimal:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income_total,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expense_total
            FROM transactions
            WHERE user_id = %s
              AND deleted_at IS NULL
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

    return quantize_amount(_normalize_amount(row["income_total"]) - _normalize_amount(row["expense_total"]))


async def _monthly_expense(
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


async def _three_complete_month_avg_expense(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> Decimal | None:
    expected = list_month_starts(shift_months(month_start, -1), 3)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                date_trunc('month', occurred_on)::date AS month_start,
                COALESCE(SUM(amount), 0) AS expense_total
            FROM transactions
            WHERE user_id = %s
              AND type = 'expense'
              AND deleted_at IS NULL
              AND occurred_on >= %s
              AND occurred_on < %s
            GROUP BY month_start
            """,
            (user_id, shift_months(month_start, -3), month_start),
        )
        rows = await cursor.fetchall()

    totals = {row["month_start"]: _normalize_amount(row["expense_total"]) for row in rows}
    if not expected or not all(month in totals for month in expected):
        return None

    return quantize_amount(sum((totals[month] for month in expected), Decimal("0.00")) / Decimal(len(expected)))


async def simulate_budget_change_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    month_start: date,
    category_id: UUID,
    delta_amount: Decimal,
) -> dict[str, Any]:
    """Simulate monthly spend and runway impact from a category budget delta."""
    month_start = validate_month_start(month_start)
    month_end_exclusive = shift_months(month_start, 1)

    category = await _resolve_expense_category(connection, user_id, category_id, None)

    delta = quantize_amount(delta_amount)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT limit_amount
            FROM budgets
            WHERE user_id = %s
              AND month_start = %s
              AND category_id = %s
            """,
            (user_id, month_start, category["id"]),
        )
        budget_row = await cursor.fetchone()

    current_limit = _normalize_amount(budget_row["limit_amount"]) if budget_row else Decimal("0.00")
    projected_limit = quantize_amount(max(Decimal("0.00"), current_limit + delta))

    total_spend = await _monthly_expense(connection, user_id, month_start, month_end_exclusive)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS category_spend
            FROM transactions
            WHERE user_id = %s
              AND type = 'expense'
              AND deleted_at IS NULL
              AND category_id = %s
              AND occurred_on >= %s
              AND occurred_on < %s
            """,
            (user_id, category["id"], month_start, month_end_exclusive),
        )
        row = await cursor.fetchone()

    category_spend = _normalize_amount(row["category_spend"])

    baseline_burn = await _three_complete_month_avg_expense(connection, user_id, month_start)
    if baseline_burn is None:
        baseline_burn = total_spend

    projected_burn = quantize_amount(max(Decimal("0.00"), baseline_burn + delta))

    balance_amount = await _all_time_balance(connection, user_id)
    runway_before = _runway_days(balance_amount, baseline_burn)
    runway_after = _runway_days(balance_amount, projected_burn)

    return {
        "month_start": month_start,
        "category_id": category["id"],
        "category_name": category["name"],
        "current_limit_amount": current_limit,
        "projected_limit_amount": projected_limit,
        "delta_amount": delta,
        "category_spent_amount": category_spend,
        "current_month_spend_amount": total_spend,
        "baseline_burn_amount_per_month": baseline_burn,
        "projected_burn_amount_per_month": projected_burn,
        "runway_days_before": runway_before,
        "runway_days_after": runway_after,
        "runway_days_delta": (runway_after - runway_before) if runway_before is not None and runway_after is not None else None,
    }

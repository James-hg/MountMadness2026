from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .reports_dates import list_month_starts, month_label, shift_months

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    # Keep tests importable even when psycopg is not installed locally.
    AsyncConnection = Any

MONEY_QUANT = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    """Normalize money values to NUMERIC(12,2) scale."""
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _normalize_amount(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return quantize_amount(value)


def _rounded_percentage(spent_amount: Decimal, total_amount: Decimal) -> int:
    """Return nearest int percentage for category-share cards."""
    if total_amount <= Decimal("0.00"):
        return 0
    ratio = (spent_amount * Decimal("100")) / total_amount
    return int(ratio.to_integral_value(rounding=ROUND_HALF_UP))


def compute_runway_days(balance_amount: Decimal, burn_rate_amount_per_month: Decimal) -> int | None:
    """Convert monthly burn to runway days, guarding very small burn rates."""
    burn = quantize_amount(burn_rate_amount_per_month)

    # Treat sub-cent/day burn as effectively zero to avoid absurd runway values.
    if burn < Decimal("0.30"):
        return None

    per_day = burn / Decimal("30")
    if per_day <= Decimal("0"):
        return None

    days = (balance_amount / per_day).to_integral_value(rounding=ROUND_FLOOR)
    return max(0, int(days))


def select_burn_rate_amount(
    *,
    three_month_totals: dict[date, Decimal],
    expected_months: list[date],
    fallback_30_day_expense: Decimal,
    fallback_days: int,
) -> Decimal:
    """
    Choose burn rate using preferred 3 complete months, else a 30-day fallback.
    """
    if expected_months and all(month in three_month_totals for month in expected_months):
        total = sum((three_month_totals[month] for month in expected_months), Decimal("0.00"))
        return quantize_amount(total / Decimal(len(expected_months)))

    if fallback_30_day_expense <= Decimal("0.00") or fallback_days <= 0:
        return Decimal("0.00")

    daily_avg = fallback_30_day_expense / Decimal(fallback_days)
    return quantize_amount(daily_avg * Decimal("30"))


def build_trend_series(
    month_starts: list[date],
    aggregates: dict[date, tuple[Decimal, Decimal]],
) -> list[dict[str, Decimal | str]]:
    """Build a zero-filled, oldest->newest monthly trend series."""
    items: list[dict[str, Decimal | str]] = []
    for month_start in month_starts:
        expense, income = aggregates.get(month_start, (Decimal("0.00"), Decimal("0.00")))
        items.append(
            {
                "month": month_label(month_start),
                "expense_amount": quantize_amount(expense),
                "income_amount": quantize_amount(income),
            }
        )
    return items


async def get_user_currency(connection: AsyncConnection, user_id: UUID) -> str:
    """Load the user's base currency; default to CAD for defensive fallback."""
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT base_currency FROM users WHERE id = %s", (user_id,))
        row = await cursor.fetchone()

    if row is None:
        return "CAD"
    return row["base_currency"]


async def _all_time_balance_amount(connection: AsyncConnection, user_id: UUID) -> Decimal:
    """All-time balance = income - expense for the authenticated tenant."""
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

    income_total = _normalize_amount(row["income_total"])
    expense_total = _normalize_amount(row["expense_total"])
    return quantize_amount(income_total - expense_total)


async def _expense_sum_in_window(
    connection: AsyncConnection,
    user_id: UUID,
    start_inclusive: date,
    end_exclusive: date,
) -> Decimal:
    """Expense sum in [start_inclusive, end_exclusive)."""
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
            (user_id, start_inclusive, end_exclusive),
        )
        row = await cursor.fetchone()

    return _normalize_amount(row["expense_total"])


async def _three_complete_month_expenses(
    connection: AsyncConnection,
    user_id: UUID,
    anchor_month_start: date,
) -> dict[date, Decimal]:
    """Aggregate expense totals for the 3 full months before the selected month."""
    start = shift_months(anchor_month_start, -3)
    end = anchor_month_start

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
            (user_id, start, end),
        )
        rows = await cursor.fetchall()

    return {row["month_start"]: _normalize_amount(row["expense_total"]) for row in rows}


async def get_summary(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    month_end_exclusive: date,
) -> dict:
    """Return summary cards data for the reports page."""
    currency = await get_user_currency(connection, user_id)

    balance_amount = await _all_time_balance_amount(connection, user_id)
    monthly_spend_amount = await _expense_sum_in_window(
        connection,
        user_id,
        month_start,
        month_end_exclusive,
    )

    previous_three = list_month_starts(shift_months(month_start, -1), 3)
    previous_totals = await _three_complete_month_expenses(
        connection,
        user_id,
        month_start,
    )

    # Anchor the fallback window to the selected month context.
    fallback_end = month_end_exclusive
    fallback_start = fallback_end - timedelta(days=30)
    fallback_days = max(1, (fallback_end - fallback_start).days)

    fallback_expense = await _expense_sum_in_window(
        connection,
        user_id,
        fallback_start,
        fallback_end,
    )

    burn_rate_amount_per_month = select_burn_rate_amount(
        three_month_totals=previous_totals,
        expected_months=previous_three,
        fallback_30_day_expense=fallback_expense,
        fallback_days=fallback_days,
    )

    runway_days = compute_runway_days(balance_amount, burn_rate_amount_per_month)

    return {
        "currency": currency,
        "balance_amount": balance_amount,
        "monthly_spend_amount": monthly_spend_amount,
        "burn_rate_amount_per_month": burn_rate_amount_per_month,
        "runway_days": runway_days,
    }


async def get_top_categories(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    month_end_exclusive: date,
    limit: int,
) -> dict:
    """Return top expense categories for a selected month window."""
    currency = await get_user_currency(connection, user_id)

    total_monthly_spend = await _expense_sum_in_window(
        connection,
        user_id,
        month_start,
        month_end_exclusive,
    )

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                COALESCE(c.name, 'Uncategorized') AS category,
                COALESCE(SUM(t.amount), 0) AS spent_amount
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = %s
              AND t.type = 'expense'
              AND t.deleted_at IS NULL
              AND t.occurred_on >= %s
              AND t.occurred_on < %s
            GROUP BY category
            ORDER BY spent_amount DESC, category ASC
            LIMIT %s
            """,
            (user_id, month_start, month_end_exclusive, limit),
        )
        rows = await cursor.fetchall()

    items = [
        {
            "category": row["category"],
            "spent_amount": quantize_amount(_normalize_amount(row["spent_amount"])),
            "percentage": _rounded_percentage(_normalize_amount(row["spent_amount"]), total_monthly_spend),
        }
        for row in rows
    ]

    return {
        "currency": currency,
        "items": items,
    }


async def get_trends(
    connection: AsyncConnection,
    user_id: UUID,
    month_starts: list[date],
) -> dict:
    """Return monthly expense/income trend data in oldest->newest order."""
    currency = await get_user_currency(connection, user_id)

    if not month_starts:
        return {"currency": currency, "items": []}

    range_start = month_starts[0]
    range_end = shift_months(month_starts[-1], 1)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                date_trunc('month', occurred_on)::date AS month_start,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expense_amount,
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income_amount
            FROM transactions
            WHERE user_id = %s
              AND deleted_at IS NULL
              AND occurred_on >= %s
              AND occurred_on < %s
            GROUP BY month_start
            """,
            (user_id, range_start, range_end),
        )
        rows = await cursor.fetchall()

    aggregates = {
        row["month_start"]: (
            _normalize_amount(row["expense_amount"]),
            _normalize_amount(row["income_amount"]),
        )
        for row in rows
    }

    return {
        "currency": currency,
        "items": build_trend_series(month_starts, aggregates),
    }


async def get_monthly_breakdown(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    month_end_exclusive: date,
) -> dict:
    """Return a day-by-day monthly expense series, zero-filled for missing days."""
    currency = await get_user_currency(connection, user_id)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT occurred_on AS txn_date, COALESCE(SUM(amount), 0) AS expense_amount
            FROM transactions
            WHERE user_id = %s
              AND type = 'expense'
              AND deleted_at IS NULL
              AND occurred_on >= %s
              AND occurred_on < %s
            GROUP BY txn_date
            ORDER BY txn_date ASC
            """,
            (user_id, month_start, month_end_exclusive),
        )
        rows = await cursor.fetchall()

    by_date = {row["txn_date"]: _normalize_amount(row["expense_amount"]) for row in rows}

    items: list[dict] = []
    day = month_start
    while day < month_end_exclusive:
        items.append(
            {
                "date": day,
                "expense_amount": quantize_amount(by_date.get(day, Decimal("0.00"))),
            }
        )
        day += timedelta(days=1)

    return {
        "currency": currency,
        "items": items,
    }

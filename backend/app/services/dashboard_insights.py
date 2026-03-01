from __future__ import annotations
"""
Service layer for dashboard budget-health and smart-insight payloads.

Design goals:
- deterministic output (no LLM)
- aggregate SQL (avoid N+1)
- money-safe arithmetic with Decimal and 2-decimal quantization
"""

from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .reports_dates import list_month_starts, month_label, shift_months

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    AsyncConnection = Any

MONEY_QUANT = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    """Normalize money to NUMERIC(12,2) precision."""
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _normalize_amount(value: Decimal | None) -> Decimal:
    """Convert nullable DB aggregates to normalized Decimal amounts."""
    if value is None:
        return Decimal("0.00")
    return quantize_amount(value)


def amount_to_pct_floor(spent: Decimal, budget: Decimal | None) -> int | None:
    """Compute floor(spent/budget*100), or null when budget is missing/non-positive."""
    if budget is None or budget <= Decimal("0.00"):
        return None
    ratio = (spent * Decimal("100")) / budget
    return int(ratio.to_integral_value(rounding=ROUND_FLOOR))


def status_for_used_pct(used_pct: int | None) -> str:
    """Map used percentage to dashboard status buckets."""
    if used_pct is None or used_pct < 70:
        return "ok"
    if used_pct <= 100:
        return "warning"
    return "over"


def _currency_symbol(currency: str) -> str:
    """Simple symbol mapping for short in-card insight messages."""
    mapping = {
        "CAD": "$",
        "USD": "$",
        "EUR": "EUR ",
        "GBP": "GBP ",
    }
    return mapping.get(currency, "$")


def format_money_for_message(amount: Decimal, currency: str) -> str:
    """Format message-friendly currency values like '$123.45'."""
    symbol = _currency_symbol(currency)
    quantized = quantize_amount(amount)
    return f"{symbol}{quantized:,.2f}"


def _category_sort_key(item: dict) -> tuple:
    """Stable sort key for top category selection."""
    has_budget = item["budget_amount"] is not None
    used_pct = item["used_pct"] if item["used_pct"] is not None else -1
    spent_amount = _normalize_amount(item["spent_amount"])
    return (
        0 if has_budget else 1,
        -used_pct,
        -spent_amount,
        item["category_name"].lower(),
    )


def build_budget_health(
    *,
    month_start: date,
    currency: str,
    total_budget_amount: Decimal | None,
    spend_rows: list[dict],
    budget_rows: list[dict],
) -> tuple[dict, list[dict]]:
    """
    Build budget-health section and return:
    1) response-ready budget_health payload (top 3 categories)
    2) full normalized category list for downstream insight generation
    """
    active: dict[UUID | None, dict] = {}

    # Seed active set from categories with monthly spend.
    for row in spend_rows:
        category_id = row["category_id"]
        category_name = row["category_name"] or "Uncategorized"
        spent_amount = _normalize_amount(row["spent_amount"])
        active[category_id] = {
            "category_id": category_id,
            "category_name": category_name,
            "budget_amount": None,
            "spent_amount": spent_amount,
            "remaining_amount": None,
            "used_pct": None,
            "status": "ok",
            "note": None,
        }

    # Merge in categories that have budget rows even if they have zero spend.
    for row in budget_rows:
        category_id = row["category_id"]
        category_name = row["category_name"] or "Uncategorized"
        if category_id not in active:
            active[category_id] = {
                "category_id": category_id,
                "category_name": category_name,
                "budget_amount": None,
                "spent_amount": Decimal("0.00"),
                "remaining_amount": None,
                "used_pct": None,
                "status": "ok",
                "note": None,
            }
        active[category_id]["budget_amount"] = _normalize_amount(row["budget_amount"])

    all_categories: list[dict] = []
    total_spent_amount = Decimal("0.00")

    for item in active.values():
        budget_amount = item["budget_amount"]
        spent_amount = _normalize_amount(item["spent_amount"])
        remaining_amount = (
            quantize_amount(budget_amount - spent_amount)
            if budget_amount is not None
            else None
        )
        used_pct = amount_to_pct_floor(spent_amount, budget_amount)
        status = status_for_used_pct(used_pct)
        note = None

        if status == "over" and remaining_amount is not None and remaining_amount < Decimal("0.00"):
            note = f"Over by {format_money_for_message(-remaining_amount, currency)}"

        normalized_item = {
            "category_id": item["category_id"],
            "category_name": item["category_name"],
            "budget_amount": budget_amount,
            "spent_amount": spent_amount,
            "remaining_amount": remaining_amount,
            "used_pct": used_pct,
            "status": status,
            "note": note,
        }
        all_categories.append(normalized_item)
        total_spent_amount += spent_amount

    sorted_categories = sorted(all_categories, key=_category_sort_key)
    top_categories = sorted_categories[:3]

    # Always include Uncategorized when it has spend for the month.
    uncategorized = next(
        (
            category
            for category in sorted_categories
            if (category["category_id"] is None or category["category_name"] == "Uncategorized")
            and category["spent_amount"] > Decimal("0.00")
        ),
        None,
    )

    if uncategorized is not None and uncategorized not in top_categories:
        if len(top_categories) < 3:
            top_categories.append(uncategorized)
        elif top_categories:
            top_categories[-1] = uncategorized

    normalized_total_budget = (
        _normalize_amount(total_budget_amount)
        if total_budget_amount is not None
        else None
    )

    total_budget_used_pct = 0
    if normalized_total_budget is not None and normalized_total_budget > Decimal("0.00"):
        total_budget_used_pct = int(
            ((total_spent_amount * Decimal("100")) / normalized_total_budget)
            .to_integral_value(rounding=ROUND_FLOOR)
        )

    return (
        {
            "month": month_label(month_start),
            "currency": currency,
            "total_budget_amount": normalized_total_budget,
            "total_spent_amount": quantize_amount(total_spent_amount),
            "total_budget_used_pct": total_budget_used_pct,
            "categories": top_categories,
        },
        all_categories,
    )


def _compute_runway_days(balance_amount: Decimal, burn_rate_amount_per_month: Decimal) -> int | None:
    """Convert monthly burn into runway days with divide-by-zero protection."""
    if burn_rate_amount_per_month <= Decimal("0.00"):
        return None
    per_day = burn_rate_amount_per_month / Decimal("30")
    if per_day <= Decimal("0.00"):
        return None
    days = (balance_amount / per_day).to_integral_value(rounding=ROUND_FLOOR)
    return max(0, int(days))


def build_smart_insights(
    *,
    currency: str,
    total_budget_amount: Decimal | None,
    total_spent_amount: Decimal,
    total_budget_used_pct: int,
    all_categories: list[dict],
    prev_month_spent_amount: Decimal,
    runway_days: int | None,
) -> dict:
    """Generate deterministic 3-5 dashboard insight cards by priority."""
    insights: list[dict] = []

    # Explicit onboarding insight for empty months.
    if total_budget_amount is None and total_spent_amount <= Decimal("0.00") and not all_categories:
        return {
            "insights": [
                {
                    "key": "get_started",
                    "title": "Start Tracking",
                    "message": "Add transactions this month to unlock budget insights.",
                    "severity": "info",
                    "metric": None,
                }
            ]
        }

    # 1) Budget pace insight (only when total monthly budget exists).
    if total_budget_amount is not None and total_budget_amount > Decimal("0.00"):
        if total_budget_used_pct >= 100:
            over_amount = quantize_amount(total_spent_amount - total_budget_amount)
            insights.append(
                {
                    "key": "budget_pace",
                    "title": "Budget Pace",
                    "message": f"You've exceeded your monthly budget by {format_money_for_message(over_amount, currency)}.",
                    "severity": "danger",
                    "metric": {"used_pct": total_budget_used_pct},
                }
            )
        elif total_budget_used_pct >= 80:
            insights.append(
                {
                    "key": "budget_pace",
                    "title": "Budget Pace",
                    "message": f"You've used {total_budget_used_pct}% of your monthly budget.",
                    "severity": "warning",
                    "metric": {"used_pct": total_budget_used_pct},
                }
            )

    # 2) Top category dominance insight.
    if total_spent_amount > Decimal("0.00") and all_categories:
        top_spend_category = max(all_categories, key=lambda item: item["spent_amount"])
        top_spend = _normalize_amount(top_spend_category["spent_amount"])
        dominance_pct = int(
            ((top_spend * Decimal("100")) / total_spent_amount).to_integral_value(rounding=ROUND_FLOOR)
        )
        insights.append(
            {
                "key": "top_category_dominance",
                "title": "Top Category",
                "message": (
                    f"{top_spend_category['category_name']} is your biggest spend at "
                    f"{dominance_pct}% of this month's expenses."
                ),
                "severity": "warning" if dominance_pct >= 50 else "info",
                "metric": {"dominance_pct": dominance_pct},
            }
        )

    # 3) Most over-budget category insight.
    most_over = None
    for category in all_categories:
        used_pct = category["used_pct"]
        if used_pct is None or used_pct <= 100:
            continue
        if most_over is None or used_pct > most_over["used_pct"]:
            most_over = category

    if most_over is not None and most_over["remaining_amount"] is not None:
        over_amount = -most_over["remaining_amount"]
        insights.append(
            {
                "key": "over_budget_category",
                "title": "Category Over Budget",
                "message": (
                    f"{most_over['category_name']} is over budget by "
                    f"{format_money_for_message(over_amount, currency)}."
                ),
                "severity": "danger",
                "metric": {"used_pct": most_over["used_pct"]},
            }
        )

    # 4) Trend vs previous month insight.
    if prev_month_spent_amount > Decimal("0.00"):
        delta = total_spent_amount - prev_month_spent_amount
        direction = "more" if delta >= Decimal("0.00") else "less"
        pct_change = int(
            ((abs(delta) * Decimal("100")) / prev_month_spent_amount).to_integral_value(rounding=ROUND_FLOOR)
        )
        insights.append(
            {
                "key": "month_vs_last_month",
                "title": "Monthly Trend",
                "message": f"You're spending {pct_change}% {direction} than last month.",
                "severity": "warning" if delta >= Decimal("0.00") and pct_change >= 10 else "info",
                "metric": {"pct_change": pct_change},
            }
        )

    # 5) Optional runway insight when computable.
    if runway_days is not None:
        severity = "info"
        if runway_days < 21:
            severity = "danger"
        elif runway_days < 45:
            severity = "warning"
        insights.append(
            {
                "key": "runway",
                "title": "Runway",
                "message": f"At this pace, your money lasts about {runway_days} days.",
                "severity": severity,
                "metric": {"runway_days": runway_days},
            }
        )

    if total_budget_amount is None and total_spent_amount > Decimal("0.00") and len(insights) < 5:
        insights.append(
            {
                "key": "set_budget",
                "title": "Set a Budget",
                "message": "Set a monthly budget to unlock pace and over-budget alerts.",
                "severity": "info",
                "metric": None,
            }
        )

    return {"insights": insights[:5]}


async def get_user_currency(connection: AsyncConnection, user_id: UUID) -> str:
    """Load user base currency; default defensively to CAD if user row is missing."""
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT base_currency FROM users WHERE id = %s", (user_id,))
        row = await cursor.fetchone()

    if row is None:
        return "CAD"
    return row["base_currency"]


async def get_month_total_budget(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> Decimal | None:
    """Fetch monthly total budget for user/month (nullable when unset)."""
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT total_budget_amount
            FROM monthly_budget_totals
            WHERE user_id = %s
              AND month_start = %s
            """,
            (user_id, month_start),
        )
        row = await cursor.fetchone()

    if row is None:
        return None
    return _normalize_amount(row["total_budget_amount"])


async def get_month_spend_by_category(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    month_end_exclusive: date,
) -> list[dict]:
    """Aggregate month expense spend grouped by category."""
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


async def get_month_budgets_by_category(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> list[dict]:
    """Fetch per-category budget limits for the month."""
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                b.category_id,
                COALESCE(c.name, 'Uncategorized') AS category_name,
                b.limit_amount AS budget_amount
            FROM budgets b
            LEFT JOIN categories c ON c.id = b.category_id
            WHERE b.user_id = %s
              AND b.month_start = %s
            """,
            (user_id, month_start),
        )
        rows = await cursor.fetchall()

    return [
        {
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "budget_amount": _normalize_amount(row["budget_amount"]),
        }
        for row in rows
    ]


async def get_prev_month_spend(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> Decimal:
    """Aggregate previous calendar month expense total."""
    prev_month_start = shift_months(month_start, -1)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS spent_amount
            FROM transactions
            WHERE user_id = %s
              AND type = 'expense'
              AND deleted_at IS NULL
              AND occurred_on >= %s
              AND occurred_on < %s
            """,
            (user_id, prev_month_start, month_start),
        )
        row = await cursor.fetchone()

    return _normalize_amount(row["spent_amount"])


async def get_balance_amount(connection: AsyncConnection, user_id: UUID) -> Decimal:
    """All-time balance = total income - total expense."""
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


async def get_three_complete_month_expenses(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> dict[date, Decimal]:
    """Aggregate expense totals for the 3 complete months before `month_start`."""
    start = shift_months(month_start, -3)

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
            (user_id, start, month_start),
        )
        rows = await cursor.fetchall()

    return {row["month_start"]: _normalize_amount(row["expense_total"]) for row in rows}


async def get_dashboard_insights(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    month_end_exclusive: date,
) -> dict:
    """Orchestrate aggregate queries and deterministic insight generation."""
    currency = await get_user_currency(connection, user_id)
    total_budget_amount = await get_month_total_budget(connection, user_id, month_start)
    spend_rows = await get_month_spend_by_category(connection, user_id, month_start, month_end_exclusive)
    budget_rows = await get_month_budgets_by_category(connection, user_id, month_start)

    budget_health, all_categories = build_budget_health(
        month_start=month_start,
        currency=currency,
        total_budget_amount=total_budget_amount,
        spend_rows=spend_rows,
        budget_rows=budget_rows,
    )

    prev_month_spent_amount = await get_prev_month_spend(connection, user_id, month_start)

    runway_days: int | None = None
    balance_amount = await get_balance_amount(connection, user_id)
    expected_months = list_month_starts(shift_months(month_start, -1), 3)
    three_month_totals = await get_three_complete_month_expenses(connection, user_id, month_start)

    # Runway is only included when all previous 3 complete months have spend coverage.
    if expected_months and all(month in three_month_totals for month in expected_months):
        total = sum((three_month_totals[month] for month in expected_months), Decimal("0.00"))
        burn_rate_amount_per_month = quantize_amount(total / Decimal(len(expected_months)))
        runway_days = _compute_runway_days(balance_amount, burn_rate_amount_per_month)

    smart_insights = build_smart_insights(
        currency=currency,
        total_budget_amount=budget_health["total_budget_amount"],
        total_spent_amount=budget_health["total_spent_amount"],
        total_budget_used_pct=budget_health["total_budget_used_pct"],
        all_categories=all_categories,
        prev_month_spent_amount=prev_month_spent_amount,
        runway_days=runway_days,
    )

    return {
        "budget_health": budget_health,
        "smart_insights": smart_insights,
    }

"""Service helpers used by AI tools for transaction creation and compact summaries."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from app.utils import slugify

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    AsyncConnection = Any

TransactionType = Literal["income", "expense"]
GroupBy = Literal["none", "category", "day"]

MONEY_QUANT = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    """Normalize money values to NUMERIC(12,2) precision."""
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _normalize_amount(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return quantize_amount(value)


async def _resolve_visible_category(
    connection: AsyncConnection,
    user_id: UUID,
    category_type: TransactionType,
    category_id: UUID | None,
    category_name: str | None,
) -> dict[str, Any]:
    """Resolve category by id or name/slug with user visibility checks."""
    if category_id is None and not category_name:
        raise ValueError("Provide either category_id or category_name")

    if category_id is not None:
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, name, slug, kind, user_id, is_system
                FROM categories
                WHERE id = %s
                """,
                (category_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            raise ValueError("Category not found")

        if not row["is_system"] and row["user_id"] != user_id:
            raise ValueError("Category is not visible to this user")

        if row["kind"] != category_type:
            raise ValueError("Category kind does not match transaction type")

        return row

    normalized_name = str(category_name).strip()
    if not normalized_name:
        raise ValueError("category_name cannot be empty")

    category_slug = slugify(normalized_name)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, slug, kind, user_id, is_system
            FROM categories
            WHERE kind = %s
              AND (is_system = TRUE OR user_id = %s)
              AND (
                LOWER(name) = LOWER(%s)
                OR slug = %s
              )
            ORDER BY is_system DESC, name ASC
            LIMIT 1
            """,
            (category_type, user_id, normalized_name, category_slug),
        )
        row = await cursor.fetchone()

    if row is None:
        raise ValueError("No matching visible category was found")

    return row


async def create_transaction_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    occurred_on: date,
    transaction_type: TransactionType,
    amount: Decimal,
    category_id: UUID | None,
    category_name: str | None,
    merchant: str | None,
    note: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create one transaction (or preview with `dry_run=True`)."""
    normalized_amount = quantize_amount(amount)
    if normalized_amount <= Decimal("0.00"):
        raise ValueError("Amount must be greater than 0")

    category = await _resolve_visible_category(
        connection,
        user_id,
        transaction_type,
        category_id,
        category_name,
    )

    payload = {
        "type": transaction_type,
        "amount": normalized_amount,
        "occurred_on": occurred_on,
        "category_id": category["id"],
        "category_name": category["name"],
        "merchant": merchant.strip() if merchant else None,
        "note": note.strip() if note else None,
    }

    if dry_run:
        return {
            "created": False,
            "dry_run": True,
            "transaction": payload,
        }

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO transactions (user_id, category_id, type, amount, occurred_on, merchant, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, category_id, type, amount, occurred_on, merchant, note, created_at
            """,
            (
                user_id,
                category["id"],
                transaction_type,
                normalized_amount,
                occurred_on,
                payload["merchant"],
                payload["note"],
            ),
        )
        row = await cursor.fetchone()

    return {
        "created": True,
        "dry_run": False,
        "transaction": {
            "id": row["id"],
            "type": row["type"],
            "amount": quantize_amount(row["amount"]),
            "occurred_on": row["occurred_on"],
            "category_id": row["category_id"],
            "category_name": category["name"],
            "merchant": row["merchant"],
            "note": row["note"],
            "created_at": row["created_at"],
        },
    }


async def get_summary_tool(
    connection: AsyncConnection,
    user_id: UUID,
    *,
    start_date: date,
    end_date: date,
    group_by: GroupBy = "none",
) -> dict[str, Any]:
    """Return compact aggregate summary for a custom date range."""
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    if group_by == "day":
        day_count = (end_date - start_date).days + 1
        if day_count > 31:
            # Guardrail to keep payloads/token use bounded.
            start_date = end_date - timedelta(days=30)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income_total,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expense_total
            FROM transactions
            WHERE user_id = %s
              AND deleted_at IS NULL
              AND occurred_on >= %s
              AND occurred_on <= %s
            """,
            (user_id, start_date, end_date),
        )
        totals_row = await cursor.fetchone()

    income_total = _normalize_amount(totals_row["income_total"])
    expense_total = _normalize_amount(totals_row["expense_total"])
    net_amount = quantize_amount(income_total - expense_total)

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
              AND t.deleted_at IS NULL
              AND t.type = 'expense'
              AND t.occurred_on >= %s
              AND t.occurred_on <= %s
            GROUP BY t.category_id, COALESCE(c.name, 'Uncategorized')
            ORDER BY spent_amount DESC, category_name ASC
            LIMIT 10
            """,
            (user_id, start_date, end_date),
        )
        top_rows = await cursor.fetchall()

    top_categories: list[dict[str, Any]] = []
    for row in top_rows:
        spent_amount = _normalize_amount(row["spent_amount"])
        pct = 0
        if expense_total > Decimal("0.00"):
            pct = int(((spent_amount * Decimal("100")) / expense_total).to_integral_value(rounding=ROUND_HALF_UP))

        top_categories.append(
            {
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "spent_amount": spent_amount,
                "share_pct": pct,
            }
        )

    daily_points: list[dict[str, Any]] = []
    if group_by == "day":
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT
                    occurred_on,
                    COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income_amount,
                    COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expense_amount
                FROM transactions
                WHERE user_id = %s
                  AND deleted_at IS NULL
                  AND occurred_on >= %s
                  AND occurred_on <= %s
                GROUP BY occurred_on
                ORDER BY occurred_on ASC
                """,
                (user_id, start_date, end_date),
            )
            by_day_rows = await cursor.fetchall()

        by_day = {
            row["occurred_on"]: (
                _normalize_amount(row["income_amount"]),
                _normalize_amount(row["expense_amount"]),
            )
            for row in by_day_rows
        }

        cursor_date = start_date
        while cursor_date <= end_date:
            income_amount, expense_amount = by_day.get(cursor_date, (Decimal("0.00"), Decimal("0.00")))
            daily_points.append(
                {
                    "date": cursor_date,
                    "income_amount": income_amount,
                    "expense_amount": expense_amount,
                }
            )
            cursor_date += timedelta(days=1)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "group_by": group_by,
        "income_total": income_total,
        "expense_total": expense_total,
        "net_amount": net_amount,
        "top_categories": top_categories,
        "daily": daily_points,
    }

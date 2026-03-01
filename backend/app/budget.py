from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import AsyncConnection
from pydantic import BaseModel, Field, field_serializer

from .auth import get_current_user_id
from .database import get_db_connection
from .services.budget_allocation import (
    AllocationCategory,
    ExistingBudget,
    compute_regenerated_allocations,
    quantize_money,
)
from .services.budget_dates import month_window, validate_month_start

# Budget endpoints implement monthly total -> per-category allocation flow.
router = APIRouter(tags=["budget"])

ALLOCATION_STRATEGY = "default_weights_v1"


class BudgetCategoryOut(BaseModel):
    category_id: UUID
    category_name: str
    limit_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    is_user_modified: bool

    @field_serializer("limit_amount", "spent_amount", "remaining_amount")
    def serialize_decimal(self, value: Decimal) -> str:
        return _money(value)


class BudgetMonthResponse(BaseModel):
    month_start: date
    total_budget_amount: Decimal | None
    currency: str | None
    allocation_strategy: str | None
    category_budgets: list[BudgetCategoryOut]

    @field_serializer("total_budget_amount", when_used="always")
    def serialize_total(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return _money(value)


class BudgetTotalRequest(BaseModel):
    month_start: date
    total_budget_amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    categories_in_scope: list[UUID] | None = None
    use_active_categories: bool = False
    force_reset: bool = False


class BudgetCategoryUpsertRequest(BaseModel):
    month_start: date
    category_id: UUID
    limit_amount: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)


class BudgetCategoryUpsertResponse(BaseModel):
    month_start: date
    currency: str
    category_id: UUID
    category_name: str
    limit_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    is_user_modified: bool

    @field_serializer("limit_amount", "spent_amount", "remaining_amount")
    def serialize_decimal(self, value: Decimal) -> str:
        return _money(value)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _get_user_currency(connection: AsyncConnection, user_id: UUID) -> str:
    # Currency is copied onto budget rows for historical consistency.
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT base_currency FROM users WHERE id = %s", (user_id,))
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return row["base_currency"]


async def _get_visible_expense_categories(connection: AsyncConnection, user_id: UUID) -> list[dict]:
    # Visible means global system categories + this user's custom categories.
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, slug
            FROM categories
            WHERE kind = 'expense'
              AND (is_system = TRUE OR user_id = %s)
            ORDER BY name ASC
            """,
            (user_id,),
        )
        return await cursor.fetchall()


async def _validate_expense_categories_for_user(
    connection: AsyncConnection,
    user_id: UUID,
    category_ids: list[UUID],
) -> list[dict]:
    # Preserve request order while removing duplicates.
    deduped_ids = list(dict.fromkeys(category_ids))
    if not deduped_ids:
        raise HTTPException(status_code=422, detail="categories_in_scope must not be empty")

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, name, slug, kind, user_id, is_system
            FROM categories
            WHERE id = ANY(%s)
            """,
            (deduped_ids,),
        )
        rows = await cursor.fetchall()

    by_id = {row["id"]: row for row in rows}
    selected: list[dict] = []

    for category_id in deduped_ids:
        row = by_id.get(category_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Category not found: {category_id}")

        if not row["is_system"] and row["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Forbidden category access")

        if row["kind"] != "expense":
            raise HTTPException(status_code=409, detail="Budget allocation supports expense categories only")

        selected.append({"id": row["id"], "name": row["name"], "slug": row["slug"]})

    return selected


async def _resolve_scope(
    connection: AsyncConnection,
    user_id: UUID,
    request: BudgetTotalRequest,
) -> list[dict]:
    # Scope precedence: explicit ids -> recent active categories -> full visible defaults.
    if request.categories_in_scope is not None:
        return await _validate_expense_categories_for_user(connection, user_id, request.categories_in_scope)

    if request.use_active_categories:
        # "Active" = expense categories used in last 60 days.
        cutoff = date.today() - timedelta(days=60)
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT DISTINCT c.id, c.name, c.slug
                FROM transactions t
                JOIN categories c ON c.id = t.category_id
                WHERE t.user_id = %s
                  AND t.type = 'expense'
                  AND t.deleted_at IS NULL
                  AND t.occurred_on >= %s
                  AND c.kind = 'expense'
                  AND (c.is_system = TRUE OR c.user_id = %s)
                ORDER BY c.name ASC
                """,
                (user_id, cutoff, user_id),
            )
            rows = await cursor.fetchall()

        if rows:
            return rows

    return await _get_visible_expense_categories(connection, user_id)


async def _fetch_existing_budgets(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> list[ExistingBudget]:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT category_id, limit_amount, is_user_modified
            FROM budgets
            WHERE user_id = %s
              AND month_start = %s
            """,
            (user_id, month_start),
        )
        rows = await cursor.fetchall()

    return [
        ExistingBudget(
            category_id=row["category_id"],
            limit_amount=quantize_money(row["limit_amount"]),
            is_user_modified=row["is_user_modified"],
        )
        for row in rows
    ]


async def _upsert_generated_budgets(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    currency: str,
    allocations: dict[UUID, Decimal],
) -> None:
    if not allocations:
        return

    rows = [
        (user_id, category_id, month_start, quantize_money(amount), currency)
        for category_id, amount in allocations.items()
    ]

    async with connection.cursor() as cursor:
        await cursor.executemany(
            """
            INSERT INTO budgets (user_id, category_id, month_start, limit_amount, currency, is_user_modified)
            VALUES (%s, %s, %s, %s, %s, FALSE)
            ON CONFLICT (user_id, category_id, month_start)
            DO UPDATE SET
                limit_amount = EXCLUDED.limit_amount,
                currency = EXCLUDED.currency,
                is_user_modified = FALSE
            -- Never overwrite rows manually edited by user.
            WHERE budgets.is_user_modified = FALSE
            """,
            rows,
        )


async def _upsert_month_total(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
    total_budget_amount: Decimal,
    currency: str,
) -> None:
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
            (user_id, month_start, quantize_money(total_budget_amount), currency, ALLOCATION_STRATEGY),
        )


async def _fetch_month_total(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> dict | None:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT total_budget_amount, currency, allocation_strategy
            FROM monthly_budget_totals
            WHERE user_id = %s AND month_start = %s
            """,
            (user_id, month_start),
        )
        return await cursor.fetchone()


async def _fetch_month_budget_rows(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> list[dict]:
    period_start, period_end = month_window(month_start)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            WITH month_spend AS (
                -- Spending snapshot for the target month and user.
                SELECT t.category_id, COALESCE(SUM(t.amount), 0) AS spent_amount
                FROM transactions t
                WHERE t.user_id = %s
                  AND t.type = 'expense'
                  AND t.deleted_at IS NULL
                  AND t.occurred_on BETWEEN %s AND %s
                GROUP BY t.category_id
            )
            SELECT
                b.category_id,
                c.name AS category_name,
                b.limit_amount,
                COALESCE(ms.spent_amount, 0) AS spent_amount,
                b.limit_amount - COALESCE(ms.spent_amount, 0) AS remaining_amount,
                b.is_user_modified,
                b.currency
            FROM budgets b
            JOIN categories c ON c.id = b.category_id
            LEFT JOIN month_spend ms ON ms.category_id = b.category_id
            WHERE b.user_id = %s
              AND b.month_start = %s
            ORDER BY c.name ASC
            """,
            (user_id, period_start, period_end, user_id, month_start),
        )
        return await cursor.fetchall()


async def _fetch_budget_snapshot(
    connection: AsyncConnection,
    user_id: UUID,
    month_start: date,
) -> BudgetMonthResponse:
    total_row = await _fetch_month_total(connection, user_id, month_start)
    rows = await _fetch_month_budget_rows(connection, user_id, month_start)

    category_budgets = [
        BudgetCategoryOut(
            category_id=row["category_id"],
            category_name=row["category_name"],
            limit_amount=quantize_money(row["limit_amount"]),
            spent_amount=quantize_money(row["spent_amount"]),
            remaining_amount=quantize_money(row["remaining_amount"]),
            is_user_modified=row["is_user_modified"],
        )
        for row in rows
    ]

    return BudgetMonthResponse(
        month_start=month_start,
        total_budget_amount=(quantize_money(total_row["total_budget_amount"]) if total_row else None),
        currency=(total_row["currency"] if total_row else None),
        allocation_strategy=(total_row["allocation_strategy"] if total_row else None),
        category_budgets=category_budgets,
    )


@router.post("/budget/total", response_model=BudgetMonthResponse)
async def post_budget_total(
    payload: BudgetTotalRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> BudgetMonthResponse:
    """
    Set one monthly total and auto-allocate category budgets.

    Request example:
    {
      "month_start": "2026-02-01",
      "total_budget_amount": "2000.00",
      "use_active_categories": true
    }

    Response example:
    {
      "month_start": "2026-02-01",
      "total_budget_amount": "2000.00",
      "currency": "CAD",
      "allocation_strategy": "default_weights_v1",
      "category_budgets": [
        {
          "category_id": "...",
          "category_name": "Food",
          "limit_amount": "400.00",
          "spent_amount": "120.50",
          "remaining_amount": "279.50",
          "is_user_modified": false
        }
      ]
    }
    """
    month_start = validate_month_start(payload.month_start)

    async with connection.transaction():
        # Keep total row + regenerated category rows atomic.
        currency = await _get_user_currency(connection, user_id)
        scope_rows = await _resolve_scope(connection, user_id, payload)

        if not scope_rows:
            raise HTTPException(status_code=422, detail="No expense categories available for allocation")

        await _upsert_month_total(
            connection,
            user_id=user_id,
            month_start=month_start,
            total_budget_amount=payload.total_budget_amount,
            currency=currency,
        )

        if payload.force_reset:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "UPDATE budgets SET is_user_modified = FALSE WHERE user_id = %s AND month_start = %s",
                    (user_id, month_start),
                )

        existing_budgets = await _fetch_existing_budgets(connection, user_id, month_start)

        in_scope_categories = [
            AllocationCategory(category_id=row["id"], slug=row["slug"])
            for row in scope_rows
        ]

        regenerated = compute_regenerated_allocations(
            total_budget_amount=quantize_money(payload.total_budget_amount),
            in_scope_categories=in_scope_categories,
            existing_budgets=existing_budgets,
        )

        await _upsert_generated_budgets(
            connection,
            user_id=user_id,
            month_start=month_start,
            currency=currency,
            allocations=regenerated,
        )

    return await _fetch_budget_snapshot(connection, user_id, month_start)


@router.get("/budget", response_model=BudgetMonthResponse)
async def get_budget(
    month_start: date = Query(...),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> BudgetMonthResponse:
    """
    Fetch monthly budget totals and category budgets.

    Response example:
    {
      "month_start": "2026-02-01",
      "total_budget_amount": "2000.00",
      "currency": "CAD",
      "allocation_strategy": "default_weights_v1",
      "category_budgets": []
    }
    """
    month_start = validate_month_start(month_start)
    return await _fetch_budget_snapshot(connection, user_id, month_start)


@router.put("/budget/category", response_model=BudgetCategoryUpsertResponse)
async def put_budget_category(
    payload: BudgetCategoryUpsertRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> BudgetCategoryUpsertResponse:
    """
    Manually override one category budget for a month.

    Request example:
    {
      "month_start": "2026-02-01",
      "category_id": "...",
      "limit_amount": "500.00"
    }

    Response example:
    {
      "month_start": "2026-02-01",
      "currency": "CAD",
      "category_id": "...",
      "category_name": "Food",
      "limit_amount": "500.00",
      "spent_amount": "220.00",
      "remaining_amount": "280.00",
      "is_user_modified": true
    }
    """
    month_start = validate_month_start(payload.month_start)

    # Validation call enforces visibility and expense-only constraints.
    scope_rows = await _validate_expense_categories_for_user(connection, user_id, [payload.category_id])
    _ = scope_rows  # Explicitly acknowledge validation-only usage.
    currency = await _get_user_currency(connection, user_id)

    async with connection.transaction():
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO budgets (user_id, category_id, month_start, limit_amount, currency, is_user_modified)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (user_id, category_id, month_start)
                DO UPDATE SET
                    limit_amount = EXCLUDED.limit_amount,
                    currency = EXCLUDED.currency,
                    -- Manual edit should pin this row from auto-regeneration.
                    is_user_modified = TRUE
                """,
                (user_id, payload.category_id, month_start, quantize_money(payload.limit_amount), currency),
            )

    rows = await _fetch_month_budget_rows(connection, user_id, month_start)
    row = next((item for item in rows if item["category_id"] == payload.category_id), None)

    if row is None:
        raise HTTPException(status_code=404, detail="Budget row not found after update")

    return BudgetCategoryUpsertResponse(
        month_start=month_start,
        currency=row["currency"],
        category_id=row["category_id"],
        category_name=row["category_name"],
        limit_amount=quantize_money(row["limit_amount"]),
        spent_amount=quantize_money(row["spent_amount"]),
        remaining_amount=quantize_money(row["remaining_amount"]),
        is_user_modified=row["is_user_modified"],
    )

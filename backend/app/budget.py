from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
import calendar
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg import AsyncConnection
from pydantic import BaseModel, Field, field_serializer

from .auth import get_current_user_id
from .database import get_db_connection

router = APIRouter(tags=["budget"])

MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class BudgetLimitUpsertRequest(BaseModel):
    monthly_limit: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)


class BudgetLimitResponse(BaseModel):
    category_id: UUID
    category_name: str
    category_slug: str
    monthly_limit: Decimal

    @field_serializer("monthly_limit")
    def serialize_limit(self, value: Decimal) -> str:
        return _money(value)


class BudgetCategorySummary(BaseModel):
    category_id: UUID
    category_name: str
    category_slug: str
    monthly_limit: Decimal | None
    spent: Decimal
    remaining: Decimal | None
    percent_used: Decimal | None
    status: str

    @field_serializer("monthly_limit", "spent", "remaining", "percent_used", when_used="always")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return _money(value)


class BudgetSummaryResponse(BaseModel):
    month: str
    period_start: date
    period_end: date
    categories: list[BudgetCategorySummary]


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _resolve_month_window(month: str | None) -> tuple[str, date, date]:
    if month is None:
        today = date.today()
        year = today.year
        month_num = today.month
    else:
        match = MONTH_PATTERN.fullmatch(month)
        if match is None:
            raise HTTPException(status_code=422, detail="Invalid month format. Use YYYY-MM")
        year = int(match.group(1))
        month_num = int(match.group(2))

    start = date(year, month_num, 1)
    end = date(year, month_num, calendar.monthrange(year, month_num)[1])
    return f"{year:04d}-{month_num:02d}", start, end


async def _fetch_expense_category_for_user(
    connection: AsyncConnection,
    *,
    category_id: UUID,
    user_id: UUID,
) -> dict:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, user_id, kind, is_system
            FROM categories
            WHERE id = %s
            """,
            (category_id,),
        )
        category = await cursor.fetchone()

    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    if not category["is_system"] and category["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden category access")

    if category["kind"] != "expense":
        raise HTTPException(status_code=409, detail="Budget is only supported for expense categories")

    return category


@router.get("/budget/limits", response_model=list[BudgetLimitResponse])
async def get_budget_limits(
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> list[BudgetLimitResponse]:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT bl.category_id, c.name AS category_name, c.slug AS category_slug, bl.monthly_limit
            FROM budget_limits bl
            JOIN categories c ON c.id = bl.category_id
            WHERE bl.user_id = %s
            ORDER BY c.name ASC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

    return [BudgetLimitResponse.model_validate(row) for row in rows]


@router.put("/budget/limits/{category_id}", response_model=BudgetLimitResponse)
async def upsert_budget_limit(
    category_id: UUID,
    payload: BudgetLimitUpsertRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> BudgetLimitResponse:
    await _fetch_expense_category_for_user(connection, category_id=category_id, user_id=user_id)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO budget_limits (user_id, category_id, monthly_limit)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, category_id)
            DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit
            RETURNING category_id, monthly_limit
            """,
            (user_id, category_id, payload.monthly_limit),
        )
        limit_row = await cursor.fetchone()

        await cursor.execute(
            "SELECT name AS category_name, slug AS category_slug FROM categories WHERE id = %s",
            (category_id,),
        )
        category_row = await cursor.fetchone()

    return BudgetLimitResponse(
        category_id=limit_row["category_id"],
        category_name=category_row["category_name"],
        category_slug=category_row["category_slug"],
        monthly_limit=limit_row["monthly_limit"],
    )


@router.delete("/budget/limits/{category_id}", status_code=204)
async def delete_budget_limit(
    category_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> Response:
    await _fetch_expense_category_for_user(connection, category_id=category_id, user_id=user_id)

    async with connection.cursor() as cursor:
        await cursor.execute(
            "DELETE FROM budget_limits WHERE user_id = %s AND category_id = %s",
            (user_id, category_id),
        )

    return Response(status_code=204)


@router.get("/budget/summary", response_model=BudgetSummaryResponse)
async def get_budget_summary(
    month: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> BudgetSummaryResponse:
    resolved_month, period_start, period_end = _resolve_month_window(month)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            WITH visible_expense_categories AS (
                SELECT c.id, c.name, c.slug
                FROM categories c
                WHERE c.kind = 'expense'
                  AND (c.is_system = TRUE OR c.user_id = %s)
            ),
            period_spending AS (
                SELECT t.category_id, COALESCE(SUM(t.amount), 0) AS spent
                FROM transactions t
                WHERE t.user_id = %s
                  AND t.type = 'expense'
                  AND t.deleted_at IS NULL
                  AND t.occurred_on BETWEEN %s AND %s
                GROUP BY t.category_id
            )
            SELECT
                c.id AS category_id,
                c.name AS category_name,
                c.slug AS category_slug,
                bl.monthly_limit,
                COALESCE(ps.spent, 0) AS spent
            FROM visible_expense_categories c
            LEFT JOIN budget_limits bl
              ON bl.user_id = %s AND bl.category_id = c.id
            LEFT JOIN period_spending ps
              ON ps.category_id = c.id
            ORDER BY c.name ASC
            """,
            (user_id, user_id, period_start, period_end, user_id),
        )
        rows = await cursor.fetchall()

    categories: list[BudgetCategorySummary] = []

    for row in rows:
        limit = row["monthly_limit"]
        spent = row["spent"]

        if limit is None:
            remaining = None
            percent_used = None
            status = "no_limit"
        else:
            remaining = limit - spent
            percent_used = (spent / limit) * Decimal("100")

            if percent_used >= Decimal("100"):
                status = "overspent"
            elif percent_used >= Decimal("80"):
                status = "warning"
            else:
                status = "ok"

        categories.append(
            BudgetCategorySummary(
                category_id=row["category_id"],
                category_name=row["category_name"],
                category_slug=row["category_slug"],
                monthly_limit=limit,
                spent=spent,
                remaining=remaining,
                percent_used=percent_used,
                status=status,
            )
        )

    return BudgetSummaryResponse(
        month=resolved_month,
        period_start=period_start,
        period_end=period_end,
        categories=categories,
    )

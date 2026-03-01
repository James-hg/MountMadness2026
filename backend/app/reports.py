from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_serializer

from .auth import get_current_user_id
from .database import get_db_connection
from .services.reports_dates import (
    list_month_starts,
    month_label,
    month_start_end_exclusive,
    parse_month,
)
from .services.reports_service import (
    get_monthly_breakdown,
    get_summary,
    get_top_categories,
    get_trends,
)

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    # Keeps module importable for tests when psycopg is unavailable.
    AsyncConnection = Any

router = APIRouter(prefix="/reports", tags=["reports"])


def _money(value: Decimal) -> str:
    """Serialize Decimal values as fixed 2-decimal strings."""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ReportsSummaryResponse(BaseModel):
    currency: str
    month: str
    month_start: date
    month_end: date
    balance_amount: Decimal
    monthly_spend_amount: Decimal
    burn_rate_amount_per_month: Decimal
    runway_days: int | None

    @field_serializer("balance_amount", "monthly_spend_amount", "burn_rate_amount_per_month")
    def serialize_decimal(self, value: Decimal) -> str:
        return _money(value)


class TopCategoryItem(BaseModel):
    category: str
    spent_amount: Decimal
    percentage: int

    @field_serializer("spent_amount")
    def serialize_decimal(self, value: Decimal) -> str:
        return _money(value)


class TopCategoriesResponse(BaseModel):
    currency: str
    month: str
    items: list[TopCategoryItem]


class TrendItem(BaseModel):
    month: str
    expense_amount: Decimal
    income_amount: Decimal

    @field_serializer("expense_amount", "income_amount")
    def serialize_decimal(self, value: Decimal) -> str:
        return _money(value)


class TrendsResponse(BaseModel):
    currency: str
    items: list[TrendItem]


class DailyBreakdownItem(BaseModel):
    date: date
    expense_amount: Decimal

    @field_serializer("expense_amount")
    def serialize_decimal(self, value: Decimal) -> str:
        return _money(value)


class MonthlyBreakdownResponse(BaseModel):
    currency: str
    month: str
    items: list[DailyBreakdownItem]


@router.get("/summary", response_model=ReportsSummaryResponse)
async def reports_summary(
    month: str | None = Query(default=None, description="YYYY-MM"),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ReportsSummaryResponse:
    """
    Summary cards for reports.

    Example response:
    {
      "currency": "CAD",
      "month": "2026-02",
      "month_start": "2026-02-01",
      "month_end": "2026-02-28",
      "balance_amount": "2400.00",
      "monthly_spend_amount": "870.00",
      "burn_rate_amount_per_month": "900.00",
      "runway_days": 80
    }
    """
    year, month_number = parse_month(month)
    month_start, month_end_exclusive = month_start_end_exclusive(year, month_number)

    data = await get_summary(connection, user_id, month_start, month_end_exclusive)

    return ReportsSummaryResponse(
        currency=data["currency"],
        month=month_label(month_start),
        month_start=month_start,
        month_end=month_end_exclusive - timedelta(days=1),
        balance_amount=data["balance_amount"],
        monthly_spend_amount=data["monthly_spend_amount"],
        burn_rate_amount_per_month=data["burn_rate_amount_per_month"],
        runway_days=data["runway_days"],
    )


@router.get("/top-categories", response_model=TopCategoriesResponse)
async def reports_top_categories(
    month: str | None = Query(default=None, description="YYYY-MM"),
    limit: int = Query(default=5, ge=1, le=20),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> TopCategoriesResponse:
    """
    Top spending categories for one month.

    Example response:
    {
      "currency": "CAD",
      "month": "2026-02",
      "items": [
        {"category": "Housing / Rent", "spent_amount": "1200.00", "percentage": 45}
      ]
    }
    """
    year, month_number = parse_month(month)
    month_start, month_end_exclusive = month_start_end_exclusive(year, month_number)

    data = await get_top_categories(connection, user_id, month_start, month_end_exclusive, limit)

    return TopCategoriesResponse(
        currency=data["currency"],
        month=month_label(month_start),
        items=[TopCategoryItem(**item) for item in data["items"]],
    )


@router.get("/trends", response_model=TrendsResponse)
async def reports_trends(
    months: int = Query(default=6, ge=1, le=24),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> TrendsResponse:
    """
    Expense/income trends for the last N months (including current month), oldest -> newest.

    Example response:
    {
      "currency": "CAD",
      "items": [
        {"month": "2025-09", "expense_amount": "820.00", "income_amount": "1500.00"}
      ]
    }
    """
    today = date.today()
    current_month_start = date(today.year, today.month, 1)
    month_starts = list_month_starts(current_month_start, months)

    data = await get_trends(connection, user_id, month_starts)

    return TrendsResponse(
        currency=data["currency"],
        items=[TrendItem(**item) for item in data["items"]],
    )


@router.get("/monthly-breakdown", response_model=MonthlyBreakdownResponse)
async def reports_monthly_breakdown(
    month: str | None = Query(default=None, description="YYYY-MM"),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> MonthlyBreakdownResponse:
    """
    Daily expense totals for one month.

    Example response:
    {
      "currency": "CAD",
      "month": "2026-02",
      "items": [
        {"date": "2026-02-01", "expense_amount": "23.00"}
      ]
    }
    """
    year, month_number = parse_month(month)
    month_start, month_end_exclusive = month_start_end_exclusive(year, month_number)

    data = await get_monthly_breakdown(connection, user_id, month_start, month_end_exclusive)

    return MonthlyBreakdownResponse(
        currency=data["currency"],
        month=month_label(month_start),
        items=[DailyBreakdownItem(**item) for item in data["items"]],
    )

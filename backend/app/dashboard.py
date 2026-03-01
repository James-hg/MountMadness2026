from __future__ import annotations
"""
Dashboard API router.

Fetch and display:

- budget progress (current budget progress)
- top 3 most used categories
- smart insights
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_serializer

from .auth import get_current_user_id
from .database import get_db_connection
from .services.dashboard_insights import get_dashboard_insights
from .services.reports_dates import month_start_end_exclusive, parse_month

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    AsyncConnection = Any

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _money(value: Decimal) -> str:
    """Serialize Decimal values to fixed 2-decimal amount strings."""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class BudgetHealthCategory(BaseModel):
    """Category row used by dashboard budget progress bars."""
    category_id: UUID | None
    category_name: str
    budget_amount: Decimal | None
    spent_amount: Decimal
    remaining_amount: Decimal | None
    used_pct: int | None
    status: Literal["ok", "warning", "over"]
    note: str | None

    @field_serializer("budget_amount", "spent_amount", "remaining_amount", when_used="always")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return _money(value)


class BudgetHealthResponse(BaseModel):
    """Top-level budget health section for one month."""
    month: str
    currency: str
    total_budget_amount: Decimal | None
    total_spent_amount: Decimal
    total_budget_used_pct: int
    categories: list[BudgetHealthCategory]

    @field_serializer("total_budget_amount", "total_spent_amount", when_used="always")
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return _money(value)


class InsightItem(BaseModel):
    """Deterministic insight card metadata and message."""
    key: str
    title: str
    message: str
    severity: Literal["info", "warning", "danger"]
    metric: dict[str, int | float | str] | None = None


class SmartInsightsResponse(BaseModel):
    """Container for dashboard insight cards."""
    insights: list[InsightItem]


class DashboardInsightsResponse(BaseModel):
    """Full dashboard response contract expected by frontend."""
    budget_health: BudgetHealthResponse
    smart_insights: SmartInsightsResponse


@router.get("/insights", response_model=DashboardInsightsResponse)
async def dashboard_insights(
    month: str | None = Query(default=None, description="YYYY-MM"),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> DashboardInsightsResponse:
    """
    Return Budget Health and Smart Insights for dashboard cards under the main chart.

    Example response:
    {
      "budget_health": {
        "month": "2026-03",
        "currency": "CAD",
        "total_budget_amount": "2000.00",
        "total_spent_amount": "1432.40",
        "total_budget_used_pct": 71,
        "categories": [
          {
            "category_id": "00000000-0000-0000-0000-000000000001",
            "category_name": "Food",
            "budget_amount": "500.00",
            "spent_amount": "420.00",
            "remaining_amount": "80.00",
            "used_pct": 84,
            "status": "warning",
            "note": null
          }
        ]
      },
      "smart_insights": {
        "insights": [
          {
            "key": "budget_pace",
            "title": "Budget Pace",
            "message": "You've used 71% of your monthly budget.",
            "severity": "warning",
            "metric": {"used_pct": 71}
          }
        ]
      }
    }
    """
    # Reuse shared YYYY-MM parsing + month window helpers for consistency with reports.
    year, month_number = parse_month(month)
    month_start, month_end_exclusive = month_start_end_exclusive(
        year, month_number)

    payload = await get_dashboard_insights(connection, user_id, month_start, month_end_exclusive)
    return DashboardInsightsResponse.model_validate(payload)

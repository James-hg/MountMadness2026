import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services import insights_service


def _run(coro):
    return asyncio.run(coro)


class RowsCursor:
    def __init__(self, rows):
        self.rows = rows
        self._rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None):
        self._rows = list(self.rows)

    async def fetchall(self):
        return list(self._rows)


class RowsConnection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return RowsCursor(self.rows)


def test_compare_category_trend_respects_lookback_bounds(monkeypatch) -> None:
    user_id = uuid4()
    food_id = uuid4()

    async def fake_month_spend(connection, user_id_arg, month_start_arg, month_end_arg):
        return [
            {
                "category_id": food_id,
                "category_name": "Food",
                "category_slug": "food",
                "spent_amount": Decimal("300.00"),
            }
        ]

    monkeypatch.setattr(insights_service, "_month_expense_by_category", fake_month_spend)

    connection = RowsConnection(
        [
            {
                "category_id": food_id,
                "category_name": "Food",
                "category_slug": "food",
                "total_amount": Decimal("600.00"),
            }
        ]
    )

    result = _run(
        insights_service.compare_category_trend_tool(
            connection,
            user_id,
            month_start=date(2026, 3, 1),
            lookback_months=30,
        )
    )

    assert result["lookback_months"] == 12
    assert result["items"][0]["category_name"] == "Food"
    assert result["items"][0]["average_amount"] == Decimal("50.00")


def test_detect_anomalies_avg_3m_path(monkeypatch) -> None:
    user_id = uuid4()
    food_id = uuid4()

    async def fake_month_spend(connection, user_id_arg, month_start_arg, month_end_arg):
        return [
            {
                "category_id": food_id,
                "category_name": "Food",
                "category_slug": "food",
                "spent_amount": Decimal("260.00"),
            }
        ]

    monkeypatch.setattr(insights_service, "_month_expense_by_category", fake_month_spend)

    connection = RowsConnection(
        [
            {"category_id": food_id, "total_amount": Decimal("300.00")},
        ]
    )

    result = _run(
        insights_service.detect_anomalies_tool(
            connection,
            user_id,
            month_start=date(2026, 3, 1),
            compare_to="avg_3m",
        )
    )

    assert result["compare_to"] == "avg_3m"
    assert len(result["items"]) == 1
    assert result["items"][0]["pct_increase"] >= 100


def test_fixed_variable_breakdown(monkeypatch) -> None:
    user_id = uuid4()

    connection = RowsConnection(
        [
            {"slug": "housing_rent", "spent_amount": Decimal("900.00")},
            {"slug": "food", "spent_amount": Decimal("300.00")},
            {"slug": "transport", "spent_amount": Decimal("100.00")},
        ]
    )

    result = _run(
        insights_service.get_fixed_variable_breakdown_tool(
            connection,
            user_id,
            month_start=date(2026, 3, 1),
            fixed_categories=["housing_rent", "transport"],
        )
    )

    assert result["fixed_total_amount"] == Decimal("1000.00")
    assert result["variable_total_amount"] == Decimal("300.00")
    assert result["fixed_pct"] == 76


def test_project_future_uses_summary_burn(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_get_summary(connection, user_id_arg, month_start_arg, month_end_arg):
        return {
            "currency": "CAD",
            "balance_amount": Decimal("3000.00"),
            "monthly_spend_amount": Decimal("900.00"),
            "burn_rate_amount_per_month": Decimal("600.00"),
            "runway_days": 150,
        }

    monkeypatch.setattr(insights_service, "get_summary", fake_get_summary)

    result = _run(
        insights_service.project_future_tool(
            connection=object(),
            user_id=user_id,
            months_ahead=3,
        )
    )

    assert result["projected_spend_amount"] == Decimal("1800.00")
    assert result["projected_balance_amount"] == Decimal("1200.00")


def test_plan_savings_goal_generates_cut_suggestions(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_month_spend(connection, user_id_arg, month_start_arg, month_end_arg):
        return [
            {
                "category_id": uuid4(),
                "category_name": "Food",
                "category_slug": "food",
                "spent_amount": Decimal("500.00"),
            },
            {
                "category_id": uuid4(),
                "category_name": "Shopping",
                "category_slug": "shopping",
                "spent_amount": Decimal("250.00"),
            },
        ]

    async def fake_month_total(connection, user_id_arg, month_start_arg, month_end_arg):
        return Decimal("750.00")

    async def fake_health(connection, user_id_arg, month_start):
        return {
            "balance_amount": Decimal("2000.00"),
            "runway_days": 90,
            "currency": "CAD",
            "monthly_spend_amount": Decimal("750.00"),
            "burn_rate_amount_per_month": Decimal("700.00"),
            "budget_used_pct": 50,
            "month": "2026-03",
            "total_budget_amount": Decimal("1500.00"),
            "top_category": None,
        }

    monkeypatch.setattr(insights_service, "_month_expense_by_category", fake_month_spend)
    monkeypatch.setattr(insights_service, "_month_expense_total", fake_month_total)
    monkeypatch.setattr(insights_service, "get_financial_health_snapshot_tool", fake_health)

    result = _run(
        insights_service.plan_savings_goal_tool(
            connection=object(),
            user_id=user_id,
            target_amount=Decimal("800.00"),
            months=4,
            month_start=date(2026, 3, 1),
        )
    )

    assert result["required_monthly_savings_amount"] == Decimal("200.00")
    assert len(result["suggested_cuts"]) >= 1
    assert result["current_balance_amount"] == Decimal("2000.00")

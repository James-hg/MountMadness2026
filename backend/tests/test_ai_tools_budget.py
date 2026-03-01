import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services import budget_service


def _run(coro):
    return asyncio.run(coro)


def test_suggest_budget_output_shape(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_categories(connection, user_id_arg):
        assert user_id_arg == user_id
        return [
            {"id": uuid4(), "name": "Housing / Rent", "slug": "housing_rent", "is_system": True, "user_id": None},
            {"id": uuid4(), "name": "Transport", "slug": "transport", "is_system": True, "user_id": None},
            {"id": uuid4(), "name": "Food", "slug": "food", "is_system": True, "user_id": None},
        ]

    async def fake_derive_total(connection, user_id_arg, month_start_arg):
        assert month_start_arg == date(2026, 3, 1)
        return Decimal("1200.00")

    async def fake_currency(connection, user_id_arg):
        return "CAD"

    monkeypatch.setattr(budget_service, "_get_visible_expense_categories", fake_categories)
    monkeypatch.setattr(budget_service, "_derive_total_budget_amount", fake_derive_total)
    monkeypatch.setattr(budget_service, "_get_user_currency", fake_currency)

    result = _run(
        budget_service.suggest_budget_tool(
            connection=object(),
            user_id=user_id,
            month_start=date(2026, 3, 1),
            total_budget_amount=None,
            fixed_overrides=None,
        )
    )

    assert result["month_start"] == date(2026, 3, 1)
    assert result["strategy"] == "default_weights_v1"
    assert result["currency"] == "CAD"
    assert len(result["allocations"]) == 3
    assert sum(item["limit_amount"] for item in result["allocations"]) == Decimal("1200.00")


class ApplyCursor:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None):
        self.connection.executed.append(("execute", " ".join(query.split()), params))

    async def executemany(self, query, seq_of_params):
        self.connection.executed.append(("executemany", " ".join(query.split()), list(seq_of_params)))


class ApplyTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class ApplyConnection:
    def __init__(self):
        self.executed = []

    def cursor(self):
        return ApplyCursor(self)

    def transaction(self):
        return ApplyTransaction()


def test_apply_budget_plan_upserts_total_and_rows(monkeypatch) -> None:
    user_id = uuid4()
    cat_food = uuid4()
    cat_transport = uuid4()

    async def fake_resolve(connection, user_id_arg, category_id_arg, category_name_arg):
        if category_name_arg == "Food":
            return {"id": cat_food, "name": "Food", "slug": "food"}
        if category_name_arg == "Transport":
            return {"id": cat_transport, "name": "Transport", "slug": "transport"}
        raise ValueError("unknown category")

    async def fake_currency(connection, user_id_arg):
        return "CAD"

    monkeypatch.setattr(budget_service, "_resolve_expense_category", fake_resolve)
    monkeypatch.setattr(budget_service, "_get_user_currency", fake_currency)

    connection = ApplyConnection()
    result = _run(
        budget_service.apply_budget_plan_tool(
            connection,
            user_id,
            month_start=date(2026, 3, 1),
            allocations=[
                {"category_name": "Food", "limit_amount": "500.00"},
                {"category_name": "Transport", "limit_amount": "200.00"},
            ],
            dry_run=False,
        )
    )

    assert result["total_budget_amount"] == Decimal("700.00")
    assert result["dry_run"] is False
    assert len(result["applied"]) == 2
    assert any(item[0] == "execute" and "INSERT INTO monthly_budget_totals" in item[1] for item in connection.executed)
    assert any(item[0] == "executemany" and "INSERT INTO budgets" in item[1] for item in connection.executed)


class SimulateCursor:
    def __init__(self):
        self._rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None):
        normalized = " ".join(query.split())
        if "SELECT limit_amount FROM budgets" in normalized:
            self._rows = [{"limit_amount": Decimal("300.00")}]
            return
        if "SELECT COALESCE(SUM(amount), 0) AS category_spend" in normalized:
            self._rows = [{"category_spend": Decimal("180.00")}]
            return
        raise AssertionError(f"Unexpected query: {normalized}")

    async def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]


class SimulateConnection:
    def cursor(self):
        return SimulateCursor()


def test_simulate_budget_change_outputs_projection(monkeypatch) -> None:
    user_id = uuid4()
    category_id = uuid4()

    async def fake_resolve(connection, user_id_arg, category_id_arg, category_name_arg):
        return {"id": category_id, "name": "Food", "slug": "food"}

    async def fake_monthly_expense(connection, user_id_arg, month_start_arg, month_end_arg):
        return Decimal("1200.00")

    async def fake_three_month_avg(connection, user_id_arg, month_start_arg):
        return Decimal("900.00")

    async def fake_balance(connection, user_id_arg):
        return Decimal("3000.00")

    monkeypatch.setattr(budget_service, "_resolve_expense_category", fake_resolve)
    monkeypatch.setattr(budget_service, "_monthly_expense", fake_monthly_expense)
    monkeypatch.setattr(budget_service, "_three_complete_month_avg_expense", fake_three_month_avg)
    monkeypatch.setattr(budget_service, "_all_time_balance", fake_balance)

    result = _run(
        budget_service.simulate_budget_change_tool(
            SimulateConnection(),
            user_id,
            month_start=date(2026, 3, 1),
            category_id=category_id,
            delta_amount=Decimal("-50.00"),
        )
    )

    assert result["category_name"] == "Food"
    assert result["current_limit_amount"] == Decimal("300.00")
    assert result["projected_limit_amount"] == Decimal("250.00")
    assert result["projected_burn_amount_per_month"] == Decimal("850.00")
    assert result["runway_days_after"] is not None

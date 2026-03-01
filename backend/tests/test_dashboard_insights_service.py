from datetime import date
from decimal import Decimal
from uuid import UUID

from app.services.dashboard_insights import build_budget_health, build_smart_insights


def _id(value: str) -> UUID:
    return UUID(value)


def test_no_data_returns_starter_insight() -> None:
    budget_health, all_categories = build_budget_health(
        month_start=date(2026, 3, 1),
        currency="CAD",
        total_budget_amount=None,
        spend_rows=[],
        budget_rows=[],
    )

    insights = build_smart_insights(
        currency="CAD",
        total_budget_amount=budget_health["total_budget_amount"],
        total_spent_amount=budget_health["total_spent_amount"],
        total_budget_used_pct=budget_health["total_budget_used_pct"],
        all_categories=all_categories,
        prev_month_spent_amount=Decimal("0.00"),
        runway_days=None,
    )

    assert budget_health["categories"] == []
    assert budget_health["total_spent_amount"] == Decimal("0.00")
    assert budget_health["total_budget_used_pct"] == 0
    assert len(insights["insights"]) == 1
    assert insights["insights"][0]["key"] == "get_started"


def test_budget_health_used_pct_status_and_remaining() -> None:
    spend_rows = [
        {"category_id": _id("00000000-0000-0000-0000-000000000001"), "category_name": "Food", "spent_amount": Decimal("420.00")},
        {"category_id": _id("00000000-0000-0000-0000-000000000002"), "category_name": "Housing / Rent", "spent_amount": Decimal("1200.00")},
        {"category_id": _id("00000000-0000-0000-0000-000000000003"), "category_name": "Entertainment", "spent_amount": Decimal("100.00")},
    ]
    budget_rows = [
        {"category_id": _id("00000000-0000-0000-0000-000000000001"), "category_name": "Food", "budget_amount": Decimal("500.00")},
        {"category_id": _id("00000000-0000-0000-0000-000000000002"), "category_name": "Housing / Rent", "budget_amount": Decimal("1000.00")},
    ]

    budget_health, _ = build_budget_health(
        month_start=date(2026, 3, 1),
        currency="CAD",
        total_budget_amount=Decimal("2000.00"),
        spend_rows=spend_rows,
        budget_rows=budget_rows,
    )

    by_name = {item["category_name"]: item for item in budget_health["categories"]}

    assert budget_health["total_budget_used_pct"] == 86

    food = by_name["Food"]
    assert food["used_pct"] == 84
    assert food["status"] == "warning"
    assert food["remaining_amount"] == Decimal("80.00")

    housing = by_name["Housing / Rent"]
    assert housing["used_pct"] == 120
    assert housing["status"] == "over"
    assert housing["remaining_amount"] == Decimal("-200.00")
    assert housing["note"] == "Over by $200.00"


def test_missing_budget_row_sets_used_pct_null() -> None:
    budget_health, _ = build_budget_health(
        month_start=date(2026, 3, 1),
        currency="CAD",
        total_budget_amount=None,
        spend_rows=[
            {"category_id": _id("00000000-0000-0000-0000-000000000010"), "category_name": "Transport", "spent_amount": Decimal("140.00")},
        ],
        budget_rows=[],
    )

    category = budget_health["categories"][0]
    assert category["budget_amount"] is None
    assert category["used_pct"] is None
    assert category["status"] == "ok"
    assert category["remaining_amount"] is None


def test_over_budget_insight_is_generated() -> None:
    all_categories = [
        {
            "category_id": _id("00000000-0000-0000-0000-000000000021"),
            "category_name": "Food",
            "budget_amount": Decimal("300.00"),
            "spent_amount": Decimal("450.00"),
            "remaining_amount": Decimal("-150.00"),
            "used_pct": 150,
            "status": "over",
            "note": "Over by $150.00",
        }
    ]

    insights = build_smart_insights(
        currency="CAD",
        total_budget_amount=Decimal("1000.00"),
        total_spent_amount=Decimal("1200.00"),
        total_budget_used_pct=120,
        all_categories=all_categories,
        prev_month_spent_amount=Decimal("0.00"),
        runway_days=None,
    )

    keys = [item["key"] for item in insights["insights"]]
    assert "budget_pace" in keys
    assert "over_budget_category" in keys


def test_trend_vs_last_month_computes_more_warning() -> None:
    insights = build_smart_insights(
        currency="CAD",
        total_budget_amount=None,
        total_spent_amount=Decimal("1100.00"),
        total_budget_used_pct=0,
        all_categories=[
            {
                "category_id": _id("00000000-0000-0000-0000-000000000031"),
                "category_name": "Food",
                "budget_amount": None,
                "spent_amount": Decimal("1100.00"),
                "remaining_amount": None,
                "used_pct": None,
                "status": "ok",
                "note": None,
            }
        ],
        prev_month_spent_amount=Decimal("1000.00"),
        runway_days=None,
    )

    trend = next(item for item in insights["insights"] if item["key"] == "month_vs_last_month")
    assert trend["severity"] == "warning"
    assert "10% more" in trend["message"]


def test_uncategorized_is_included_even_if_not_in_top_three() -> None:
    spend_rows = [
        {"category_id": _id("00000000-0000-0000-0000-000000000041"), "category_name": "Food", "spent_amount": Decimal("900.00")},
        {"category_id": _id("00000000-0000-0000-0000-000000000042"), "category_name": "Housing / Rent", "spent_amount": Decimal("800.00")},
        {"category_id": _id("00000000-0000-0000-0000-000000000043"), "category_name": "Transport", "spent_amount": Decimal("700.00")},
        {"category_id": None, "category_name": "Uncategorized", "spent_amount": Decimal("50.00")},
    ]
    budget_rows = [
        {"category_id": _id("00000000-0000-0000-0000-000000000041"), "category_name": "Food", "budget_amount": Decimal("1000.00")},
        {"category_id": _id("00000000-0000-0000-0000-000000000042"), "category_name": "Housing / Rent", "budget_amount": Decimal("900.00")},
        {"category_id": _id("00000000-0000-0000-0000-000000000043"), "category_name": "Transport", "budget_amount": Decimal("800.00")},
    ]

    budget_health, _ = build_budget_health(
        month_start=date(2026, 3, 1),
        currency="CAD",
        total_budget_amount=Decimal("3000.00"),
        spend_rows=spend_rows,
        budget_rows=budget_rows,
    )

    assert len(budget_health["categories"]) == 3
    assert any(item["category_name"] == "Uncategorized" for item in budget_health["categories"])

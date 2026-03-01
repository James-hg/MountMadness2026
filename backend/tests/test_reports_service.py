from datetime import date
from decimal import Decimal

from app.services.reports_service import (
    build_trend_series,
    compute_runway_days,
    quantize_amount,
    select_burn_rate_amount,
)


def test_no_transactions_like_behavior_zero_burn_and_null_runway() -> None:
    burn = select_burn_rate_amount(
        three_month_totals={},
        expected_months=[date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)],
        fallback_30_day_expense=Decimal("0.00"),
        fallback_days=30,
    )
    assert burn == Decimal("0.00")
    assert compute_runway_days(Decimal("1000.00"), burn) is None


def test_only_income_like_behavior_positive_balance_still_null_runway_with_zero_burn() -> None:
    # Burn remains zero because no expense data.
    burn = Decimal("0.00")
    runway = compute_runway_days(Decimal("2500.00"), burn)
    assert runway is None


def test_burn_prefers_three_complete_months_when_all_present() -> None:
    months = [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)]
    burn = select_burn_rate_amount(
        three_month_totals={
            months[0]: Decimal("900.00"),
            months[1]: Decimal("1200.00"),
            months[2]: Decimal("600.00"),
        },
        expected_months=months,
        fallback_30_day_expense=Decimal("50.00"),
        fallback_days=30,
    )
    assert burn == Decimal("900.00")


def test_burn_falls_back_when_months_missing() -> None:
    burn = select_burn_rate_amount(
        three_month_totals={date(2026, 1, 1): Decimal("800.00")},
        expected_months=[date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)],
        fallback_30_day_expense=Decimal("300.00"),
        fallback_days=30,
    )
    assert burn == Decimal("300.00")


def test_runway_days_calculation_and_low_burn_guard() -> None:
    assert compute_runway_days(Decimal("2400.00"), Decimal("900.00")) == 80
    assert compute_runway_days(Decimal("2400.00"), Decimal("0.29")) is None


def test_trend_series_order_and_zero_filling() -> None:
    months = [date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]
    items = build_trend_series(
        months,
        {
            date(2026, 1, 1): (Decimal("820.00"), Decimal("1500.00")),
        },
    )

    assert items[0] == {
        "month": "2025-12",
        "expense_amount": Decimal("0.00"),
        "income_amount": Decimal("0.00"),
    }
    assert items[1] == {
        "month": "2026-01",
        "expense_amount": Decimal("820.00"),
        "income_amount": Decimal("1500.00"),
    }
    assert items[2] == {
        "month": "2026-02",
        "expense_amount": Decimal("0.00"),
        "income_amount": Decimal("0.00"),
    }


def test_quantize_amount_deterministic_rounding() -> None:
    assert quantize_amount(Decimal("12.345")) == Decimal("12.35")
    assert quantize_amount(Decimal("12.344")) == Decimal("12.34")

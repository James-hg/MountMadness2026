from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.budget_allocation import quantize_money
from app.services.budget_dates import month_window, validate_month_start


def test_validate_month_start_accepts_first_day() -> None:
    assert validate_month_start(date(2026, 2, 1)) == date(2026, 2, 1)


def test_validate_month_start_rejects_non_first_day() -> None:
    with pytest.raises(HTTPException):
        validate_month_start(date(2026, 2, 2))


def test_month_window_matches_calendar_month() -> None:
    start, end = month_window(date(2026, 2, 1))
    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)


def test_remaining_can_be_negative_when_overspent() -> None:
    limit_amount = Decimal("100.00")
    spent_amount = Decimal("140.00")
    remaining_amount = quantize_money(limit_amount - spent_amount)

    assert remaining_amount == Decimal("-40.00")

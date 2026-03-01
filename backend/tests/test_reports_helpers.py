from datetime import date

import pytest
from fastapi import HTTPException

from app.services.reports_dates import (
    list_month_starts,
    month_label,
    month_start_end_exclusive,
    parse_month,
    shift_months,
)


def test_parse_month_valid_and_default() -> None:
    assert parse_month("2026-02") == (2026, 2)
    assert parse_month(None, today=date(2026, 3, 5)) == (2026, 3)


def test_parse_month_invalid_raises_422() -> None:
    with pytest.raises(HTTPException):
        parse_month("2026/02")
    with pytest.raises(HTTPException):
        parse_month("2026-13")
    with pytest.raises(HTTPException):
        parse_month("26-02")


def test_month_bounds_handle_leap_year() -> None:
    start, end_exclusive = month_start_end_exclusive(2024, 2)
    assert start == date(2024, 2, 1)
    assert end_exclusive == date(2024, 3, 1)


def test_shift_months_year_boundary() -> None:
    assert shift_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert shift_months(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_list_month_starts_order_oldest_to_newest() -> None:
    months = list_month_starts(date(2026, 2, 1), 4)
    assert months == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert [month_label(m) for m in months] == ["2025-11", "2025-12", "2026-01", "2026-02"]

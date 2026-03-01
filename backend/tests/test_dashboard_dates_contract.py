from datetime import date

import pytest
from fastapi import HTTPException

from app.services.reports_dates import month_start_end_exclusive, parse_month


def test_dashboard_month_parser_valid_and_default() -> None:
    assert parse_month("2026-03") == (2026, 3)
    assert parse_month(None, today=date(2026, 3, 15)) == (2026, 3)


def test_dashboard_month_parser_invalid() -> None:
    with pytest.raises(HTTPException):
        parse_month("2026/03")
    with pytest.raises(HTTPException):
        parse_month("26-03")
    with pytest.raises(HTTPException):
        parse_month("2026-13")


def test_dashboard_month_window_exclusive_end() -> None:
    start, end_exclusive = month_start_end_exclusive(2026, 2)
    assert start == date(2026, 2, 1)
    assert end_exclusive == date(2026, 3, 1)

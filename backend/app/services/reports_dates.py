from __future__ import annotations

from datetime import date

from fastapi import HTTPException


def parse_month(month: str | None, *, today: date | None = None) -> tuple[int, int]:
    """Parse YYYY-MM; default to the current month when omitted."""
    if month is None:
        current = today or date.today()
        return current.year, current.month

    parts = month.split("-")
    if len(parts) != 2:
        raise HTTPException(status_code=422, detail="Expected YYYY-MM")

    year_text, month_text = parts
    if len(year_text) != 4 or len(month_text) != 2 or not year_text.isdigit() or not month_text.isdigit():
        raise HTTPException(status_code=422, detail="Expected YYYY-MM")

    year = int(year_text)
    month_number = int(month_text)

    if month_number < 1 or month_number > 12:
        raise HTTPException(status_code=422, detail="Expected YYYY-MM")

    return year, month_number


def month_start_end_exclusive(year: int, month: int) -> tuple[date, date]:
    """Build [month_start, next_month_start) boundaries."""
    month_start = date(year, month, 1)
    month_end_exclusive = shift_months(month_start, 1)
    return month_start, month_end_exclusive


def month_label(month_start: date) -> str:
    """Render month start date as YYYY-MM."""
    return f"{month_start.year:04d}-{month_start.month:02d}"


def shift_months(month_start: date, offset: int) -> date:
    # Normalize any input date to month start for stable month arithmetic.
    year = month_start.year
    month_number = month_start.month

    absolute_index = (year * 12 + (month_number - 1)) + offset
    next_year, month_zero_based = divmod(absolute_index, 12)
    return date(next_year, month_zero_based + 1, 1)


def list_month_starts(end_month_start: date, count: int) -> list[date]:
    """Return `count` month starts ending at `end_month_start`, oldest first."""
    if count < 1:
        return []

    oldest = shift_months(end_month_start, -(count - 1))
    return [shift_months(oldest, i) for i in range(count)]

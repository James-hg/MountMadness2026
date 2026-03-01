from datetime import date
import calendar

from fastapi import HTTPException


def validate_month_start(month_start: date) -> date:
    # Budget rows are keyed by canonical month start only.
    if month_start.day != 1:
        raise HTTPException(status_code=422, detail="month_start must be the first day of month (YYYY-MM-01)")
    return month_start


def month_window(month_start: date) -> tuple[date, date]:
    # Inclusive window used for monthly spending aggregation.
    month_end = date(month_start.year, month_start.month, calendar.monthrange(month_start.year, month_start.month)[1])
    return month_start, month_end

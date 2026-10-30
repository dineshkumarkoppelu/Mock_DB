"""Date helpers used by the seed generator."""

from __future__ import annotations

import calendar
from datetime import date


def month_bounds(d: date) -> tuple[date, date]:
    """First and last day of d's month."""
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def subtract_months(d: date, months: int) -> date:
    """d minus whole months, clamping the day to the target month's length."""
    index = d.year * 12 + (d.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))

from datetime import date, datetime, timedelta


def _to_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def workday(start, days: int, holidays: set) -> date:
    """Reimplementation of Excel's WORKDAY(start, days, holidays).

    Moves `days` working days from `start`, skipping weekends and any date
    present in `holidays`. Negative `days` moves backwards. The start date
    itself is never counted or returned as-is.
    """
    current = _to_date(start)
    step = -1 if days < 0 else 1
    remaining = abs(days)
    while remaining > 0:
        current += timedelta(days=step)
        if current.weekday() < 5 and current not in holidays:
            remaining -= 1
    return current


def safe_workday(start, days: int, holidays: set):
    """Mirrors =IFERROR(WORKDAY(...), "") -- returns None if start is missing/invalid."""
    if not start:
        return None
    try:
        return workday(start, days, holidays)
    except (ValueError, TypeError):
        return None


def iso_week(start) -> int:
    """Week Due = ISO week number of the Shipping Date."""
    if not start:
        return None
    return _to_date(start).isocalendar()[1]


def compute_stage_dates(shipping_date, holidays: set) -> dict:
    """Make/Press = 2 workdays before shipping; CNC = 1 workday before shipping."""
    return {
        "make": safe_workday(shipping_date, -2, holidays),
        "press": safe_workday(shipping_date, -2, holidays),
        "cnc": safe_workday(shipping_date, -1, holidays),
        "week_due": iso_week(shipping_date),
    }

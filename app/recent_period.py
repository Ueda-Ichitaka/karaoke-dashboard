"""About me: the "What's new" period - how far back the "Recently added" and
"Recently updated" lists on /new reach (app/routes/songs.py), set on the
admin Settings page as a whole number of a unit (AppSettings.recent_amount,
recent_unit). period_start() turns it into the exact moment the lists start
from, keeping the time of day. Each unit is one entry in _UNITS, so another
one (e.g. hours: timedelta(hours=amount)) only needs adding there.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import datetime, timedelta

DEFAULT_AMOUNT = 2
DEFAULT_UNIT = "months"
MAX_AMOUNT = 999


def months_before(moment: datetime, months: int) -> datetime:
    """The same day and time "months" calendar months earlier, clamped to
    the end of a shorter month (30 April minus 2 months is 28 February)."""
    month_index = moment.year * 12 + moment.month - 1 - months
    year, month = divmod(month_index, 12)
    day = min(moment.day, calendar.monthrange(year, month + 1)[1])
    return moment.replace(year=year, month=month + 1, day=day)


# code: (label on the Settings page, singular, start of the period)
_UNITS: dict[str, tuple[str, str, Callable[[datetime, int], datetime]]] = {
    "days": ("Days", "day", lambda now, amount: now - timedelta(days=amount)),
    "weeks": ("Weeks", "week", lambda now, amount: now - timedelta(weeks=amount)),
    "months": ("Months", "month", months_before),
}

UNIT_CHOICES: tuple[tuple[str, str], ...] = tuple((code, label) for code, (label, _, _) in _UNITS.items())


def is_valid_unit(unit: str) -> bool:
    return unit in _UNITS


def period_start(now: datetime, amount: int, unit: str) -> datetime:
    """The moment "amount" units before "now"."""
    return _UNITS[unit][2](now, amount)


def describe(amount: int, unit: str) -> str:
    """The period as text, e.g. "2 months" or "1 week"."""
    return f"{amount} {_UNITS[unit][1] if amount == 1 else unit}"

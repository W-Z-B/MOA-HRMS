"""Guyana's public holidays for a year: which follow a rule, and which come from the gazette (item 1.25).

Fixed dates and the dates that follow from Easter or from the first Monday in July are worked out here.
Phagwah, Eid ul-Adha, Youman Nabi and Deepavali follow lunar calendars and are named each year in the
gazette, as is any substitute day when a holiday falls on a Sunday; HR enters those.
"""

from dataclasses import dataclass
from datetime import date, timedelta

FIXED = [
    ((1, 1), "New Year's Day"),
    ((2, 23), "Republic Day (Mashramani)"),
    ((5, 1), "Labour Day"),
    ((5, 5), "Arrival Day"),
    ((5, 26), "Independence Day"),
    ((8, 1), "Emancipation Day"),
    ((12, 25), "Christmas Day"),
    ((12, 26), "Boxing Day"),
]
# Named in the gazette each year: (name, words that find it among the holidays on file).
FROM_THE_GAZETTE = [
    ("Phagwah", ("phagwah", "holi")),
    ("Eid ul-Adha", ("eid",)),
    ("Youman Nabi", ("youman", "mawlid")),
    ("Deepavali", ("deepavali", "diwali")),
]


@dataclass
class Expected:
    name: str
    day: date | None  # None: the date comes from the gazette
    rule: str


def easter(year: int) -> date:
    """Easter Sunday in the Gregorian calendar (the anonymous algorithm, as published by Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def first_monday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7)


def by_rule(year: int) -> list[Expected]:
    """The holidays whose date follows from a rule."""
    sunday = easter(year)
    days = [Expected(name, date(year, month, day), "Fixed date") for (month, day), name in FIXED]
    days += [
        Expected("Good Friday", sunday - timedelta(days=2), "Two days before Easter Sunday"),
        Expected("Easter Monday", sunday + timedelta(days=1), "The day after Easter Sunday"),
        Expected("CARICOM Day", first_monday(year, 7), "The first Monday in July"),
    ]
    return sorted(days, key=lambda e: e.day)


def expected(year: int) -> list[Expected]:
    """Every holiday a year should have: dated by rule, or waiting for its date from the gazette."""
    return by_rule(year) + [Expected(name, None, "Date named in the gazette") for name, _ in FROM_THE_GAZETTE]

from datetime import UTC, date, datetime

import pytest
from dateutil.rrule import rrulestr
from todoist_api_python.models import Due

from ntimporters.todoist.importer import parse_due
from ntimporters.todoist.recurrence import to_rrule


@pytest.mark.parametrize(
    "value, timezone, expected",
    [
        (date(2025, 3, 4), None, (1741046400000, True)),
        (datetime(2025, 3, 4, 15, 30), None, (1741098600000, False)),
        (datetime(2025, 3, 4, 15, 30), "UTC", (1741102200000, False)),
        (datetime(2025, 3, 4, 15, 30, tzinfo=UTC), "Asia/Tokyo", (1741102200000, False)),
    ],
)
def test_parse_due(value, timezone, expected):
    assert parse_due(Due(date=value, string="", timezone=timezone), "Europe/Warsaw") == expected


def test_parse_due_empty():
    assert parse_due(None, "UTC") == (None, False)


@pytest.mark.parametrize(
    "text, rrule",
    [
        ("every! 3 days at 9am", "FREQ=DAILY;INTERVAL=3"),
        ("every other monday", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
        ("every mon, fri", "FREQ=WEEKLY;BYDAY=MO,FR"),
        ("every weekday", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("every 1st, 15th", "FREQ=MONTHLY;BYMONTHDAY=1,15"),
        ("every last day of the month", "FREQ=MONTHLY;BYMONTHDAY=-1"),
        ("every 3rd friday", "FREQ=MONTHLY;BYDAY=FR;BYSETPOS=3"),
        ("every year", "FREQ=YEARLY"),
        ("every 3 days ending 2029-01-19", "FREQ=DAILY;INTERVAL=3;UNTIL=20290119"),
        ("codziennie o 8:00", "FREQ=DAILY"),
        ("co 2 tygodnie", "FREQ=WEEKLY;INTERVAL=2"),
        ("w każdą środę", "FREQ=WEEKLY;BYDAY=WE"),
        ("w dni robocze", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("every 2 weeks on monday", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
        ("every month on the 5th", "FREQ=MONTHLY;BYMONTHDAY=5"),
        ("every quarter", "FREQ=MONTHLY;INTERVAL=3"),
        ("every morning", "FREQ=DAILY"),
        ("every jan 27", "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=27"),
        ("co 27 stycznia", "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=27"),
        # unbounded rule would be wrong: comment instead
        ("every day starting jan 1 until feb 28", None),
        ("every day for 3 weeks", None),
        ("every monday morning", None),
        ("every 2 hours", None),
        (None, None),
    ],
)
def test_to_rrule(text, rrule):
    assert to_rrule(text) == rrule
    if rrule:
        assert rrulestr(rrule, dtstart=datetime(2026, 1, 1))[1]


def test_to_rrule_other_language():
    assert to_rrule("jeden Montag", "de") is None
    assert to_rrule("every monday", "de") is None

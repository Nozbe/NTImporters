from datetime import UTC, date, datetime

import pytest
from ntimporters.todoist.importer import parse_due
from ntimporters.todoist.recurrence import to_rrule
from todoist_api_python.models import Due


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
        ("every jan 27", None),
        ("every 2 hours", None),
        (None, None),
    ],
)
def test_to_rrule(text, rrule):
    assert to_rrule(text) == rrule

from datetime import UTC, date, datetime
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest
from dateutil.rrule import rrulestr
from todoist_api_python.models import Due

from ntimporters.todoist import importer
from ntimporters.todoist.importer import parse_due
from ntimporters.todoist.recurrence import to_rrule


@pytest.mark.parametrize(
    "value, timezone, expected",
    [
        (date(2025, 3, 4), None, (1741046400000, True)),
        (
            datetime(2025, 3, 4, 15, 30),
            None,
            (1741098600000, False),
        ),  # floating: user zone
        (datetime(2025, 3, 4, 15, 30), "UTC", (1741102200000, False)),
        (
            datetime(2025, 3, 4, 15, 30, tzinfo=UTC),
            "Asia/Tokyo",
            (1741102200000, False),
        ),
    ],
)
def test_parse_due(value, timezone, expected):
    assert (
        parse_due(Due(date=value, string="", timezone=timezone), "Europe/Warsaw")
        == expected
    )


def test_parse_due_empty():
    assert parse_due(None, "UTC") == (None, False)


@pytest.mark.parametrize(
    "text, rrule",
    [
        ("every! 3 days at 9am", None),  # after completion: no RRULE
        ("every other monday", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
        ("every mon, fri", "FREQ=WEEKLY;BYDAY=MO,FR"),
        ("every weekday", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("every 1st, 15th", "FREQ=MONTHLY;BYMONTHDAY=1,15"),
        ("every 1, 15", "FREQ=MONTHLY;BYMONTHDAY=1,15"),
        ("every 1 and 15", "FREQ=MONTHLY;BYMONTHDAY=1,15"),
        ("every 15 30", "FREQ=MONTHLY;BYMONTHDAY=15,30"),
        ("every 2 weeks", "FREQ=WEEKLY;INTERVAL=2"),
        ("every 3 months", "FREQ=MONTHLY;INTERVAL=3"),
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
        # would be unbounded
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


def test_comment_entries():
    """Description first; body as earlier imports ('…' if empty) + file; link only: link;
    link not in body: own entry"""
    file = NS(file_url="https://files.todoist.com/f.png", url=None)
    link = NS(file_url=None, url="https://x.io/page")
    comments = [
        NS(content="see", attachment=link, posted_at="2"),
        NS(content="", attachment=file, posted_at="1"),
        NS(content="", attachment=link, posted_at="3"),
        NS(content="https://x.io/page", attachment=link, posted_at="4"),
    ]
    assert importer._comment_entries({"description": "d"}, comments) == [
        ("d", None),
        ("…", file),
        ("see", None),
        ("https://x.io/page", None),
        ("https://x.io/page", None),
        ("https://x.io/page", None),
    ]


@pytest.mark.parametrize(
    "string, refused, calls, fallback",
    [
        ("every day", False, 2, False),
        ("every day", True, 1, True),
        ("every 2 hours", False, 0, True),
    ],
)
def test_set_recurrence(string, refused, calls, fallback):
    """Recurrence posted, task PUT with recurrence_id + is_all_day only; unrecognised or
    refused: due string as comment"""
    due = Due(date=date(2026, 1, 1), string=string, is_recurring=True)
    call = MagicMock(return_value={"id": "r" * 16})
    if refused:
        call.side_effect = importer.ApiException(status=400)
    with (
        patch.object(importer, "_call", call),
        patch.object(importer, "_post_comment") as comment,
    ):
        importer._set_recurrence(None, "p", "t", due, True, "a")
    assert call.call_count == calls
    if calls == 2:
        assert call.call_args.args[1:] == (
            "PUT",
            "/tasks/t",
            {"recurrence_id": "r" * 16, "is_all_day": True},
        )
    assert comment.called == fallback
    if fallback:
        comment.assert_called_once_with(None, "t", f"Todoist: {string}", "a")

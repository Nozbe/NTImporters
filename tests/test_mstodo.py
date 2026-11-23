from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from dateutil.rrule import rrulestr

from ntimporters.mstodo.importer import parse_due, to_rrule
from ntimporters.mstodo.mstodo_api import MSTodoClient


def recurrence(range_=None, **pattern):
    return {"pattern": {"interval": 1} | pattern, "range": range_ or {"type": "noEnd"}}


@pytest.mark.parametrize(
    "value, rrule",
    [
        (recurrence(type="daily"), "FREQ=DAILY"),
        (recurrence(type="daily", interval=3), "FREQ=DAILY;INTERVAL=3"),
        (
            recurrence(type="weekly", daysOfWeek=["monday", "friday"], firstDayOfWeek="sunday"),
            "FREQ=WEEKLY;BYDAY=MO,FR",
        ),
        (
            recurrence(type="weekly", interval=2, daysOfWeek=["monday"], firstDayOfWeek="sunday"),
            "FREQ=WEEKLY;INTERVAL=2;WKST=SU;BYDAY=MO",
        ),
        (recurrence(type="absoluteMonthly", dayOfMonth=15), "FREQ=MONTHLY;BYMONTHDAY=15"),
        (
            recurrence(type="relativeMonthly", daysOfWeek=["thursday"], index="second"),
            "FREQ=MONTHLY;BYDAY=TH;BYSETPOS=2",
        ),
        (
            recurrence(type="relativeMonthly", daysOfWeek=["friday"], index="last"),
            "FREQ=MONTHLY;BYDAY=FR;BYSETPOS=-1",
        ),
        (
            recurrence(type="absoluteYearly", dayOfMonth=27, month=1),
            "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=27",
        ),
        (
            recurrence(type="relativeYearly", daysOfWeek=["thursday"], month=11, index="fourth"),
            "FREQ=YEARLY;BYMONTH=11;BYDAY=TH;BYSETPOS=4",
        ),
        (
            recurrence({"type": "endDate", "endDate": "2029-01-19"}, type="daily"),
            "FREQ=DAILY;UNTIL=20290119",
        ),
        (
            recurrence({"type": "numbered", "numberOfOccurrences": 5}, type="daily"),
            "FREQ=DAILY;COUNT=5",
        ),
        # unmappable: comment instead
        (recurrence({"type": "numbered"}, type="daily"), None),
        (recurrence(type="absoluteMonthly"), None),
        (recurrence(type="weekly", daysOfWeek=["someday"]), None),
        (recurrence(type="hourly"), None),
        (None, None),
    ],
)
def test_to_rrule(value, rrule):
    assert to_rrule(value) == rrule
    if rrule:
        assert rrulestr(rrule, dtstart=datetime(2026, 1, 1))[0]


@pytest.mark.parametrize(
    "due, expected",
    [
        ({"dateTime": "2025-03-04T00:00:00.0000000", "timeZone": "UTC"}, (1741046400000, True)),
        # due date's midnight in UTC+2 / UTC-5
        ({"dateTime": "2025-03-03T22:00:00.0000000", "timeZone": "UTC"}, (1741046400000, True)),
        ({"dateTime": "2025-03-04T05:00:00.0000000", "timeZone": "UTC"}, (1741046400000, True)),
        (None, (None, False)),
    ],
)
def test_parse_due(due, expected):
    assert parse_due(due) == expected


def test_client_follows_next_link():
    pages = [
        {"value": [{"id": "a"}], "@odata.nextLink": "https://graph.microsoft.com/next"},
        {"value": [{"id": "b"}]},
    ]
    get = MagicMock(side_effect=[MagicMock(ok=True, json=MagicMock(return_value=p)) for p in pages])
    with patch("requests.Session.get", get):
        assert MSTodoClient("token").lists() == [{"id": "a"}, {"id": "b"}]
    assert [call.args[0] for call in get.call_args_list] == [
        "https://graph.microsoft.com/v1.0/me/todo/lists",
        "https://graph.microsoft.com/next",
    ]
    assert get.call_args_list[1].kwargs.get("params") is None

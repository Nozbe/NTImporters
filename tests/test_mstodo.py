from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from dateutil.rrule import rrulestr

from ntimporters.mstodo.importer import _import_comments, _remind_at, _text, parse_due, to_rrule
from ntimporters.mstodo.mstodo_api import MSTodoClient
from ntimporters.nozbe import due_fields


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
        # unmappable
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
        # app-set: local midnight as UTC (Warsaw +1, New York -5)
        ({"dateTime": "2025-03-03T23:00:00.0000000", "timeZone": "UTC"}, (1741046400000, True)),
        ({"dateTime": "2025-03-04T05:00:00.0000000", "timeZone": "UTC"}, (1741046400000, True)),
        (None, (None, False)),
    ],
)
def test_parse_due(due, expected):
    assert due_fields(parse_due(due)) == expected


def test_parse_due_in_user_zone():
    """App-set local midnight, offset over 12 h (Auckland +13)"""
    due = {"dateTime": "2025-03-03T11:00:00.0000000", "timeZone": "UTC"}
    assert due_fields(parse_due(due, "Pacific/Auckland")) == (1741046400000, True)


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


def test_comments_from_expanded_task():
    """checklistItems, linkedResources from task; no per-task requests"""
    nz, todo = MagicMock(), MagicMock()
    task = {
        "id": "t",
        "checklistItems": [{"displayName": "a", "isChecked": True}],
        "linkedResources": [{"displayName": "L", "webUrl": "https://x.io"}],
    }
    _import_comments(nz, todo, "l", "nt", task)
    nz.comment.assert_called_once_with("nt", "- [x] a")
    nz.attachment.assert_called_once_with("nt", "L", "https://x.io", is_file=False)
    assert not todo.method_calls


@pytest.mark.parametrize(
    "task, expected",
    [
        (
            {"isReminderOn": True, "reminderDateTime": {"dateTime": "2026-11-25T08:00:00.0000000"}},
            1795593600000,
        ),
        ({"isReminderOn": False, "reminderDateTime": {"dateTime": "2026-11-25T08:00:00"}}, None),
        (
            {"isReminderOn": True, "status": "completed", "reminderDateTime": {"dateTime": "x"}},
            None,
        ),
    ],
)
def test_remind_at(task, expected):
    assert _remind_at(task) == expected


@pytest.mark.parametrize(
    "body, text",
    [
        ({"contentType": "text", "content": "a\r\nb "}, "a\nb"),
        (
            {
                "contentType": "html",
                "content": "<html><head><style>p{}</style></head><body><p>Buy <b>milk</b> &amp; "
                '<a href="https://x.com">eggs</a><br>now</p><ul><li>one</li><li>two</li></ul>',
            },
            "Buy **milk** & [eggs](https://x.com)\nnow\n\n- one\n- two",
        ),
        (None, ""),
    ],
)
def test_text(body, text):
    """html -> markdown: links, lists kept; head/style dropped"""
    assert _text(body) == text

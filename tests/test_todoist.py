from datetime import UTC, date, datetime
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import httpx
import pytest
from dateutil.rrule import rrulestr
from todoist_api_python.models import Due

from ntimporters.nozbe import due_fields
from ntimporters.todoist import importer
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
    due = parse_due(Due(date=value, string="", timezone=timezone), "Europe/Warsaw")
    assert due_fields(due) == expected


def test_parse_due_empty():
    assert parse_due(None, "UTC") is None


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


def test_owner_and_time_zone_from_single_user_request():
    user = {"id": "u1", "tz_info": {"timezone": "Asia/Tokyo"}}
    project = NS(id="p", name="P", is_inbox_project=False, is_shared=True, is_favorite=False)
    todoist = MagicMock()
    todoist.get_projects.return_value = [[project]]
    todoist.get_collaborators.return_value = [[NS(id="u1", email="me@x.io")]]
    todoist.get_labels.return_value = todoist.get_sections.return_value = []
    todoist.get_tasks.return_value = []
    nz = MagicMock()
    with patch("requests.Session.get") as get, patch("requests.Session.post"):
        get.return_value.json.return_value = user
        importer._import_data(nz, todoist, "token")
    get.assert_called_once()
    nz.members.assert_called_once_with({"u1": "me@x.io"}, owner="u1")


def test_retry_transport(monkeypatch):
    """429/503 retried: Retry-After seconds if sent, else backoff; other statuses returned"""
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(503),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda self, request: next(responses)
    )
    monkeypatch.setattr(importer.time, "sleep", sleep := MagicMock())
    client = httpx.Client(transport=importer.RetryTransport())
    assert client.get("https://api.todoist.com/x").json() == {"ok": 1}
    assert [elt.args[0] for elt in sleep.call_args_list] == [7, 2]


def test_comments_one_sync_grouped():
    """Deleted notes skipped; incomplete tasks refetched per task"""
    note = {"content": "c", "posted_uid": "u", "posted_at": "2025-03-04T15:30:00Z"}
    sync = {
        "notes": [
            note | {"id": "1", "item_id": "t1", "file_attachment": {"file_name": "f"}},
            note | {"id": "2", "item_id": "t1", "is_deleted": True},
        ],
        "incomplete_item_ids": ["t2"],
    }
    with patch("requests.Session.post") as post:
        post.return_value.json.return_value = sync
        comments = importer._comments("token")
    assert {key: [elt.id for elt in value or []] for key, value in comments.items()} == {
        "t1": ["1"],
        "t2": [],
    }
    assert comments.get("t1")[0].attachment.file_name == "f"
    ctx = MagicMock(comments=comments)
    ctx.todoist.get_comments.return_value = [[]]
    for task_id in ("t1", "t2", "t3"):
        importer._import_comments(ctx, "nt", NS(id=task_id, description=""))
    ctx.todoist.get_comments.assert_called_once_with(task_id="t2")


def test_comments_bad_note_falls_back_per_task():
    """A note the SDK can't parse: None (all tasks fetch comments per task), not a crash"""
    with patch("requests.Session.post") as post:
        post.return_value.json.return_value = {"notes": [{"id": "1", "item_id": "t1"}]}
        assert importer._comments("token") is None

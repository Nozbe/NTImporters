from unittest.mock import Mock, patch

import pytest

from ntimporters.monday.importer import _task, _tasks
from ntimporters.monday.monday_api import MondayClient
from ntimporters.nozbe import due_fields
from ntimporters.utils import ImportException


@pytest.mark.parametrize(
    "status, payload, message",
    [
        (500, {}, "HTTP 500"),
        (200, {"errors": [{"message": "Bad query"}]}, "Bad query"),
        (429, {"errors": [{"extensions": {"code": "DAILY_LIMIT_EXCEEDED"}}]}, "daily limit"),
        (502, ValueError("HTML page"), "HTTP 502"),
    ],
)
def test_req_raises(status, payload, message):
    response = Mock(status_code=status, content=b"x", json=Mock(side_effect=[payload]))
    with (
        patch("requests.Session.post", return_value=response),
        pytest.raises(ImportException, match=message),
    ):
        MondayClient("key")._req("me{email}")


def test_req_waits_out_rate_limit(monkeypatch):
    """429 / exhausted budget: wait retry_in_seconds, then retry"""
    limited = {
        "errors": [{"extensions": {"code": "COMPLEXITY_BUDGET_EXHAUSTED", "retry_in_seconds": 7}}]
    }
    responses = [Mock(status_code=429, content=b"x", json=Mock(return_value=limited))] * 2 + [
        Mock(status_code=200, content=b"x", json=Mock(return_value={"data": {"ok": 1}}))
    ]
    monkeypatch.setattr("ntimporters.monday.monday_api.time.sleep", sleep := Mock())
    with patch("requests.Session.post", side_effect=responses):
        assert MondayClient("key")._req("me{id}") == {"data": {"ok": 1}}
    assert [elt.args[0] for elt in sleep.call_args_list] == [7, 7]


def test_req_paces_on_low_budget(monkeypatch):
    """Budget left below COST_MARGIN x query cost: next request waits for the reset"""

    def response(after):
        complexity = {"query": 100, "after": after, "reset_in_x_seconds": 30}
        return Mock(
            status_code=200,
            content=b"x",
            json=Mock(return_value={"data": {"complexity": complexity}}),
        )

    monkeypatch.setattr("ntimporters.monday.monday_api.time.monotonic", lambda: 1000.0)
    monkeypatch.setattr("ntimporters.monday.monday_api.time.sleep", sleep := Mock())
    client = MondayClient("key")
    with patch(
        "requests.Session.post", side_effect=[response(500), response(150), response(500)]
    ) as post:
        for _ in range(3):
            client._req("me{id}")
    assert [elt.args[0] for elt in sleep.call_args_list] == [30]
    assert "complexity { query after reset_in_x_seconds }" in post.call_args.kwargs.get("json").get(
        "query"
    )


def test_paged():
    client = MondayClient("key")
    client.limit = 2
    pages = {1: [1, 2], 2: [3, 4], 3: [5]}
    with patch.object(
        client, "_req", side_effect=lambda query: {"data": {"x": pages.get(int(query))}}
    ) as req:
        assert client._paged(str, "data.x") == [1, 2, 3, 4, 5]
    assert req.call_count == 3


def _raw(id_, *columns, updates=()):
    return {"id": id_, "name": f"n{id_}", "column_values": list(columns), "updates": list(updates)}


DATE = {"type": "date", "text": "x", "value": '{"date": "2024-05-01", "time": "10:00:00"}'}
PEOPLE = {"type": "people", "value": '{"personsAndTeams": [{"id": 7, "kind": "person"}]}'}


@pytest.mark.parametrize(
    "columns, due_at, is_all_day, assigned",
    [
        ((DATE, PEOPLE), 1714557600000, False, ["7"]),
        ((DATE | {"value": '{"date": "2024-05-01"}'},), 1714521600000, True, []),
        ((DATE, DATE), None, False, []),
    ],
)
def test_task(columns, due_at, is_all_day, assigned):
    replies = [{"created_at": "2024-01-03T00:00:00Z", "text_body": "r"}]
    updates = [
        {"created_at": "2024-01-02T00:00:00Z", "text_body": "u2", "replies": replies},
        {"created_at": "2024-01-01T00:00:00Z", "text_body": "u1"},
    ]
    task = _task(_raw(1, *columns, updates=updates), "g", 3)
    assert due_fields(task.pop("due")) == (due_at, is_all_day)
    assert task == {
        "id": 1,
        "name": "n1",
        "group": "g",
        "position": 3,
        "assigned": assigned,
        "comments": [updates[1], updates[0], *replies],
    }


def test_board_pages_and_orders():
    client = MondayClient("key")
    client.updates_limit = 1
    full = [{"created_at": "2024-01-02", "text_body": "b"}, {"created_at": "2024-01-01"}]
    item1 = _raw(1, updates=[full[0]]) | {"group": {"id": "g"}, "subitems": [_raw(2)]}
    responses = [
        {
            "data": {
                "boards": [
                    {"groups": [{"id": "g"}], "items_page": {"cursor": "c", "items": [item1]}}
                ]
            }
        },
        {
            "data": {
                "next_items_page": {"cursor": None, "items": [_raw(3) | {"group": {"id": "h"}}]}
            }
        },
        {"data": {"items": [{"updates": full}]}},
    ]
    with patch.object(client, "_req", side_effect=responses) as req:
        groups, items = client.board("b")
    tasks = _tasks(items)
    assert req.call_count == 3
    assert groups == [{"id": "g"}]
    assert [(t["id"], t["group"], t["position"]) for t in tasks] == [
        (3, "h", 3),
        (2, "g", 2),
        (1, "g", 1),
    ]
    assert tasks[2]["comments"] == full[::-1]

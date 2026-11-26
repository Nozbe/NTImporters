from unittest.mock import Mock, patch

import pytest

from ntimporters.trello import trello_api
from ntimporters.trello.trello_api import TrelloClient, checklists
from ntimporters.utils import ImportException


def test_comments_paged_grouped_oldest_first():
    def action(n, card="c"):
        return {
            "id": f"a{n}",
            "date": f"2025-01-01T00:00:{n:02}.000Z",
            "data": {"card": {"id": card}, "text": f"t{n}"},
        }

    pages = {
        "boards/b/actions?filter=commentCard&limit=2": [action(4), action(3, "d")],
        "boards/b/actions?filter=commentCard&limit=2&before=a3": [action(2), action(1)],
        "boards/b/actions?filter=commentCard&limit=2&before=a1": [action(0)],
    }
    with (
        patch.object(trello_api, "ACTIONS_LIMIT", 2),
        patch.object(TrelloClient, "__init__", lambda self: None),
        patch.object(TrelloClient, "_req", lambda self, suffix: pages.get(suffix)),
    ):
        assert TrelloClient().comments("b") == {"c": ["t0", "t1", "t2", "t4"], "d": ["t3"]}


def test_tasks_grouped_by_list_in_pos_order():
    cards = [
        {"id": "x", "idList": "l1", "pos": 3},
        {"id": "y", "idList": "l2", "pos": 1},
        {"id": "z", "idList": "l1", "pos": 2},
    ]
    with (
        patch.object(TrelloClient, "__init__", lambda self: None),
        patch.object(TrelloClient, "_req", lambda self, suffix: cards),
    ):
        tasks = TrelloClient().tasks("b")
    assert {key: [card.get("id") for card in value] for key, value in tasks.items()} == {
        "l1": ["z", "x"],
        "l2": ["y"],
    }


def test_members_emails_batched_failed_refetched():
    """Failed entry refetched; still failing (gone member): None"""
    boards = [
        {"members": [{"id": "me"}, {"id": "a"}]},
        {"members": [{"id": "b"}, {"id": "a"}, {"id": "gone"}]},
    ]
    client = TrelloClient.__new__(TrelloClient)
    client.author_id = "me"
    single = {"members/b": {"id": "b", "email": "b@x.io"}}

    def req(suffix):
        if suffix.startswith("batch?urls="):
            ids = [
                url.split("/")[2].split("?")[0]
                for url in suffix.removeprefix("batch?urls=").split(",")
            ]
            return [
                {"200": {"id": "a", "email": "a@x.io"}} if i == "a" else {"statusCode": 429}
                for i in ids
            ]
        if suffix not in single:
            raise ImportException("Connection to trello failed (404)")
        return single.get(suffix)

    with (
        patch.object(trello_api, "BATCH_LIMIT", 1),
        patch.object(client, "_req", side_effect=req) as mock,
    ):
        assert client.members_emails(boards) == {"a": "a@x.io", "b": "b@x.io", "gone": None}
    assert len(mock.call_args_list) == 5


def test_checklists():
    card = {
        "checklists": [
            {
                "checkItems": [
                    {"state": "incomplete", "name": "x"},
                    {"state": "complete", "name": "y"},
                ]
            },
            {"checkItems": []},  # no items: no "…" comment
        ]
    }
    assert checklists(card) == ["- [ ] x\n- [x] y"]


@pytest.mark.parametrize("status, message", [(401, "wrong credentials"), (500, r"failed \(500\)")])
def test_req_raises(status, message):
    with (
        patch("requests.Session.get", return_value=Mock(status_code=status, ok=False)),
        pytest.raises(ImportException, match=message),
    ):
        TrelloClient("key", "token")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://trello.com/1/cards/c/attachments/a/download/f.png", True),
        ("https://api.trello.com/x", True),
        ("https://trello-attachments.s3.amazonaws.com/f.png", False),
        ("https://eviltrello.com/x", False),
        (None, False),
    ],
)
def test_on_host(url, expected):
    from ntimporters.utils import on_host

    assert on_host(url, "trello.com") is expected

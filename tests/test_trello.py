from unittest.mock import patch

from ntimporters.trello import trello_api
from ntimporters.trello.trello_api import TrelloClient, checklists


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


def test_checklists():
    card = {
        "checklists": [
            {
                "checkItems": [
                    {"state": "incomplete", "name": "x"},
                    {"state": "complete", "name": "y"},
                ]
            }
        ]
    }
    assert checklists(card) == ["- [ ] x\n- [x] y"]

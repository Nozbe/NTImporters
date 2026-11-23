"""Simple trello REST API client"""

from collections import defaultdict

import requests

from ntimporters.utils import ImportException, dig

ACTIONS_LIMIT = 1000  # API maximum
BOARD_NESTED = "lists=open&labels=all&labels_limit=1000&members=all"
CARD_FIELDS = "name,desc,due,dueComplete,idList,idMembers,labels,pos"

# board -> project
# list ->  section
# card -> task
# comment -> comment
# checklist -> comment


class TrelloClient:
    """Simple trello REST API client"""

    api_path = "https://api.trello.com/1"

    def __init__(self, app_key, token):
        self.headers = {
            "Authorization": f'OAuth oauth_consumer_key="{app_key}", oauth_token="{token}"'
        }
        user_data = self._req("members/me")
        self.author_id = user_data.get("id")
        self.boards_ids = user_data.get("idBoards", [])

    def _req(self, suffix) -> dict:
        if resp := requests.get(f"{self.api_path}/{suffix}", headers=self.headers, timeout=60):
            return resp.json()
        raise ImportException(
            f"Connection to trello failed ({resp.status_code}). Wrong credentials?"
        )

    def projects(self) -> list[dict]:
        """Boards with lists, labels, members; is_fav if starred by me"""
        starred = {star.get("idBoard") for star in self._req("members/me/boardStars")}
        return [
            self._req(f"boards/{board_id}?{BOARD_NESTED}") | {"is_fav": board_id in starred}
            for board_id in self.boards_ids
        ]

    def members_emails(self, boards: list[dict]) -> dict:
        """Member id -> email, other boards' members (each fetched once)"""
        member_ids = {
            member.get("id") for board in boards for member in board.get("members") or []
        } - {self.author_id}
        return {
            member_id: self._req(f"members/{member_id}").get("email") for member_id in member_ids
        }

    def tasks(self, board_id: str) -> dict[str, list[dict]]:
        """List id -> its open cards by pos, with checklists and attachments"""
        lists = defaultdict(list)
        for card in sorted(
            self._req(
                f"boards/{board_id}/cards/visible?fields={CARD_FIELDS}&checklists=all&attachments=true"
            ),
            key=lambda card: card.get("pos") or 0,
        ):
            lists[card.get("idList")].append(card)
        return lists

    def comments(self, board_id: str) -> dict[str, list[str]]:
        """Card id -> comment texts, oldest first"""
        actions, before = [], ""
        while page := self._req(
            f"boards/{board_id}/actions?filter=commentCard&limit={ACTIONS_LIMIT}{before}"
        ):
            actions += page
            if len(page) < ACTIONS_LIMIT:
                break
            before = f"&before={page[-1].get('id')}"  # newest first
        cards = defaultdict(list)
        for action in sorted(actions, key=lambda elt: elt.get("date") or ""):
            cards[dig(action, "data.card.id")].append(dig(action, "data.text"))
        return cards


def checklists(card: dict) -> list[str]:
    """Card checklists as markdown task lists"""
    return [
        "\n".join(
            f"- [{' ' if item.get('state') == 'incomplete' else 'x'}] {item.get('name')}"
            for item in checklist.get("checkItems") or []
        )
        for checklist in card.get("checklists") or []
    ]

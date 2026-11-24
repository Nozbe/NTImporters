"""Trello REST client"""

import itertools
from collections import defaultdict

from ntimporters.utils import ImportException, checklist, dig, session

ACTIONS_LIMIT = 1000  # API maximum
BATCH_LIMIT = 10  # API maximum
BOARD_NESTED = "lists=all&labels=all&labels_limit=1000&members=all"
CARD_FIELDS = "name,desc,due,dueComplete,idList,idMembers,labels,pos"

# board -> project, list -> section, card -> task, comment/checklist -> comment


class TrelloClient:
    """Trello REST API v1"""

    api_path = "https://api.trello.com/1"

    def __init__(self, app_key, token):
        self.headers = {
            "Authorization": f'OAuth oauth_consumer_key="{app_key}", oauth_token="{token}"'
        }
        self.session = session(self.headers)
        user_data = self._req("members/me")
        self.author_id = user_data.get("id")
        self.boards_ids = user_data.get("idBoards", [])

    def _req(self, suffix) -> dict:
        """GET api_path/suffix -> JSON; ImportException on failure"""
        resp = self.session.get(f"{self.api_path}/{suffix}", timeout=60)
        if resp.status_code in (401, 403):
            raise ImportException("Trello: wrong credentials (API key or token)")
        if not resp.ok:
            raise ImportException(f"Connection to trello failed ({resp.status_code})")
        return resp.json()

    def projects(self) -> list[dict]:
        """boards + lists, labels, members; is_fav: starred by me"""
        starred = {star.get("idBoard") for star in self._req("members/me/boardStars")}
        return [
            self._req(f"boards/{board_id}?{BOARD_NESTED}") | {"is_fav": board_id in starred}
            for board_id in self.boards_ids
        ]

    def members_emails(self, boards: list[dict]) -> dict:
        """member id -> email, boards' members but me; email only via members/{id},
        batched by BATCH_LIMIT, failed entry refetched alone"""
        member_ids = {
            member.get("id") for board in boards for member in board.get("members") or []
        } - {self.author_id}
        emails = {}
        for chunk in itertools.batched(member_ids, BATCH_LIMIT, strict=False):
            urls = ",".join(f"/members/{member_id}?fields=email" for member_id in chunk)
            for member_id, entry in zip(chunk, self._req(f"batch?urls={urls}"), strict=True):
                member = entry.get("200") or self._req(f"members/{member_id}")
                emails[member_id] = member.get("email")
        return emails

    def tasks(self, board_id: str) -> dict[str, list[dict]]:
        """list id -> open cards by pos (archived lists too), + checklists, attachments"""
        lists = defaultdict(list)
        for card in sorted(
            self._req(
                f"boards/{board_id}/cards/open?fields={CARD_FIELDS}&checklists=all&attachments=true"
            ),
            key=lambda card: card.get("pos") or 0,
        ):
            lists[card.get("idList")].append(card)
        return lists

    def comments(self, board_id: str) -> dict[str, list[str]]:
        """card id -> comment texts, oldest first"""
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
    """checklists -> markdown task lists"""
    return [
        checklist(
            (item.get("name"), item.get("state") != "incomplete")
            for item in elt.get("checkItems") or []
        )
        for elt in card.get("checklists") or []
    ]

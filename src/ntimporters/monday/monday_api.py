"""Monday API client module"""

import itertools
import time
from collections.abc import Callable

from ntimporters.utils import ImportException, dig, session

UPDATE_FIELDS = "id created_at text_body replies { created_at text_body }"
RATE_LIMITED = {"COMPLEXITY_BUDGET_EXHAUSTED", "RATE_LIMIT_EXCEEDED", "IP_RATE_LIMIT_EXCEEDED"}
RETRIES = 30  # with <= 60 s waits: Monday budgets reset per minute
COST_MARGIN = 2  # pause when remaining budget is below this many last-query costs


class MondayClient:
    """Client to connect to Monday API"""

    api_path = "https://api.monday.com/v2"
    limit = 300
    page_limit = 100
    updates_limit = 20

    def __init__(self, app_key):
        self.headers = {"Authorization": app_key}
        # 429 left to _req: its body's retry_in_seconds is the right wait
        self.session = session(self.headers, statuses=(500, 502, 503, 504))
        self._resume_at = 0.0  # monotonic time before which the budget is too low

    def _req(self, query) -> dict:
        """Response of GraphQL query. Paced: if the budget left after a query is below
        COST_MARGIN times its cost, the next waits for the budget reset. Rate limits waited
        out (retry_in_seconds, up to RETRIES times); ImportException on daily limit and
        other HTTP or GraphQL errors"""
        for _ in range(RETRIES):
            if (wait := self._resume_at - time.monotonic()) > 0:
                time.sleep(wait)
            resp = self.session.post(
                self.api_path,
                json={"query": f"{{ complexity {{ query after reset_in_x_seconds }} {query} }}"},
                timeout=60,
            )
            try:
                data = resp.json() if resp.content else {}
            except ValueError:  # e.g. HTML error page: reported by status below
                data = {}
            error = dig(data, "errors.0", {})
            code = dig(error, "extensions.code")
            if code == "DAILY_LIMIT_EXCEEDED":
                raise ImportException("Monday API: daily limit exceeded, retry after 00:00 UTC")
            if resp.status_code == 429 or code in RATE_LIMITED:
                time.sleep(min(dig(error, "extensions.retry_in_seconds", 10), 60))
                continue
            if resp.status_code != 200:
                raise ImportException(f"Monday API: HTTP {resp.status_code}")
            if error:
                raise ImportException(f"Monday API: {error.get('message')}")
            cost = dig(data, "data.complexity", {})
            if cost.get("after", 0) < COST_MARGIN * cost.get("query", 0):
                self._resume_at = time.monotonic() + cost.get("reset_in_x_seconds", 0)
            return data
        raise ImportException("Monday API: rate limit not lifted")

    def _paged(self, query: Callable[[int], str], path: str) -> list[dict]:
        """All records at path of query(page), pages 1.. until a short one"""
        records = []
        for page in itertools.count(1):
            records += (batch := dig(self._req(query(page)), path, []))
            if len(batch) < self.limit:
                return records

    def projects(self) -> list[dict]:
        """Get Monday boards (NT projects); sub-items boards and docs skipped"""
        return [
            board
            for board in self._paged(
                lambda page: (
                    f"boards(state:all limit:{self.limit} page:{page})"
                    "{name,id,state,description,board_kind,type}"
                ),
                "data.boards",
            )
            if board.get("type") == "board"
        ]

    def _updates(self, raw: dict) -> list[dict]:
        """Updates of item raw; refetched in full if its nested ones hit the limit"""
        updates = raw.get("updates") or []
        if len(updates) < self.updates_limit:
            return updates
        return self._paged(
            lambda page: (
                f"items(ids:{raw.get('id')}) {{ updates(limit:{self.limit} page:{page})"
                f" {{ {UPDATE_FIELDS} }} }}"
            ),
            "data.items.0.updates",
        )

    def board(self, project_id: str) -> tuple[list[dict], list[dict]]:
        """(groups, items) of board, items in board order; items and their subitems
        carry all their updates"""
        page_args = f"limit:{self.page_limit}"
        item_fields = (
            "id name column_values { id type text value }"
            f" updates(limit:{self.updates_limit}) {{ {UPDATE_FIELDS} }}"
        )
        fields = f"cursor items {{ {item_fields} group {{ id }} subitems {{ {item_fields} }} }}"
        board = dig(
            self._req(
                f"boards(state:all order_by:created_at ids:{project_id}) "
                f"{{ groups {{ id title archived position }} items_page({page_args}) {{ {fields} }} }}"
            ),
            "data.boards.0",
            {},
        )
        page = board.get("items_page") or {}
        items = page.get("items") or []
        while cursor := page.get("cursor"):
            page = dig(
                self._req(f'next_items_page({page_args} cursor:"{cursor}") {{ {fields} }}'),
                "data.next_items_page",
                {},
            )
            items += page.get("items") or []
        for item in items:
            for raw in [item, *(item.get("subitems") or [])]:
                raw["updates"] = self._updates(raw)
        return board.get("groups") or [], items

    def me_id(self) -> str | None:
        """Monday id of token owner"""
        return dig(self._req("me {id}"), "data.me.id")

    def users(self) -> dict:
        """Get Monday users"""
        return {
            elt.get("id"): email
            for elt in dig(self._req("users {id email}"), "data.users", [])
            if (email := elt.get("email"))
        }

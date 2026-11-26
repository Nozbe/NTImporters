"""Monday GraphQL client"""

import itertools
import time
from collections.abc import Callable
from contextlib import suppress

from ntimporters.utils import ImportException, dig, session

UPDATE_FIELDS = "id created_at text_body replies { created_at text_body }"
RATE_LIMITED = {"COMPLEXITY_BUDGET_EXHAUSTED", "RATE_LIMIT_EXCEEDED", "IP_RATE_LIMIT_EXCEEDED"}
RETRIES = 30  # waits <= 60 s; budgets reset per minute
COST_MARGIN = 2  # pause if budget left < this * last query cost


class MondayClient:
    """Monday API v2"""

    api_path = "https://api.monday.com/v2"
    limit = 300
    page_limit = 100  # 500 (API max) exhausts complexity budget with nested updates, subitems
    updates_limit = 20  # nested per item
    updates_page = 100  # API maximum per updates page
    ids_limit = 100  # API maximum ids per items query

    def __init__(self, app_key):
        self.headers = {"Authorization": app_key}
        # 429 handled in _req: wait = body's retry_in_seconds
        self.session = session(self.headers, statuses=(500, 502, 503, 504))
        self._resume_at = 0.0  # monotonic; budget too low until then

    def _req(self, query) -> dict:
        """query -> response. Budget left < COST_MARGIN * cost: next call waits for reset.
        Rate limits waited out (<= RETRIES); ImportException: daily limit, other errors"""
        for _ in range(RETRIES):
            if (wait := self._resume_at - time.monotonic()) > 0:
                time.sleep(wait)
            resp = self.session.post(
                self.api_path,
                json={"query": f"{{ complexity {{ query after reset_in_x_seconds }} {query} }}"},
                timeout=60,
            )
            data = {}
            with suppress(ValueError):  # e.g. HTML error page; status check reports it
                data = resp.json() if resp.content else {}
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

    def _paged(self, query: Callable[[int, int], str], path: str, size: int) -> list[dict]:
        """records at path of query(page, size), pages 1.. until one is short"""
        records = []
        for page in itertools.count(1):
            records += (batch := dig(self._req(query(page, size)), path, []))
            if len(batch) < size:
                return records

    def projects(self) -> list[dict]:
        """boards; subitem boards, docs skipped"""
        return [
            board
            for board in self._paged(
                lambda page, size: (
                    f"boards(state:all limit:{size} page:{page})"
                    "{name,id,state,description,board_kind,type}"
                ),
                "data.boards",
                self.limit,
            )
            if board.get("type") == "board"
        ]

    def _refetch_updates(self, raws: list[dict]):
        """all updates of raws whose nested ones hit updates_limit; per page one request for
        <= ids_limit items, items with a short page dropped"""
        full = [raw for raw in raws if len(raw.get("updates") or []) >= self.updates_limit]
        for chunk in itertools.batched(full, self.ids_limit, strict=False):
            pending = {str(raw.get("id")): raw for raw in chunk}
            for raw in chunk:
                raw["updates"] = []
            for page in itertools.count(1):
                if not pending:
                    break
                query = (
                    f"items(ids:[{','.join(pending)}] limit:{len(pending)}) {{ id"
                    f" updates(limit:{self.updates_page} page:{page}) {{ {UPDATE_FIELDS} }} }}"
                )
                more = {}
                for item in dig(self._req(query), "data.items", []):
                    if raw := pending.get(str(item.get("id"))):
                        raw.get("updates").extend(updates := item.get("updates") or [])
                        if len(updates) == self.updates_page:
                            more[str(item.get("id"))] = raw
                pending = more

    def board(self, project_id: str) -> tuple[list[dict], list[dict]]:
        """(groups, items in board order); items, subitems carry all updates"""
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
        self._refetch_updates(
            [raw for item in items for raw in [item, *(item.get("subitems") or [])]]
        )
        return board.get("groups") or [], items

    def me_id(self) -> str | None:
        """id of token owner"""
        return dig(self._req("me {id}"), "data.me.id")

    def users(self) -> dict:
        """user id -> email; emailless skipped"""
        return {
            elt.get("id"): email
            for elt in dig(self._req("users {id email}"), "data.users", [])
            if (email := elt.get("email"))
        }

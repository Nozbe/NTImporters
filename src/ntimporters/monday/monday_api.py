"""Monday API client module"""

import itertools
import json
import time
from collections.abc import Callable

import requests
from more_itertools import first_true

from ntimporters.utils import ImportException, dig, parse_timestamp

UPDATE_FIELDS = "id created_at text_body replies { created_at text_body }"
PEOPLE = {"people", "multiple-person"}
RATE_LIMITED = {"COMPLEXITY_BUDGET_EXHAUSTED", "RATE_LIMIT_EXCEEDED", "IP_RATE_LIMIT_EXCEEDED"}
RETRIES = 30  # with <= 60 s waits: Monday budgets reset per minute


class MondayClient:
    """Client to connect to Monday API"""

    api_path = "https://api.monday.com/v2"
    limit = 300
    page_limit = 100
    updates_limit = 20

    def __init__(self, app_key):
        self.headers = {"Authorization": app_key}

    def _req(self, query) -> dict:
        """Response of GraphQL query; rate limits waited out (retry_in_seconds, up to
        RETRIES times); ImportException on other HTTP or GraphQL errors"""
        for _ in range(RETRIES):
            resp = requests.post(
                self.api_path, json={"query": f"{{ {query} }}"}, headers=self.headers, timeout=60
            )
            data = resp.json() if resp.content else {}
            error = dig(data, "errors.0", {})
            if resp.status_code == 429 or dig(error, "extensions.code") in RATE_LIMITED:
                time.sleep(min(dig(error, "extensions.retry_in_seconds", 10), 60))
                continue
            if resp.status_code != 200:
                raise ImportException(f"Monday API: HTTP {resp.status_code}")
            if error:
                raise ImportException(f"Monday API: {error.get('message')}")
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

    @staticmethod
    def _thread(updates: list[dict]) -> list[dict]:
        """Updates and their replies, oldest first"""
        return sorted(
            itertools.chain.from_iterable(
                [update, *(update.pop("replies", None) or [])] for update in updates
            ),
            key=lambda elt: parse_timestamp(elt.get("created_at")) or 0,
        )

    def _comments(self, raw: dict) -> list[dict]:
        """Thread of item raw; refetched in full if its nested updates hit the limit"""
        updates = raw.get("updates") or []
        if len(updates) < self.updates_limit:
            return self._thread(updates)
        return self._thread(
            self._paged(
                lambda page: (
                    f"items(ids:{raw.get('id')}) {{ updates(limit:{self.limit} page:{page})"
                    f" {{ {UPDATE_FIELDS} }} }}"
                ),
                "data.items.0.updates",
            )
        )

    def _item(self, raw: dict, group: str | None, position: int) -> dict:
        """Task of item or subitem raw: due_at if exactly one dated date column,
        assigned from first people column, comments"""
        # ASSUMPTION: if only one date-type column then it is due_at
        columns = raw.get("column_values") or []
        due_at, is_all_day = None, False
        match [col for col in columns if col.get("type") == "date" and col.get("text")]:
            case [column]:
                try:
                    # value holds UTC date/time; text is in account's time zone
                    value = json.loads(column.get("value") or "{}")
                    is_all_day = not value.get("time")
                    due_at = parse_timestamp(
                        f"{value.get('date')}T{value.get('time')}Z"
                        if value.get("time")
                        else value.get("date") or column.get("text")
                    )
                except json.decoder.JSONDecodeError, ValueError:
                    pass
        people = first_true(
            columns, pred=lambda col: col.get("type") in PEOPLE and col.get("value")
        )
        return {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "group": group,
            "position": position,
            "due_at": due_at,
            "is_all_day": is_all_day,
            "assigned": [
                str(elt.get("id"))
                for elt in dig(
                    json.loads(people.get("value")) if people else {}, "personsAndTeams", []
                )
            ],
            "comments": self._comments(raw),
        }

    def board(self, project_id: str) -> tuple[list[dict], list[dict]]:
        """(groups, tasks) of board: groups (NT sections); items each followed by its subitems
        (NT tasks), numbered 1.. in that order, returned last first"""
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
        position = itertools.count(1)
        tasks = [
            self._item(raw, dig(item, "group.id"), next(position))
            for item in items
            for raw in [item, *(item.get("subitems") or [])]
        ]
        return board.get("groups") or [], tasks[::-1]

    def users(self) -> dict:
        """Get Monday users"""
        return {
            elt.get("id"): email
            for elt in dig(self._req("users {id email}"), "data.users", [])
            if (email := elt.get("email"))
        }

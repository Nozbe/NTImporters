"""Monday -> Nozbe importer"""

import itertools
import json
import re
from contextlib import suppress
from datetime import datetime

from more_itertools import first_true

from ntimporters.monday.monday_api import MondayClient
from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.utils import dig, parse_timestamp

SPEC = {
    "code": "monday",
    "name": "Monday",
    "url": "https://nozbe.help/advancedfeatures/importers/#monday",
    "input_fields": ("team_id", "nt_auth_token", "app_key"),
}
IMPORT_NAME = "Imported from Monday"
PEOPLE = {"people", "multiple-person"}


def run_import(nt_auth_token: str, app_key: str, team_id: str) -> Exception | str | None:
    """Nozbe app entry point"""
    return run_safely(
        lambda: _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME), MondayClient(app_key)
        ),
        nt_auth_token=nt_auth_token,
        app_key=app_key,
    )


def _import_data(nz: NozbeImport, monday: MondayClient):
    """active boards -> projects, groups -> sections, items -> tasks"""
    boards = [board for board in monday.projects() if board.get("state") == "active"]
    nz.check_group(bool(boards))
    responsible = nz.members(monday.users(), owner=monday.me_id())
    for board in boards:
        _import_board(nz, monday, board, responsible)


def _import_board(nz: NozbeImport, monday: MondayClient, board: dict, responsible: dict):
    """board -> project + sections, tasks, comments"""
    if not (
        nt_project_id := nz.project(
            board.get("name", ""),
            description=board.get("description"),
            is_open=board.get("board_kind") == "public",
        )
    ):
        return
    groups, items = monday.board(board.get("id"))
    section_ids = {
        group.get("id"): section_id
        for group in groups
        if (
            section_id := nz.section(
                nt_project_id,
                group.get("title", ""),
                group.get("position") or 1,
                archived=bool(group.get("archived")),
            )
        )
    }
    for item in _tasks(items):
        nt_task_id, _ = nz.task(
            nt_project_id,
            item.get("name", ""),
            section_id=section_ids.get(item.get("group")),
            position=item.get("position") or 1,
            due=item.get("due"),
            responsible_id=first_true(map(responsible.get, item.get("assigned") or [])),
            assigned=bool(item.get("assigned") or item.get("teams")),
        )
        if nt_task_id:
            for update in item.get("comments") or []:
                body = update.get("text_body")
                # bullets at line start -> markdown
                nz.comment(nt_task_id, body and re.sub(r"(?m)^(\s*)\* ", r"\1- ", body))


def _thread(updates: list[dict]) -> list[dict]:
    """updates + replies, flat, oldest first"""
    return sorted(
        itertools.chain.from_iterable(
            [update, *(update.pop("replies", None) or [])] for update in updates
        ),
        key=lambda elt: parse_timestamp(elt.get("created_at")) or 0,
    )


def _value(column: dict | None):
    """column's parsed JSON value (read with dig); None if none or unreadable"""
    with suppress(ValueError):
        return json.loads(dig(column, "value") or "null")
    return None


def _task(raw: dict, group: str | None, position: int) -> dict:
    """item/subitem -> task; due: sole dated date column; assigned: first set people column"""
    columns = raw.get("column_values") or []
    due = None
    match [col for col in columns if col.get("type") == "date" and col.get("text")]:
        case [column]:
            value = _value(column)  # value: UTC; text: account time zone
            day, moment = dig(value, "date"), dig(value, "time")
            with suppress(ValueError):  # unreadable date: no due
                due = (
                    datetime.fromisoformat(f"{day}T{moment}Z")
                    if moment
                    else datetime.fromisoformat(day or column.get("text")).date()
                )
    people = first_true(columns, pred=lambda col: col.get("type") in PEOPLE and col.get("value"))
    entries = dig(_value(people), "personsAndTeams", [])
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "group": group,
        "position": position,
        "due": due,
        "assigned": [str(elt.get("id")) for elt in entries if elt.get("kind") == "person"],
        "teams": [str(elt.get("id")) for elt in entries if elt.get("kind") == "team"],
        "comments": _thread(raw.get("updates") or []),
    }


def _tasks(items: list[dict]) -> list[dict]:
    """items, each then its subitems; positions 1.. in that order; returned reversed"""
    rows = [(raw, item) for item in items for raw in [item, *(item.get("subitems") or [])]]
    return [
        _task(raw, dig(item, "group.id"), position) for position, (raw, item) in enumerate(rows, 1)
    ][::-1]

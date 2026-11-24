"""Monday -> Nozbe importer"""

import itertools
import json

from dateutil.parser import isoparse
from more_itertools import first_true

from ntimporters.monday.monday_api import MondayClient
from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.utils import dig, parse_timestamp

SPEC = {
    "code": "monday",  # codename / ID of importer
    "name": "Monday",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#monday",
    "input_fields": ("team_id", "nt_auth_token", "app_key"),
}
IMPORT_NAME = "Imported from Monday"
PEOPLE = {"people", "multiple-person"}


# main method called by Nozbe app
def run_import(nt_auth_token: str, app_key: str, team_id: str) -> Exception | str | None:
    """Perform import from monday to Nozbe"""
    return run_safely(
        lambda: _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME), MondayClient(app_key)
        ),
        nt_auth_token=nt_auth_token,
        app_key=app_key,
    )


def _import_data(nz: NozbeImport, monday: MondayClient):
    """Import active boards (projects), groups (sections), items (tasks)"""
    boards = [board for board in monday.projects() if board.get("state") == "active"]
    nz.check_open_projects(
        board.get("name") for board in boards if board.get("board_kind") == "public"
    )
    responsible = nz.members(monday.users(), owner=monday.me_id())
    for board in boards:
        _import_board(nz, monday, board, responsible)


def _import_board(nz: NozbeImport, monday: MondayClient, board: dict, responsible: dict):
    """Import board with its groups and items"""
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
            assigned=bool(item.get("assigned")),
        )
        if nt_task_id:
            for update in item.get("comments") or []:
                nz.comment(nt_task_id, format_body(update.get("text_body")))


def format_body(body: str | None) -> str | None:
    """Monday bullets -> markdown"""
    return body and body.replace("* ", "- ")


def _thread(updates: list[dict]) -> list[dict]:
    """Updates and their replies, oldest first"""
    return sorted(
        itertools.chain.from_iterable(
            [update, *(update.pop("replies", None) or [])] for update in updates
        ),
        key=lambda elt: parse_timestamp(elt.get("created_at")) or 0,
    )


def _task(raw: dict, group: str | None, position: int) -> dict:
    """Task of item or subitem raw: due if exactly one dated date column,
    assigned from first people column, comments"""
    # ASSUMPTION: if only one date-type column then it is the due date
    columns = raw.get("column_values") or []
    due = None
    match [col for col in columns if col.get("type") == "date" and col.get("text")]:
        case [column]:
            try:
                # value holds UTC date/time; text is in account's time zone
                value = json.loads(column.get("value") or "{}")
                due = (
                    isoparse(f"{value.get('date')}T{value.get('time')}Z")
                    if value.get("time")
                    else isoparse(value.get("date") or column.get("text")).date()
                )
            except json.decoder.JSONDecodeError, ValueError:
                pass
    people = first_true(columns, pred=lambda col: col.get("type") in PEOPLE and col.get("value"))
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "group": group,
        "position": position,
        "due": due,
        "assigned": [
            str(elt.get("id"))
            for elt in dig(json.loads(people.get("value")) if people else {}, "personsAndTeams", [])
        ],
        "comments": _thread(raw.get("updates") or []),
    }


def _tasks(items: list[dict]) -> list[dict]:
    """Tasks of items, each followed by its subitems, numbered 1.. in that order,
    returned last first"""
    position = itertools.count(1)
    tasks = [
        _task(raw, dig(item, "group.id"), next(position))
        for item in items
        for raw in [item, *(item.get("subitems") or [])]
    ]
    return tasks[::-1]

"""Monday -> Nozbe importer"""

from more_itertools import first_true

from ntimporters.monday.monday_api import MondayClient
from ntimporters.nozbe import NozbeImport, run_safely

SPEC = {
    "code": "monday",  # codename / ID of importer
    "name": "Monday",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#monday",
    "input_fields": ("team_id", "nt_auth_token", "app_key"),
}
IMPORT_NAME = "Imported from Monday"


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
    responsible = nz.members(monday.users())
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
    nz.check_limit("project_sections", len(groups))
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
    for item in items:
        nt_task_id, _ = nz.task(
            nt_project_id,
            item.get("name", ""),
            section_id=section_ids.get(item.get("group")),
            position=item.get("position") or 1,
            due_at=item.get("due_at"),
            is_all_day=bool(item.get("is_all_day")),
            responsible_id=first_true(map(responsible.get, item.get("assigned") or [])),
            assigned=bool(item.get("assigned")),
        )
        if nt_task_id:
            for update in item.get("comments") or []:
                nz.comment(nt_task_id, format_body(update.get("text_body")))


def format_body(body: str | None) -> str | None:
    """Monday bullets -> markdown"""
    return body and body.replace("* ", "- ")

"""Trello -> Nozbe importer"""

from urllib.parse import urlparse

from dateutil.parser import isoparse
from more_itertools import first_true

from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.trello.trello_api import TrelloClient, checklists
from ntimporters.utils import dig, map_color, parse_timestamp

SPEC = {
    "code": "trello",  # codename / ID of importer
    "name": "Trello",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#trello",
    "input_fields": ("nt_auth_token", "app_key", "auth_token", "team_id"),
}
IMPORT_NAME = "Imported from Trello"


# main method called by Nozbe app
def run_import(
    nt_auth_token: str, auth_token: str, app_key: str, team_id: str
) -> Exception | str | None:
    """Perform import from Trello to Nozbe"""
    return run_safely(
        lambda: _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME), TrelloClient(app_key, auth_token)
        ),
        nt_auth_token=nt_auth_token,
        auth_token=auth_token,
        app_key=app_key,
    )


def _import_data(nz: NozbeImport, trello: TrelloClient):
    """Import boards (projects), lists (sections), cards (tasks)"""
    boards = trello.projects()
    nz.check_open_projects(board.get("name") for board in boards if not board.get("closed"))
    responsible = nz.members(trello.members_emails(boards), owner=trello.author_id)
    for board in boards:
        _import_board(nz, trello, board, responsible)


def _import_board(nz: NozbeImport, trello: TrelloClient, board: dict, responsible: dict):
    """Import board with its lists, labels and cards"""
    if not (
        nt_project_id := nz.project(
            board.get("name", ""),
            color=map_color(_color(dig(board, "prefs.background"))),
            description=board.get("desc") or "",
            is_favorite=board.get("is_fav"),
            ended=bool(board.get("closed")),
        )
    ):
        return
    cards, comments = trello.tasks(board.get("id")), trello.comments(board.get("id"))
    lists = [  # archived lists only if they hold open cards
        elt for elt in board.get("lists") or [] if not elt.get("closed") or cards.get(elt.get("id"))
    ]
    tag_ids = nz.tags(
        (_label_name(label), label.get("color")) for label in board.get("labels") or []
    )
    for position, trello_list in enumerate(lists):
        section_id = nz.section(
            nt_project_id,
            trello_list.get("name", ""),
            position,
            archived=bool(trello_list.get("closed")),
        )
        for card_position, card in enumerate(cards.get(trello_list.get("id")) or []):
            due = card.get("due")  # always has time
            nt_task_id, is_new = nz.task(
                nt_project_id,
                card.get("name", ""),
                section_id=section_id,
                position=card_position,
                due=isoparse(due) if due else None,
                responsible_id=first_true(map(responsible.get, card.get("idMembers") or [])),
                assigned=bool(card.get("idMembers")),
                ended_at=parse_timestamp(due) if card.get("dueComplete") else None,
            )
            if not nt_task_id:
                continue
            nz.assign_tags(
                nt_task_id,
                (tag_ids.get(_label_name(label)) for label in card.get("labels") or []),
                is_new,
            )
            _import_comments(nz, trello, nt_task_id, card, comments.get(card.get("id")) or [])


def _label_name(label: dict) -> str:
    """Label name; 'Unnamed' if empty"""
    return label.get("name") or "Unnamed"


def _import_comments(
    nz: NozbeImport, trello: TrelloClient, nt_task_id: str, card: dict, comments: list[str]
):
    """Description, comments (oldest first), checklists and attachments of card"""
    if desc := card.get("desc"):
        nz.comment(nt_task_id, desc)
    for text in comments + checklists(card):
        nz.comment(nt_task_id, text)
    for attachment in card.get("attachments") or []:
        nz.attachment(
            nt_task_id,
            attachment.get("name") or "attachment",
            attachment.get("url"),
            bool(attachment.get("isUpload")),
            trello.headers if _is_trello(attachment.get("url")) else None,
        )


def _is_trello(url: str | None) -> bool:
    """URL on trello.com (OAuth headers sent only there)"""
    host = urlparse(url or "").hostname or ""
    return host == "trello.com" or host.endswith(".trello.com")


def _color(background: str | None) -> str | None:
    """Trello board background name -> Nozbe color name (photos: None)"""
    return {"sky": "lightblue", "lime": "green", "grey": "stone"}.get(background, background)

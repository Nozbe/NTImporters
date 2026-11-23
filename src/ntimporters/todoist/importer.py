"""Todoist -> Nozbe importer"""

import itertools
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from operator import attrgetter
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Attachment, Due, Project, Task

from ntimporters.nozbe import File, NozbeImport, run_safely
from ntimporters.rate_limiting import RLProxy
from ntimporters.todoist.recurrence import to_rrule
from ntimporters.utils import dig

SPEC = {
    "code": "todoist",  # codename / ID of importer
    "name": "Todoist",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#todoist",
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}
IMPORT_NAME = "Imported from Todoist"


def unpack(paginator) -> list:
    """Flatten Todoist paginator"""
    return list(itertools.chain.from_iterable(paginator))


@dataclass(frozen=True)
class Ctx:
    """Import-wide state"""

    nz: NozbeImport
    todoist: RLProxy
    todoist_token: str
    time_zone: str
    tags: dict[str, str]


# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Exception | str | None:
    """Perform import from todoist to Nozbe"""
    return run_safely(
        lambda: _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME, with_single_tasks=True),
            RLProxy(TodoistAPI(auth_token)),
            auth_token,
        ),
        nt_auth_token=nt_auth_token,
        auth_token=auth_token,
    )


def _import_data(nz: NozbeImport, todoist, todoist_token: str):
    """Import everything from todoist to Nozbe"""
    projects = unpack(todoist.get_projects())
    nz.check_open_projects(project.name for project in projects if not project.is_inbox_project)
    ctx = Ctx(
        nz=nz,
        todoist=todoist,
        todoist_token=todoist_token,
        time_zone=_todoist_time_zone(todoist_token) or nz.time_zone,
        tags=nz.tags((label.name, label.color) for label in unpack(todoist.get_labels())),
    )
    for project in projects:
        _import_project(ctx, project)


def _todoist_time_zone(token: str) -> str | None:
    """Todoist user's time zone"""
    try:
        response = requests.get(
            "https://api.todoist.com/api/v1/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        response.raise_for_status()
        return dig(response.json(), "tz_info.timezone")
    except requests.RequestException:
        return None


def _import_project(ctx: Ctx, project: Project):
    """Import todoist project (Inbox into Single Tasks) with its sections and tasks"""
    if project.is_inbox_project:
        nt_project_id, sections = ctx.nz.single_tasks_id, {}
    elif nt_project_id := ctx.nz.project(project.name, is_favorite=project.is_favorite):
        sections = {
            section.id: section_id
            for section in unpack(ctx.todoist.get_sections(project_id=project.id))
            if (section_id := ctx.nz.section(nt_project_id, section.name, section.order))
        }
    if not nt_project_id:
        return
    assignees = _assignees(ctx, project)
    for task in unpack(ctx.todoist.get_tasks(project_id=project.id)):
        _import_task(ctx, task, nt_project_id, sections, assignees)


def _assignees(ctx: Ctx, project: Project) -> dict[str, str]:
    """Todoist collaborator id -> NT member id"""
    if not project.is_shared:
        return {}
    collaborators = unpack(ctx.todoist.get_collaborators(project_id=project.id))
    return ctx.nz.members({elt.id: elt.email for elt in collaborators})


def parse_due(due: Due | None, time_zone: str) -> tuple[int | None, bool]:
    """Due -> (due_at ms, is_all_day); date: UTC midnight, floating datetime: in due/user zone"""
    match due and due.date:
        case datetime() as moment:
            if not moment.tzinfo:
                moment = moment.replace(tzinfo=_zone(due.timezone or time_zone))
            return int(moment.timestamp() * 1000), False
        case date() as day:
            return int(datetime.combine(day, time(), UTC).timestamp() * 1000), True
    return None, False


def _zone(name: str) -> ZoneInfo:
    """ZoneInfo by name, UTC if unknown"""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        return ZoneInfo("UTC")


def _import_task(ctx: Ctx, task: Task, nt_project_id: str, sections: dict, assignees: dict):
    """Import todoist task with comments, tags and recurrence"""
    due_at, is_all_day = parse_due(task.due, ctx.time_zone)
    nt_task_id, is_new = ctx.nz.task(
        nt_project_id,
        task.content,
        section_id=sections.get(task.section_id),
        position=task.order or 1,
        due_at=due_at,
        is_all_day=is_all_day,
        responsible_id=assignees.get(task.assignee_id),
        assigned=bool(task.assignee_id),
    )
    if not nt_task_id:
        return
    if is_new and due_at is not None and task.due.is_recurring:
        _import_recurrence(ctx, nt_project_id, nt_task_id, task.due, is_all_day)
    _import_comments(ctx, nt_task_id, task)
    ctx.nz.assign_tags(nt_task_id, map(ctx.tags.get, task.labels or []), is_new)


def _import_recurrence(ctx: Ctx, nt_project_id: str, nt_task_id: str, due: Due, is_all_day: bool):
    """Set task recurrence; unparsed rule goes to a comment"""
    ctx.nz.recurrence(
        nt_project_id,
        nt_task_id,
        to_rrule(due.string, due.lang),
        is_all_day,
        f"Todoist: {due.string}",
    )


def _import_comments(ctx: Ctx, nt_task_id: str, task: Task):
    """Import description and comments with attachments"""
    if task.description:
        ctx.nz.comment(nt_task_id, task.description)
    for comment in sorted(
        unpack(ctx.todoist.get_comments(task_id=task.id)), key=attrgetter("posted_at")
    ):
        body, attachment = comment.content, comment.attachment
        if attachment and not attachment.file_url and attachment.url and attachment.url not in body:
            body = f"{body}\n{attachment.url}".strip()
        ctx.nz.comment(nt_task_id, body or _file_name(attachment), _file(ctx, attachment))


def _file_name(attachment: Attachment | None) -> str | None:
    """Attachment file name, without path (also comment body: kept as in earlier imports)"""
    return attachment and Path(attachment.file_name or attachment.title or "attachment").name


def _file(ctx: Ctx, attachment: Attachment | None) -> File | None:
    """(url, name, headers) of todoist file attachment; token sent to todoist only"""
    if not (attachment and attachment.file_url):
        return None
    host = urlparse(attachment.file_url).hostname or ""
    is_todoist = host == "todoist.com" or host.endswith(".todoist.com")
    return (
        attachment.file_url,
        _file_name(attachment),
        {"Authorization": f"Bearer {ctx.todoist_token}"} if is_todoist else None,
    )

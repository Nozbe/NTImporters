"""Todoist -> Nozbe importer"""

import itertools
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from operator import attrgetter
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import requests
from dataclass_wizard.errors import JSONWizardError
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Attachment, Comment, Due, Project, Task

from ntimporters.nozbe import File, NozbeImport, run_safely
from ntimporters.todoist.recurrence import to_rrule
from ntimporters.utils import dig, log, session

SPEC = {
    "code": "todoist",
    "name": "Todoist",
    "url": "https://nozbe.help/advancedfeatures/importers/#todoist",
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}
IMPORT_NAME = "Imported from Todoist"
API_URL = "https://api.todoist.com/api/v1"
RETRIES = 10
MAX_WAIT = 300  # s; worst case ~50 min/request


class RetryTransport(httpx.HTTPTransport):
    """429/503: retry <= RETRIES; sleep Retry-After s (<= MAX_WAIT), else 1, 2, 4 .. 60 s"""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(RETRIES):
            response = super().handle_request(request)
            if response.status_code not in (429, 503):
                return response
            response.close()
            after = response.headers.get("Retry-After", "")
            time.sleep(min(int(after), MAX_WAIT) if after.isdigit() else min(2**attempt, 60))
        return super().handle_request(request)


def unpack(paginator) -> list:
    """paginator -> flat list"""
    return list(itertools.chain.from_iterable(paginator))


@dataclass(frozen=True)
class Ctx:
    """import-wide state; comments: see _comments"""

    nz: NozbeImport
    todoist: TodoistAPI
    todoist_token: str
    owner: str | None
    time_zone: str
    tags: dict[str, str]
    comments: dict[str, list[Comment] | None] | None


# Nozbe app entry point
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Exception | str | None:
    """Todoist -> Nozbe"""
    return run_safely(
        lambda: _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME, with_single_tasks=True),
            TodoistAPI(auth_token, client=httpx.Client(transport=RetryTransport())),
            auth_token,
        ),
        nt_auth_token=nt_auth_token,
        auth_token=auth_token,
    )


def _import_data(nz: NozbeImport, todoist, todoist_token: str):
    """projects, labels, comments, tasks"""
    projects = unpack(todoist.get_projects())
    nz.check_open_projects(project.name for project in projects if not project.is_inbox_project)
    user = _todoist_user(todoist_token)
    ctx = Ctx(
        nz=nz,
        todoist=todoist,
        todoist_token=todoist_token,
        owner=user.get("id"),
        time_zone=dig(user, "tz_info.timezone") or nz.time_zone,
        tags=nz.tags((label.name, label.color) for label in unpack(todoist.get_labels())),
        comments=_comments(todoist_token),
    )
    for project in projects:
        _import_project(ctx, project)


def _todoist_user(token: str) -> dict:
    """token owner; {}: request failed"""
    try:
        response = session({"Authorization": f"Bearer {token}"}).get(f"{API_URL}/user", timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {}


def _comments(token: str) -> dict[str, list[Comment] | None] | None:
    """task id -> live comments, one notes sync; value None: incomplete; None: sync failed"""
    try:
        response = session({"Authorization": f"Bearer {token}"}).post(
            f"{API_URL}/sync", data={"sync_token": "*", "resource_types": '["notes"]'}, timeout=60
        )
        response.raise_for_status()
        sync = response.json()
        comments = defaultdict(list)
        for note in sync.get("notes") or []:
            if not note.get("is_deleted"):
                comments[note.get("item_id")].append(Comment.from_dict(note))
    except (requests.RequestException, JSONWizardError, ValueError, TypeError, KeyError) as exc:
        log.warning("Todoist comments sync failed, fetching per task: %s", exc)
        return None
    return comments | dict.fromkeys(sync.get("incomplete_item_ids") or [])


def _import_project(ctx: Ctx, project: Project):
    """project, sections, tasks; Inbox -> Single Tasks"""
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
    """collaborator id -> NT member id; {}: not shared"""
    if not project.is_shared:
        return {}
    collaborators = unpack(ctx.todoist.get_collaborators(project_id=project.id))
    return ctx.nz.members({elt.id: elt.email for elt in collaborators}, owner=ctx.owner)


def parse_due(due: Due | None, time_zone: str) -> date | datetime | None:
    """date | aware datetime; floating -> due zone, else user zone"""
    match due and due.date:
        case datetime() as moment if not moment.tzinfo:
            return moment.replace(tzinfo=_zone(due.timezone or time_zone))
        case date() as value:  # date | aware datetime
            return value
    return None


def _zone(name: str) -> ZoneInfo:
    """UTC if unknown"""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        return ZoneInfo("UTC")


def _import_task(ctx: Ctx, task: Task, nt_project_id: str, sections: dict, assignees: dict):
    """task, comments, tags, recurrence"""
    nt_task_id, is_new = ctx.nz.task(
        nt_project_id,
        task.content,
        section_id=sections.get(task.section_id),
        position=task.order or 1,
        due=parse_due(task.due, ctx.time_zone),
        responsible_id=assignees.get(task.assignee_id),
        assigned=bool(task.assignee_id),
        recurrence=(
            (to_rrule(task.due.string, task.due.lang), f"Todoist: {task.due.string}")
            if task.due and task.due.is_recurring
            else None
        ),
    )
    if not nt_task_id:
        return
    _import_comments(ctx, nt_task_id, task)
    ctx.nz.assign_tags(nt_task_id, map(ctx.tags.get, task.labels or []), is_new)


def _import_comments(ctx: Ctx, nt_task_id: str, task: Task):
    """description, comments by posted_at, attachments; per-task fetch if not synced"""
    if task.description:
        ctx.nz.comment(nt_task_id, task.description)
    comments = None if ctx.comments is None else ctx.comments.get(task.id, [])
    if comments is None:
        comments = unpack(ctx.todoist.get_comments(task_id=task.id))
    for comment in sorted(comments, key=attrgetter("posted_at")):
        body, attachment = comment.content, comment.attachment
        if attachment and not attachment.file_url and attachment.url and attachment.url not in body:
            body = f"{body}\n{attachment.url}".strip()
        ctx.nz.comment(nt_task_id, body or _file_name(attachment), _file(ctx, attachment))


def _file_name(attachment: Attachment | None) -> str | None:
    """basename; also empty comment body (as earlier imports)"""
    return attachment and Path(attachment.file_name or attachment.title or "attachment").name


def _file(ctx: Ctx, attachment: Attachment | None) -> File | None:
    """(url, name, headers); token only to *.todoist.com"""
    if not (attachment and attachment.file_url):
        return None
    host = urlparse(attachment.file_url).hostname or ""
    is_todoist = host == "todoist.com" or host.endswith(".todoist.com")
    return (
        attachment.file_url,
        _file_name(attachment),
        {"Authorization": f"Bearer {ctx.todoist_token}"} if is_todoist else None,
    )

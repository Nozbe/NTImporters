"""Todoist -> Nozbe importer"""

import itertools
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from operator import attrgetter
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import openapi_client as nt
import requests
from ntimporters.rate_limiting import RLProxy
from ntimporters.todoist.recurrence import to_rrule
from ntimporters.utils import (
    API_HOST,
    add_to_project_group,
    assign_tags,
    check_limits,
    current_nt_member,
    exists,
    get_imported_entities,
    get_single_tasks_project_id,
    id16,
    match_nt_users,
    nt_open_projects_len,
    nt_time_zone,
    post_tag,
    post_task_recurrence,
    set_unassigned_tag,
    trim,
    upload_attachment,
)
from openapi_client import api, models
from openapi_client.exceptions import OpenApiException
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Attachment, Due, Project, Task

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

    nt_client: nt.ApiClient
    todoist: RLProxy
    todoist_token: str
    team_id: str
    author_id: str
    single_tasks_id: str
    time_zone: str
    imported: dict
    tags: dict


# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Exception | None:
    """Perform import from todoist to Nozbe"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not auth_token:
        return "Missing 'auth_token'"

    try:
        _import_data(
            nt.ApiClient(
                configuration=nt.Configuration(
                    host=API_HOST,
                    api_key={"ApiKeyAuth": nt_auth_token},
                    username=nt_auth_token.split("_")[0],
                )
            ),
            RLProxy(TodoistAPI(auth_token)),
            auth_token,
            team_id,
            nt_auth_token,
        )
    except Exception as exc:
        return exc
    return None


def _import_data(nt_client, todoist, todoist_token: str, team_id: str, nt_auth_token: str):
    """Import everything from todoist to Nozbe"""
    projects = unpack(todoist.get_projects())
    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "projects_open",
        len(projects) + nt_open_projects_len(nt_client, team_id),
    )
    ctx = Ctx(
        nt_client=nt_client,
        todoist=todoist,
        todoist_token=todoist_token,
        team_id=team_id,
        author_id=current_nt_member(nt_client, team_id),
        single_tasks_id=get_single_tasks_project_id(nt_client, team_id),
        time_zone=_todoist_time_zone(todoist_token) or nt_time_zone(nt_client),
        imported=get_imported_entities(nt_client, team_id, IMPORT_NAME),
        tags=_import_tags(nt_client, todoist, team_id, nt_auth_token),
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
        return (response.json().get("tz_info") or {}).get("timezone")
    except requests.RequestException:
        return None


def _import_project(ctx: Ctx, project: Project):
    """Import todoist project with its sections and tasks"""
    if project.is_inbox_project:
        nt_project_id = ctx.single_tasks_id
    else:
        try:
            nt_project = exists(
                "projects", name := trim(project.name), ctx.imported
            ) or api.ProjectsApi(ctx.nt_client).post_project(
                models.Project(
                    name=name,
                    is_template=False,
                    team_id=ctx.team_id,
                    author_id=ctx.author_id,
                    created_at=1,
                    last_event_at=1,
                    is_favorite=project.is_favorite,
                    sidebar_position=1.0,
                    is_open=True,
                    extra="",
                )
            )
        except Exception as exc:
            print(exc)
            return
        if not (nt_project_id := nt_project and str(nt_project.id)):
            return
        add_to_project_group(ctx.nt_client, ctx.team_id, nt_project_id, IMPORT_NAME)

    is_sap = nt_project_id == ctx.single_tasks_id
    sections = {} if is_sap else _import_sections(ctx, nt_project_id, project.id)
    assignees = _assignees(ctx, project)
    for task in unpack(ctx.todoist.get_tasks(project_id=project.id)):
        _import_task(ctx, task, nt_project_id, sections, assignees, is_sap)


def _import_sections(ctx: Ctx, nt_project_id: str, project_id: str) -> dict[str, str]:
    """Import todoist sections; return todoist -> NT section id"""
    mapping = {}
    for section in unpack(ctx.todoist.get_sections(project_id=project_id)):
        try:
            if nt_section := exists(
                "project_sections", name := trim(section.name), ctx.imported, nt_project_id
            ) or api.ProjectSectionsApi(ctx.nt_client).post_project_section(
                models.ProjectSection(
                    id=id16(),
                    project_id=nt_project_id,
                    name=name,
                    created_at=1,
                    position=float(section.order),
                )
            ):
                mapping[section.id] = str(nt_section.id)
        except OpenApiException as exc:
            print(exc)
    return mapping


def _assignees(ctx: Ctx, project: Project) -> dict[str, str]:
    """Todoist collaborator id -> NT member id"""
    if not project.is_shared:
        return {}
    emails = {
        elt.id: elt.email for elt in unpack(ctx.todoist.get_collaborators(project_id=project.id))
    }
    matches = match_nt_users(ctx.nt_client, emails.values())
    return {uid: member for uid, email in emails.items() if (member := matches.get(email.lower()))}


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
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _import_task(
    ctx: Ctx, task: Task, nt_project_id: str, sections: dict, assignees: dict, is_sap: bool
):
    """Import todoist task with comments, tags and recurrence"""
    due_at, is_all_day = parse_due(task.due, ctx.time_zone)
    responsible_id = assignees.get(task.assignee_id)
    if is_sap and responsible_id:
        responsible_id = ctx.author_id
    if missing_responsible := not responsible_id and due_at is not None:
        responsible_id = ctx.author_id

    if nt_task := exists("tasks", name := trim(task.content), ctx.imported, nt_project_id):
        nt_task_id, is_new = str(nt_task.id), False
    elif nt_task := api.TasksApi(ctx.nt_client).post_task(
        models.Task(
            id=id16(),
            is_followed=False,
            is_abandoned=False,
            name=name,
            project_id=nt_project_id,
            author_id=ctx.author_id,
            missed_repeats=0,
            created_at=1,
            extra="",
            last_activity_at=1,
            project_section_id=sections.get(task.section_id),
            project_position=float(task.order or 1),
            due_at=due_at,
            is_all_day=is_all_day,
            responsible_id=responsible_id,
        )
    ):
        nt_task_id, is_new = str(nt_task.id), True
        if due_at is not None and task.due.is_recurring:
            _import_recurrence(ctx, nt_project_id, nt_task_id, task.due, is_all_day)
    else:
        return

    if not is_sap and missing_responsible:
        set_unassigned_tag(ctx.nt_client, nt_task_id)
    try:
        _import_comments(ctx, nt_task_id, task)
        assign_tags(ctx.nt_client, nt_task_id, map(ctx.tags.get, task.labels or []), not is_new)
    except Exception as exc:
        print(exc)


def _import_recurrence(ctx: Ctx, nt_project_id: str, nt_task_id: str, due: Due, is_all_day: bool):
    """Set task recurrence; unparsed rule goes to a comment"""
    try:
        if (pattern := to_rrule(due.string)) and post_task_recurrence(
            ctx.nt_client, nt_project_id, nt_task_id, pattern, is_all_day
        ):
            return
    except Exception as exc:
        print(exc)
    _post_comment(ctx, nt_task_id, f"Todoist: {due.string}")


def _import_tags(nt_client, todoist, team_id: str, nt_auth_token: str) -> dict[str, str]:
    """Import todoist labels; return name -> NT tag id"""
    nt_tags = {
        str(elt.name): str(elt.id) for elt in api.TagsApi(nt_client).get_tags(fields="id,name")
    }
    labels = unpack(todoist.get_labels())
    check_limits(nt_auth_token, team_id, nt_client, "tags", len(labels) + len(nt_tags))
    for label in labels:
        name = str(label.name)
        nt_tags[name] = nt_tags.get(name) or post_tag(nt_client, name, str(label.color))
    return nt_tags


def _import_comments(ctx: Ctx, nt_task_id: str, task: Task):
    """Import description and comments with attachments"""
    if task.description:
        _post_comment(ctx, nt_task_id, task.description)
    for comment in sorted(
        unpack(ctx.todoist.get_comments(task_id=task.id)), key=attrgetter("posted_at")
    ):
        body, attachment = comment.content, comment.attachment
        if attachment and not attachment.file_url and attachment.url not in (None, *body.split()):
            body = f"{body}\n{attachment.url}".strip()
        if (
            (nt_comment_id := _post_comment(ctx, nt_task_id, body or _file_name(attachment)))
            and attachment
            and attachment.file_url
        ):
            _upload_attachment(ctx, nt_comment_id, attachment)


def _post_comment(ctx: Ctx, nt_task_id: str, body: str | None) -> str | None:
    """Post comment unless imported before; return its id"""
    if exists("comments", body := str(body or "…"), ctx.imported, nt_task_id):
        return None
    nt_comment = api.CommentsApi(ctx.nt_client).post_comment(
        models.Comment(
            is_team=False,
            is_pinned=False,
            body=body,
            task_id=nt_task_id,
            author_id=ctx.author_id,
            created_at=1,
            extra="",
        )
    )
    return nt_comment and str(nt_comment.id)


def _file_name(attachment: Attachment | None) -> str | None:
    """Safe attachment file name"""
    return attachment and Path(attachment.file_name or attachment.title or "attachment").name


def _upload_attachment(ctx: Ctx, nt_comment_id: str, attachment: Attachment):
    """Copy todoist file into NT comment attachment"""
    host = urlparse(attachment.file_url).hostname or ""
    is_todoist = host == "todoist.com" or host.endswith(".todoist.com")
    upload_attachment(
        ctx.nt_client,
        nt_comment_id,
        attachment.file_url,
        _file_name(attachment),
        {"Authorization": f"Bearer {ctx.todoist_token}"} if is_todoist else None,
    )

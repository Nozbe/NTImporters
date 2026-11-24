"""Todoist -> Nozbe importer"""

import functools
import json
import shutil
import tempfile
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import openapi_client as nt
import requests
from dateutil.parser import isoparse
from ntimporters.rate_limiting import RLProxy
from ntimporters.todoist.recurrence import to_rrule
from ntimporters.utils import (
    add_to_project_group,
    check_limits,
    API_HOST,
    get_imported_entities,
    current_nt_member,
    exists,
    get_single_tasks_project_id,
    id16,
    match_nt_users,
    nt_members_by_email,
    nt_open_projects_len,
    post_tag,
    set_unassigned_tag,
    trim,
)
from openapi_client import models, api
from openapi_client.exceptions import ApiException, OpenApiException
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Attachment, Due

import itertools


def unpack(paginator):
    return list(itertools.chain.from_iterable(paginator))


SPEC = {
    "code": "todoist",  # codename / ID of importer
    "name": "Todoist",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#todoist",
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}
IMPORT_NAME = "Imported from Todoist"
API_URL = "https://api.todoist.com/api/v1"


# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Optional[Exception]:
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
            team_id,
            nt_auth_token,
            auth_token,
        )
    except Exception as exc:
        return exc
    return None


def _import_data(
    nt_client: nt.ApiClient, todoist_client, team_id: str, nt_auth_token: str, todoist_token: str
):
    """Import everything from todoist to Nozbe"""
    nt_project_api = api.ProjectsApi(nt_client)
    single_tasks_id = get_single_tasks_project_id(nt_client, team_id)
    imported = get_imported_entities(nt_client, team_id, IMPORT_NAME)
    author_id = current_nt_member(nt_client, team_id)

    def _import_project(project: dict):
        """Import todoist project"""
        if project.name != "Inbox":
            project_model = models.Project(
                name=(name := trim(project.name)),
                is_template=False,
                team_id=team_id,
                author_id=author_id,
                created_at=1,
                last_event_at=1,
                is_favorite=project.is_favorite,
                sidebar_position=1.0,
                is_open=True,
                extra="",
            )
            try:
                nt_project = (
                    exists("projects", name, imported)
                    or nt_project_api.post_project(project_model)
                    or {}
                )
            except Exception as e:
                print(e)
                return

            if not (nt_project_id := nt_project and str(nt_project.id)):
                return
            add_to_project_group(nt_client, team_id, nt_project_id, "Imported from Todoist")
        else:
            nt_project_id = single_tasks_id

        _import_project_sections(
            nt_client,
            todoist_client,
            nt_project_id,
            project,
            nt_members_by_email(nt_client, team_id),
            team_id,
            nt_auth_token,
            is_sap=nt_project_id == single_tasks_id,
            imported=imported,
            todoist_token=todoist_token,
        )

    todoist_projects = unpack(todoist_client.get_projects())
    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "projects_open",
        len(todoist_projects) + nt_open_projects_len(nt_client, team_id),
    )
    _import_members(nt_client, todoist_client, todoist_projects, team_id, nt_auth_token)
    for project in todoist_projects:
        _import_project(project)


def _import_members(
    nt_client, todoist_client, todoist_projects: list, team_id: str, nt_auth_token: str
):
    """Import members into Nozbe"""
    return  # TODO
    # nt_team_members_api = api.TeamMembersApi(nt_client)
    # active_nt_members =sum([True for elt in nt_team_members_api.get_team_members()
    # if elt.get("status") == "active"])
    # uniq_emails = set()
    # for project in todoist_projects:
    #     uniq_emails.update(todoist_members(todoist_client, project.id).values())
    # uniq_emails -= set(nt_members_by_email(nt_client)[0])
    # print(f"would import {uniq_emails=}")
    # TODO
    # check_limits(
    # nt_auth_token,
    # team_id,
    # nt_client,
    # "team_members", active_nt_members + len(uniq_emails))
    # for email in uniq_emails:
    #     if nt_user := api.UsersApi(nt_client).post_user(user_model):
    #         user_id = nt_user.get("id")
    #         nt_team_members_api.post_team_member(team_member_model)


# pylint: disable=too-many-arguments
def _import_project_sections(
    nt_client,
    todoist_client,
    nt_project_id: str,
    project: dict,
    nt_members: tuple[dict, str],
    team_id: str,
    nt_auth_token: str,
    is_sap: bool = False,
    imported=None,
    todoist_token: str = "",
):
    """Import todoist lists as project sections"""
    nt_api_sections = api.ProjectSectionsApi(nt_client)

    # import project sections
    mapping = {}
    if project.name != "Inbox":
        for section in unpack(todoist_client.get_sections(project_id=project.id)):
            try:
                name = trim(section.name)
                if nt_section := exists(
                    "project_sections_by_project", (nt_project_id, name), imported
                ) or nt_api_sections.post_project_section(
                    models.ProjectSection(
                        id=id16(),
                        project_id=nt_project_id,
                        name=name,
                        created_at=1,
                        position=float(section.order),
                    )
                ):
                    mapping[section.id] = str(nt_section.id)
            except OpenApiException as e:
                print(e)
    _import_tasks(
        nt_client,
        todoist_client,
        mapping,
        nt_members,
        nt_project_id,
        project.id,
        team_id,
        nt_auth_token,
        is_sap,
        imported=imported,
        todoist_token=todoist_token,
    )


def _import_tasks(
    nt_client,
    todoist_client,
    sections_mapping: dict,
    nt_members: dict,
    nt_project_id: str,
    to_project_id: str,
    team_id,
    nt_auth_token,
    is_sap: bool = False,
    imported=None,
    todoist_token: str = "",
):
    nt_api_tag_assignments = api.TagAssignmentsApi(nt_client)
    nt_api_tasks = api.TasksApi(nt_client)
    tags_mapping = _import_tags(nt_client, todoist_client, team_id, nt_auth_token)
    author_id = nt_members[1]

    def _get_responsible_id(task: dict):
        """Get NT responsible_id given todoist assignee id"""
        should_set_tag, responsible_id = False, None
        if task.get("assignee_id"):
            t_members = todoist_members(todoist_client, task.get("project_id"))
            user_matches = match_nt_users(nt_client, t_members.values())
            responsible_id = user_matches.get(t_members.get(task.get("assignee_id")))
        if is_sap and responsible_id and responsible_id != author_id:
            responsible_id = author_id
        if not responsible_id and task.get("due"):
            should_set_tag = True
            responsible_id = author_id

        return should_set_tag, responsible_id

    for todoist_task in unpack(todoist_client.get_tasks(project_id=to_project_id)):
        task = todoist_task.to_dict()
        due_at, is_all_day = parse_due(todoist_task.due, _time_zone(nt_client, todoist_token))
        should_set_tag, responsible_id = _get_responsible_id(task)
        name = trim(task.get("content", ""))
        existing = exists("tasks_by_project", (nt_project_id, name), imported)
        if nt_task := existing or nt_api_tasks.post_task(
            models.Task(
                id=id16(),
                is_followed=False,
                is_abandoned=False,
                name=name,
                project_id=nt_project_id,
                author_id=author_id,
                missed_repeats=0,
                created_at=1,
                extra="",
                last_activity_at=1,
                project_section_id=sections_mapping.get(task.get("section_id")),
                project_position=float(task.get("order") or 1),
                due_at=due_at,
                is_all_day=is_all_day,
                responsible_id=responsible_id,
                ended_at=_parse_timestamp(task.get("completed_at")),
            )
        ):
            if not is_sap and should_set_tag:
                set_unassigned_tag(nt_client, nt_task.id)
            due = todoist_task.due
            # imported task: due may be wrong (all day), recurrence would repeat it
            if not existing and due and due.is_recurring and not task.get("completed_at"):
                _set_recurrence(
                    nt_client, nt_project_id, str(nt_task.id), due, is_all_day, author_id
                )
            try:
                _import_comments(
                    nt_client,
                    todoist_client,
                    str(nt_task.id),
                    task,
                    todoist_token,
                    is_new=not existing,
                    author_id=author_id,
                )
                _import_tags_assignments(
                    nt_api_tag_assignments,
                    str(nt_task.id),
                    tags_mapping,
                    task.get("labels") or [],
                )
            except Exception as e:
                print(e)


# pylint: enable=too-many-arguments
@functools.cache
def todoist_members(todoist_client, project_id: str):
    """Get todoist collaborators per project"""
    return {
        elt.id: elt.email for elt in unpack(todoist_client.get_collaborators(project_id=project_id))
    }


def _import_tags_assignments(
    nt_api_tag_assignments, nt_task_id: str, tags_mapping: dict, task_tags: list
):
    """Assign tags to task"""
    for tag_name in task_tags:
        if nt_tag_id := tags_mapping.get(tag_name):
            try:
                nt_api_tag_assignments.post_tag_assignment(
                    models.TagAssignment(
                        id=id16(),
                        tag_id=nt_tag_id,
                        task_id=nt_task_id,
                    )
                )
            except Exception as e:
                print(e)


def _import_tags(nt_client, todoist_client, team_id: str, nt_auth_token: str) -> dict:
    """Import todoist tags and return name -> NT tag id mapping"""
    nt_api_tags = api.TagsApi(nt_client)
    nt_tags = {str(elt.name): str(elt.id) for elt in nt_api_tags.get_tags(fields="id,name")}
    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "tags",
        len(todoist_tags := unpack(todoist_client.get_labels())) + len(nt_tags),
    )
    for tag in todoist_tags:
        tag_name = str(tag.name)
        nt_tags[tag_name] = nt_tags.get(tag_name) or post_tag(nt_client, tag_name, str(tag.color))
    return nt_tags


def _parse_timestamp(value) -> int | None:
    """ISO string -> ms"""
    return int(isoparse(value).timestamp() * 1000) if isinstance(value, str) and value else None


def _zone(name: str | None) -> ZoneInfo:
    """UTC if unknown"""
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@functools.cache
def _time_zone(nt_client, todoist_token: str) -> str:
    """Todoist user's time zone, else Nozbe user's, else UTC"""
    try:
        response = requests.get(
            f"{API_URL}/user", headers={"Authorization": f"Bearer {todoist_token}"}, timeout=30
        )
        response.raise_for_status()
        if name := (response.json().get("tz_info") or {}).get("timezone"):
            return name
    except (requests.RequestException, ValueError, AttributeError) as exc:
        print(exc)
    try:
        user = api.UsersApi(nt_client).get_user_by_id(nt_client.configuration.username)
        return getattr(user, "time_zone", None) or "UTC"
    except OpenApiException as exc:
        print(exc)
    return "UTC"


def parse_due(due: Due | None, time_zone: str) -> tuple[int | None, bool]:
    """(due_at ms, is_all_day); date: UTC midnight; floating time: due zone, else time_zone"""
    match due and due.date:
        case datetime() as moment:
            if not moment.tzinfo:
                moment = moment.replace(tzinfo=_zone(due.timezone or time_zone))
            return int(moment.timestamp() * 1000), False
        case date() as day:
            return int(datetime.combine(day, time(), UTC).timestamp() * 1000), True
    return None, False


def _call(nt_client, method: str, path: str, body: dict) -> dict:
    """JSON body to Nozbe API path -> JSON reply; ApiException unless 2xx (client has no
    task recurrences, its Task needs all fields)"""
    response = nt_client.call_api(
        *nt_client.param_serialize(
            method,
            path,
            body=body,
            header_params={"Accept": "application/json", "Content-Type": "application/json"},
            auth_settings=["ApiKeyAuth"],
        )
    )
    response.read()
    if not 200 <= response.status < 300:
        raise ApiException(status=response.status, reason=response.reason, body=response.data)
    return json.loads(response.data or "{}")


def _set_recurrence(
    nt_client, nt_project_id: str, nt_task_id: str, due: Due, is_all_day: bool, author_id
):
    """RRULE of recurring due on task; unrecognised or refused: due string as comment"""
    if pattern := to_rrule(due.string, due.lang):
        try:
            recurrence_id = _call(
                nt_client,
                "POST",
                "/task_recurrences",
                {
                    "id": id16(),
                    "project_id": nt_project_id,
                    "current_task_id": nt_task_id,
                    "pattern": pattern,
                },
            ).get("id")
            # only fields sent are changed; is_all_day reset unless sent
            _call(
                nt_client,
                "PUT",
                f"/tasks/{nt_task_id}",
                {"recurrence_id": recurrence_id, "is_all_day": is_all_day},
            )
            return
        except OpenApiException as exc:
            print(exc)
    _post_comment(nt_client, nt_task_id, f"Todoist: {due.string}", author_id)


def _post_comment(nt_client, nt_task_id: str, body: str, author_id) -> str | None:
    """id of posted comment; None (printed) if refused"""
    try:
        return str(
            api.CommentsApi(nt_client)
            .post_comment(
                models.Comment(
                    is_team=False,
                    is_pinned=False,
                    body=body,
                    task_id=nt_task_id,
                    author_id=author_id or id16(),
                    created_at=1,
                    extra="",
                )
            )
            .id
        )
    except (OpenApiException, ValueError, AttributeError) as exc:
        print(exc)
    return None


def _comment_entries(task: dict, comments: list) -> list[tuple[str, Attachment | None]]:
    """(body, file attachment): description, then comments by posted_at; body as earlier
    imports ('…' if empty), except link only: link; link not in body: own entry"""
    entries = [(task.get("description"), None)] if task.get("description") else []
    for comment in sorted(comments, key=lambda elt: elt.posted_at):
        attachment = comment.attachment
        file = attachment if attachment and attachment.file_url else None
        url = attachment and not file and attachment.url
        if comment.content or file or not url:
            entries.append((comment.content or "…", file))
        if url and url not in (comment.content or ""):
            entries.append((url, None))
    return entries


def _import_comments(
    nt_client, todoist_client, nt_task_id: str, task: dict, todoist_token: str, is_new, author_id
):
    """comments + files; imported task: missing ones (body match, author's) and missing files"""
    existing = (
        {}
        if is_new
        else {
            str(elt.body): str(elt.id)
            for elt in api.CommentsApi(nt_client).get_comments(task_id=nt_task_id)
            if str(elt.author_id) == str(author_id)
        }
    )
    comments = unpack(todoist_client.get_comments(task_id=task.get("id")))
    for body, file in _comment_entries(task, comments):
        if comment_id := existing.get(body):
            if file and not api.AttachmentsApi(nt_client).getattachments(comment_id):
                _upload(nt_client, comment_id, file, todoist_token)
        elif (comment_id := _post_comment(nt_client, nt_task_id, body, author_id)) and file:
            _upload(nt_client, comment_id, file, todoist_token)


def _upload(nt_client, comment_id: str, attachment: Attachment, todoist_token: str):
    """Todoist file -> attachment of comment; token only to *.todoist.com; failure printed"""
    host = urlparse(attachment.file_url).hostname or ""
    is_todoist = host == "todoist.com" or host.endswith(".todoist.com")
    name = Path(attachment.file_name or attachment.title or "").name
    try:
        with (
            requests.get(
                attachment.file_url,
                headers={"Authorization": f"Bearer {todoist_token}"} if is_todoist else None,
                timeout=120,
                stream=True,
            ) as response,
            tempfile.TemporaryDirectory() as tmp,
        ):
            response.raise_for_status()
            response.raw.decode_content = True
            path = Path(tmp, name if name not in ("", ".", "..") else "attachment")
            with path.open("wb") as file:
                shutil.copyfileobj(response.raw, file)
            api.AttachmentsApi(nt_client).postattachment_by_id_content2(comment_id, file=str(path))
    except (requests.RequestException, OpenApiException, OSError) as exc:
        print(exc)

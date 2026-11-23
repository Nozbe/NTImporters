"""Common helper functions"""

import functools
import hashlib
import json
import random
import shutil
import string
import tempfile
from collections import UserDict
from datetime import UTC
from os import getenv
from pathlib import Path

import requests
from dateutil.parser import isoparse
from more_itertools import first, unique_everseen
from openapi_client import Color, api, models

HOST = "api4"
if getenv("DEV_ACCESS_TOKEN"):
    HOST = f"dev{HOST}"
API_HOST = getenv("CUSTOM_API_HOST") or f"https://{HOST}.nozbe.com/v1/api"
# API_HOST = "http://localhost:8888/v1/api"


def id16():
    """Generate random string"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


class ImportException(Exception):
    """Importer exception"""


def subscribe_trial(api_key: str, nt_team_id: str, members_len: int = 1) -> bool:
    """Return True if trial has been subscribed"""
    resp = requests.patch(
        "/".join((API_HOST.removesuffix("/api"), "teams", nt_team_id, "plan")),
        json={"members_len": members_len, "plan_type": "trial", "is_recurring": False, "creds": 0},
        headers={"Authorization": f"Apikey {api_key}", "API-Version": "current"},
    )
    return resp.status_code == 200


def nt_open_projects_len(nt_client, team_id: str):
    """Return number of open projects"""
    return sum(
        bool(elt.get("is_open"))
        and not any(elt.get(key) for key in ("ended_at", "is_template", "is_single_actions"))
        for elt in get_projects_per_team(nt_client, team_id)
    )


def check_limits(api_key: str, nt_team_id: str, nt_client, limit_name: str, current_len: int):
    """Raise an exception if limits exceeded"""
    # if "localhost" in API_HOST:
    #     return
    limits = nt_limits(nt_client, nt_team_id)
    if current_len > (limit := limits.get(limit_name, 0)) > -1 and not subscribe_trial(
        api_key, nt_team_id
    ):
        raise ImportException(f"LIMIT {limit_name} : {current_len} > {limit}")


def get_group_id(nt_client, team_id: str, group_name: str) -> str | None:
    """Get project group id if any"""
    groups = api.ProjectGroupsApi(nt_client).get_project_groups(
        limit=1, name=group_name, team_id=team_id
    )
    return (group := first(groups or [], None)) and str(group.id)


def exists(entity_type: str, name: str, imported_entities: dict, parent: str | None = None) -> dict:
    """Already imported entity by name (under parent id, if given), else Dict with id None"""
    key = name if parent is None else (str(parent), name)
    if imported_entities and (record := (imported_entities.get(entity_type) or {}).get(key)):
        return record
    return Dict({"id": None})


class Dict(UserDict):
    """Class pretending OpenApi object and dict in the same time"""

    @property
    def id(self):
        """Id as a property"""
        return self.get("id")

    def __len__(self):
        """Check if none"""
        return self.get("id") is not None


def get_imported_entities(
    nt_client, team_id, group_name, with_single_tasks: bool = False
) -> dict[str, dict]:
    """Records of group's projects (and Single Tasks if with_single_tasks);
    sections, tasks keyed (project_id, name), comments (task_id, body)"""
    projects, sections, tasks, comments, tags = {}, {}, {}, {}, {}

    def _add_tasks(project_id: str):
        for task in api.TasksApi(nt_client).get_tasks(project_id=project_id):
            tasks[(project_id, str(task.name))] = Dict({"id": task.id})
            task_id = str(task.id)
            for comment in api.CommentsApi(nt_client).get_comments(task_id=task_id):
                comments[(task_id, str(comment.body))] = Dict({"id": comment.id})

    if group_id := get_group_id(nt_client, team_id, group_name):
        for pgroup in api.GroupAssignmentsApi(nt_client).get_group_assignments(
            group_id=group_id, group_type="project"
        ):
            project = api.ProjectsApi(nt_client).get_project_by_id(str(pgroup.object_id))
            projects[str(project.name)] = Dict({"id": project.id})
            project_id = str(project.id)
            for section in api.ProjectSectionsApi(nt_client).get_project_sections(
                project_id=project_id
            ):
                sections[(project_id, str(section.name))] = Dict({"id": section.id})
            _add_tasks(project_id)
        tags = {str(tag.name): Dict({"id": tag.id}) for tag in api.TagsApi(nt_client).get_tags()}
    if with_single_tasks and (single_tasks_id := get_single_tasks_project_id(nt_client, team_id)):
        _add_tasks(single_tasks_id)
    return {
        "projects": projects,
        "project_sections": sections,
        "tasks": tasks,
        "comments": comments,
        "tags": tags,
    }


def add_to_project_group(nt_client, team_id: str, project_id: str, group_name: str):
    """Add newly created project to project group (created if missing)"""
    try:
        group_id = get_group_id(nt_client, team_id, group_name)
        if not group_id and (
            group := api.ProjectGroupsApi(nt_client).post_project_group(
                models.ProjectGroup(id=id16(), name=group_name, team_id=team_id, is_private=True)
            )
        ):
            group_id = group.id
        if group_id:
            api.GroupAssignmentsApi(nt_client).post_group_assignment(
                models.GroupAssignment(
                    id=id16(),
                    object_id=str(project_id),
                    group_id=str(group_id),
                    group_type="project",
                )
            )
    except Exception as exc:
        print(exc)


def set_unassigned_tag(nt_client, task_id: str):
    """set 'missing responsibility' tag"""
    assign_tags(nt_client, str(task_id), [post_tag(nt_client, "missing responsibility", None)])


def assign_tags(nt_client, nt_task_id: str, tag_ids, is_new: bool = False):
    """Assign NT tags to task, skipping already assigned ones (none on a new task)"""
    if not (tag_ids := list(unique_everseen(map(str, filter(None, tag_ids))))):
        return
    tag_assignments = api.TagAssignmentsApi(nt_client)
    assigned = (
        set()
        if is_new
        else {str(elt.tag_id) for elt in tag_assignments.get_tag_assignments(task_id=nt_task_id)}
    )
    for tag_id in (elt for elt in tag_ids if elt not in assigned):
        try:
            tag_assignments.post_tag_assignment(
                models.TagAssignment(id=id16(), tag_id=tag_id, task_id=nt_task_id)
            )
        except Exception as exc:
            print(exc)


def post_comment(nt_client, nt_task_id: str, body: str | None, author_id: str, imported: dict):
    """Post comment unless imported before; return its id"""
    if exists("comments", body := str(body or "…"), imported, nt_task_id):
        return None
    nt_comment = api.CommentsApi(nt_client).post_comment(
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
    return nt_comment and str(nt_comment.id)


def nt_limits(nt_client, team_id: str):
    """Check Nozbe limits"""
    if (team := api.TeamsApi(nt_client).get_team_by_id(team_id)) and hasattr(team, "limits"):
        return json.loads(team.limits)
    return {}


def map_color(color: str | None) -> Color:
    """Maps color onto Nozbe color"""
    colors = [elt.value for elt in Color if elt.value != "null"]
    return Color(color if color in colors else random.choice(colors))  # nosec


def get_projects_per_team(nt_client, team_id: str) -> list[dict]:
    """Get team-related projects"""
    return [
        dict(project)
        for project in api.ProjectsApi(nt_client).get_projects(
            team_id=team_id,
            limit=10000,
            fields=(
                "id,name,author_id,created_at,last_event_at,ended_at,"
                "team_id,is_open,is_single_actions"
            ),
        )
    ]


def get_single_tasks_project_id(nt_client, team_id: str) -> str | None:
    """Returns NT Single Tasks's project ID"""
    projects = api.ProjectsApi(nt_client).get_projects(
        limit=1, team_id=team_id, is_single_actions=True
    )
    return (project := first(projects or [], None)) and str(project.id)


def current_nt_member(nt_client, team_id: str | None = None) -> str:
    """Map current NT member id"""
    return nt_members_by_email(nt_client, team_id)[1] or id16()


@functools.cache
def nt_members_by_email(nt_client, team_id: str | None = None) -> tuple[dict, str | None]:
    """(NT email -> member id, current member id)"""
    nt_members = {
        str(elt.user_id): str(elt.id)
        for elt in api.TeamMembersApi(nt_client).get_team_members()
        if not team_id or elt.team_id == team_id
    }
    mapping = {
        str(email): nt_members.get(str(user.id))
        for user in api.UsersApi(nt_client).get_users()
        if (email := _user_email(user))
    }
    return mapping, nt_members.get(nt_client.configuration.username)


def _user_email(user) -> str | None:
    """User's email, else invitation email"""
    return getattr(user, "email", None) or getattr(user, "invitation_email", None)


def trim(name: str | None) -> str:
    """First 255 characters, "Untitled" if empty"""
    return (name or "")[:255] or "Untitled"


def parse_timestamp(datetime: str | None) -> int | None:
    """ISO date/datetime -> ms; date-only or naive as UTC"""
    if not datetime:
        return None
    moment = isoparse(datetime)
    return int((moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp() * 1000)


def upload_attachment(nt_client, nt_comment_id: str, url: str, name: str, headers=None):
    """Download url, attach it to NT comment as file name"""
    try:
        with (
            requests.get(url, headers=headers or {}, timeout=120, stream=True) as response,
            tempfile.TemporaryDirectory() as tmp,
        ):
            response.raise_for_status()
            response.raw.decode_content = True
            with (path := Path(tmp, Path(name).name or "attachment")).open("wb") as file:
                shutil.copyfileobj(response.raw, file)
            api.AttachmentsApi(nt_client).postattachment_by_id_content2(
                nt_comment_id, file=str(path)
            )
    except Exception as exc:
        print(exc)


def post_tag(nt_client, tag_name: str, color: str | None) -> str | None:
    """Id of tag by name, posted if missing"""
    if tag := first(api.TagsApi(nt_client).get_tags(limit=1, name=tag_name) or [], None):
        return str(tag.id)
    try:
        nt_tag = api.TagsApi(nt_client).post_tag(
            models.Tag(id=id16(), name=trim(tag_name), team_id=None, color=map_color(color))
        )
        return str(nt_tag.id) if nt_tag else None
    except Exception as exc:
        print(exc)
    return None


def post_task_recurrence(
    nt_client, project_id: str, task_id: str, pattern: str, is_all_day: bool
) -> str | None:
    """Create recurrence (RRULE pattern) of an existing task with due_at; return its id"""
    response = nt_client.call_api(
        *nt_client.param_serialize(
            "POST",
            "/task_recurrences",
            header_params={"Accept": "application/json", "Content-Type": "application/json"},
            body={"project_id": project_id, "current_task_id": task_id, "pattern": pattern},
            auth_settings=["ApiKeyAuth"],
        )
    )
    response.read()
    if response.status not in (200, 201) or not (
        recurrence_id := json.loads(response.data).get("id")
    ):
        return None
    api.TasksApi(nt_client).put_task_by_id(
        task_id,
        # PUT /tasks resets is_all_day unless sent
        {"recurrence_id": recurrence_id, "is_all_day": is_all_day},
    )
    return recurrence_id


def nt_time_zone(nt_client) -> str:
    """Current NT user's time zone, UTC if unset"""
    user = api.UsersApi(nt_client).get_user_by_id(nt_client.configuration.username)
    return str(getattr(user, "time_zone", None) or "UTC")


def match_nt_users(nt_client, emails) -> dict[str, str]:
    """3rd party email (lowercased) -> NT member id; NT email may be md5(user_id + email)"""

    def md5(email: str, user_id: str) -> str:
        return hashlib.md5((user_id + email).encode()).hexdigest()  # nosec

    nt_users = [
        (str(email), str(user.id))
        for user in api.UsersApi(nt_client).get_users()
        if (email := _user_email(user))
    ]
    pairs = {
        email: user_id
        for email in {elt.lower() for elt in emails if elt}
        if (
            user_id := first(
                (uid for nt_email, uid in nt_users if nt_email in (email, md5(email, uid))), None
            )
        )
    }
    if not pairs:
        return {}
    nt_members = {
        str(elt.user_id): str(elt.id) for elt in api.TeamMembersApi(nt_client).get_team_members()
    }
    return {
        email: member for email, user_id in pairs.items() if (member := nt_members.get(user_id))
    }

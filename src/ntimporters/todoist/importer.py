"""todoist -> Nozbe Teams importer"""
import functools
from dataclasses import dataclass
from typing import Optional, Tuple

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.utils import (
    ImportException,
    check_limits,
    id16,
    map_color,
    nt_limits,
    strip_readonly,
)
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException
from todoist_api_python.api import TodoistAPI

from todoist import TodoistAPI as TodoistAPISync

SPEC = {
    "code": "todoist",  # codename / ID of importer
    "name": "todoist",  # name of application
    "url": "https://todoist.com/app/settings/integrations",
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}

# main method called by Nozbe Teams app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Optional[str]:
    """Perform import from todoist to Nozbe Teams"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not auth_token:
        return "Missing 'auth_token'"

    try:
        _import_data(
            nt.ApiClient(
                configuration=nt.Configuration(
                    host="https://devapi4.nozbe.com/v1/api",
                    api_key={"ApiKeyAuth": nt_auth_token},
                )
            ),
            TodoistAPI(auth_token),
            TodoistAPISync(auth_token),
            team_id,
        )

    except (ImportException, OpenApiException) as exc:
        return str(exc)
    return None


def _import_data(nt_client: nt.ApiClient, todoist_client, todoist_sync_client, team_id: str):
    """Import everything from todoist to Nozbe Teams"""
    limits = nt_limits(nt_client, team_id)
    nt_project_api = apis.ProjectsApi(nt_client)

    def _import_project(project: dict):
        """Import todoist project"""
        if project.name != "Inbox":
            project_model = models.Project(
                id=models.Id16ReadOnly(id16()),
                name=models.NameAllowEmpty(project.name),
                team_id=models.Id16(team_id),
                author_id=models.Id16ReadOnly(id16()),
                created_at=models.TimestampReadOnly(1),
                last_event_at=models.TimestampReadOnly(1),
                is_favorite=project.favorite,
                sidebar_position=None if not project.favorite else 1.0,
                is_open=project.shared,
                extra="",
            )
            nt_project = nt_project_api.post_project(strip_readonly(project_model)) or {}
        else:
            for nt_project in nt_project_api.get_projects():
                if nt_project.is_single_actions:
                    nt_project_id = str(nt_project.id)
                    break
        if not (nt_project_id := str(nt_project.get("id"))):
            return

        _import_project_sections(
            nt_client,
            todoist_client,
            todoist_sync_client,
            nt_project_id,
            project,
            nt_members_by_email(nt_client),
            limits,
        )

    todoist_projects = todoist_client.get_projects()
    check_limits(
        limits,
        "projects_open",
        sum([True for elt in todoist_projects if elt.shared])
        + sum(
            [
                True
                for elt in nt_project_api.get_projects()
                if elt.get("is_open") and not elt.get("ended_at")
            ]
        ),
    )
    _import_members(nt_client, todoist_client, todoist_projects, limits)
    for project in todoist_projects:
        _import_project(project)


def _import_members(nt_client, todoist_client, todoist_projects: list, limits):
    """Import members into Nozbe Teams"""
    nt_team_members_api = apis.TeamMembersApi(nt_client)
    active_nt_members = sum(
        [True for elt in nt_team_members_api.get_team_members() if elt.get("status") == "active"]
    )
    uniq_emails = set()
    for project in todoist_projects:
        uniq_emails.update(todoist_members(todoist_client, project.id).values())
    uniq_emails -= set(nt_members_by_email(nt_client)[0])
    print(f"would import {uniq_emails=}")
    # TODO needs change on NT backend
    # check_limits(limits, "team_members", active_nt_members + len(uniq_emails))
    # for email in uniq_emails:
    #     if nt_user := apis.UsersApi(nt_client).post_user(user_model):
    #         user_id = nt_user.get("id")
    #         nt_team_members_api.post_team_member(team_member_model)


# pylint: disable=too-many-arguments
def _import_project_sections(
    nt_client,
    todoist_client,
    todoist_sync_client,
    nt_project_id: str,
    project: dict,
    nt_members: tuple[dict, str],
    limits: dict,
):
    """Import todoist lists as project sections"""
    nt_api_sections = apis.ProjectSectionsApi(nt_client)

    # import project sections
    mapping = {}
    if project.name != "Inbox":
        for section in todoist_client.get_sections(project_id=project.id):
            if nt_section := nt_api_sections.post_project_section(
                strip_readonly(
                    models.ProjectSection(
                        models.Id16ReadOnly(id16()),
                        models.Id16(nt_project_id),
                        models.Name(section.name),
                        models.TimestampReadOnly(1),
                        position=float(section.order),
                    )
                )
            ):
                mapping[section.id] = str(nt_section.get("id"))
    _import_tasks(
        nt_client,
        todoist_client,
        todoist_sync_client,
        mapping,
        nt_members,
        limits,
        nt_project_id,
        project.id,
    )


def _import_tasks(
    nt_client,
    todoist_client,
    todoist_sync_client,
    sections_mapping: dict,
    nt_members: dict,
    limits: dict,
    nt_project_id: str,
    to_project_id: str,
):
    nt_api_tag_assignments = apis.TagAssignmentsApi(nt_client)
    nt_api_tasks = apis.TasksApi(nt_client)
    tags_mapping = _import_tags(nt_client, todoist_client, limits)

    def _parse_timestamp(todoist_date) -> Optional[models.TimestampNullable]:
        """Parses todoist timestamp into NT timestamp format"""
        if isinstance(todoist_date, str):
            return models.TimestampNullable(int(isoparse(todoist_date).timestamp() * 1000))

        if not todoist_date or not any((todoist_date.get("date"), todoist_date.get("datetime"))):
            return None
        return models.TimestampNullable(
            int(
                isoparse(todoist_date.get("datetime") or todoist_date.get("date")).timestamp()
                * 1000
            )
        )

    def _get_responsible_id(task):
        """Get NT responsible_id given todoist assignee id"""
        responsible_id = None
        if task.get("assignee") and (
            collaborators := todoist_members(todoist_client, task.get("project_id"))
        ):
            if todoist_email := collaborators.get(task.get("assignee")):
                responsible_id = nt_members[0].get(todoist_email)
        elif task.get("due"):  # task with due set must be assign to someone
            responsible_id = nt_members[1]

        return models.Id16Nullable(responsible_id)

    # get tasks and completed tasks, while completed tasks are fetched from sync api
    for task in todoist_sync_client.completed.get_all(project_id=to_project_id).get("items", []) + [
        task.to_dict() for task in todoist_client.get_tasks(project_id=to_project_id)
    ]:
        if nt_task := nt_api_tasks.post_task(
            strip_readonly(
                models.Task(
                    id=models.Id16ReadOnly(id16()),
                    name=models.Name(task.get("content")),
                    project_id=models.ProjectId(nt_project_id),
                    author_id=models.Id16ReadOnly(id16()),
                    created_at=models.TimestampReadOnly(1),
                    last_activity_at=models.TimestampReadOnly(1),
                    project_section_id=models.Id16Nullable(
                        sections_mapping.get(task.get("section_id"))
                    ),
                    project_position=float(task.get("order") or 1),
                    due_at=_parse_timestamp(task.get("due")),
                    responsible_id=_get_responsible_id(task),
                    ended_at=_parse_timestamp(task.get("completed_date")),
                )
            )
        ):
            _import_comments(nt_client, todoist_client, str(nt_task.id), task)
            _import_tags_assignments(
                nt_api_tag_assignments, str(nt_task.id), tags_mapping, task.get("label_ids") or []
            )


# pylint: enable=too-many-arguments
@functools.cache
def todoist_members(todoist_client, project_id: str):
    """Get todoist collaborators per project"""
    return {elt.id: elt.email for elt in todoist_client.get_collaborators(project_id=project_id)}


def _import_tags_assignments(
    nt_api_tag_assignments, nt_task_id: str, tags_mapping: dict, task_tags: list
):
    """Assign tags to task"""
    for tag_id in task_tags:
        if nt_tag_id := tags_mapping.get(str(tag_id)):
            nt_api_tag_assignments.post_tag_assignment(
                strip_readonly(
                    models.TagAssignment(
                        id=models.Id16ReadOnly(id16()),
                        tag_id=models.Id16(nt_tag_id),
                        task_id=models.Id16(nt_task_id),
                    )
                )
            )


def _import_tags(nt_client, todoist_client, limits) -> dict:
    """Import todoist tags and return name -> NT tag id mapping"""
    nt_api_tags = apis.TagsApi(nt_client)
    nt_tags = {
        str(elt.get("name")): str(elt.get("id")) for elt in nt_api_tags.get_tags(fields="id,name")
    }
    check_limits(limits, "tags", len(todoist_tags := todoist_client.get_labels()) + len(nt_tags))
    mapping = {}
    for tag in todoist_tags:
        if (tag_name := str(tag.name)) not in nt_tags and (
            nt_tag := nt_api_tags.post_tag(
                strip_readonly(
                    models.Tag(
                        models.Id16ReadOnly(id16()),
                        models.Name(tag_name),
                        color=map_color(str(tag.color)),  # TODO todoist color = some number
                        is_favorite=tag.favorite,
                    )
                )
            )
        ):
            mapping[tag.id] = str(nt_tag.id)
        elif tag_name in nt_tags:
            mapping[str(tag.id)] = nt_tags.get(tag_name)
    return mapping


@functools.cache
def nt_members_by_email(nt_client) -> Tuple[dict, str]:
    """Map NT emails to member ids"""
    nt_members = {
        str(elt.user_id): str(elt.id) for elt in apis.TeamMembersApi(nt_client).get_team_members()
    }
    mapping = {}
    current_user_id = None
    for user in apis.UsersApi(nt_client).get_users():
        if hasattr(user, "email") and user.email:
            email = user.email
        elif hasattr(user, "invitation_email") and user.invitation_email:
            email = user.invitation_email
        else:
            continue
        if bool(user.is_me):
            current_user_id = str(user.id)
        mapping[str(email)] = nt_members.get(str(user.id))
    return mapping, nt_members.get(current_user_id)


@dataclass
class Comment:
    content: str


def _import_comments(nt_client, todoist_client, nt_task_id: str, task: dict):
    """Import task-related comments"""
    nt_api_comments = apis.CommentsApi(nt_client)

    comments = sorted(
        todoist_client.get_comments(task_id=task.get("id")),
        key=lambda elt: isoparse(elt.posted).timestamp(),
    )
    if task.get("description"):
        comments.insert(0, Comment(content=task.get("description")))
    for comment in comments:
        nt_api_comments.post_comment(
            strip_readonly(
                models.Comment(
                    id=models.Id16ReadOnly(id16()),
                    body=comment.content,
                    task_id=models.Id16(nt_task_id),
                    author_id=models.Id16ReadOnly(id16()),
                    created_at=models.TimestampReadOnly(1),
                    # FIXME impossible to set ReadOnly for current API impl
                    extra="",
                )
            )
        )

"""Monday -> Nozbe importer"""
from typing import Optional

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.monday.monday_api import MondayClient
from ntimporters.utils import (
    API_HOST,
    ImportException,
    check_limits,
    current_nt_member,
    get_projects_per_team,
    id16,
    nt_limits,
    strip_readonly,
    trim,
)
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException

SPEC = {
    "code": "monday",  # codename / ID of importer
    "name": "Monday",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#monday",
    "input_fields": ("team_id", "nt_auth_token", "app_key"),
}


# main method called by Nozbe app
def run_import(nt_auth_token: str, app_key: str, team_id: str) -> Optional[Exception]:
    """Perform import from monday to Nozbe"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not app_key:
        return "Missing 'app_key'"

    try:
        _import_data(
            nt.ApiClient(
                configuration=nt.Configuration(
                    host=API_HOST,
                    api_key={"ApiKeyAuth": nt_auth_token},
                )
            ),
            MondayClient(app_key),
            team_id,
        )

    except (ImportException, OpenApiException) as exc:
        return exc
    return None


def _import_data(nt_client: nt.ApiClient, monday_client, team_id: str):
    """Import everything from monday to Nozbe"""
    limits = nt_limits(nt_client, team_id)
    projects_api = apis.ProjectsApi(nt_client)
    curr_member = current_nt_member(nt_client)

    def _import_project(project: dict, curr_member: str):
        """Import monday project"""
        project_model = models.Project(
            name=models.NameAllowEmpty(trim(project.get("name", ""))),
            team_id=models.Id16(team_id),
            author_id=models.Id16ReadOnly(id16()),
            created_at=models.TimestampReadOnly(1),
            last_event_at=models.TimestampReadOnly(1),
            ended_at=models.TimestampNullable(1)
            if project.get("state") in ("archived", "deleted")
            else None,
            sidebar_position=1.0,
            description=project.get("description"),
            is_open=project.get("board_kind") == "public",
            extra="",
        )
        nt_project = projects_api.post_project(strip_readonly(project_model)) or {}
        if not (nt_project_id := str(nt_project.get("id"))):
            return

        _import_project_sections(
            nt_client, monday_client, nt_project_id, project, limits, curr_member
        )

    monday_projects = monday_client.projects()
    monday_projects_open = [
        elt.get("id") for elt in monday_projects if elt.get("board_kind") == "public"
    ]
    nt_projects = get_projects_per_team(nt_client, team_id)
    check_limits(
        limits,
        "projects_open",
        len(monday_projects_open)
        + sum(
            [
                True
                for elt in nt_projects
                if (
                    elt.get("is_open")
                    and (not hasattr(elt, "ended_at") or not bool(elt.get("ended_at")))
                )
            ]
        ),
    )

    for project in monday_projects:
        _import_project(project, curr_member)


# pylint: disable=too-many-arguments
def _import_project_sections(
    nt_client, monday_client, nt_project_id, project, limits: dict, curr_member: str
):
    """Import monday lists as project sections"""
    nt_api_sections = apis.ProjectSectionsApi(nt_client)

    check_limits(
        limits,
        "project_sections",
        len(monday_sections := monday_client.sections(project.get("id"))),
    )
    sections_mapping = {}
    for section in monday_sections:
        if nt_section := nt_api_sections.post_project_section(
            strip_readonly(
                models.ProjectSection(
                    models.Id16ReadOnly(id16()),
                    models.Id16(nt_project_id),
                    models.Name(trim(section.get("title", ""))),
                    models.TimestampReadOnly(1),
                    archived_at=models.TimestampReadOnly(1) if section.get("archived") else None,
                    position=float(section.get("position") or 1.0),
                )
            )
        ):
            sections_mapping[section.get("id")] = str(nt_section.get("id"))
    _import_tasks(
        nt_client, monday_client, sections_mapping, project.get("id"), nt_project_id, curr_member
    )


def _import_tasks(
    nt_client, monday_client, sections_mapping, m_project_id, nt_project_id, author_id
):
    """Import tasks"""
    nt_api_tasks = apis.TasksApi(nt_client)
    for task in monday_client.tasks(m_project_id):
        if nt_task := nt_api_tasks.post_task(
            strip_readonly(
                models.Task(
                    name=models.Name(trim(task.get("name", ""))),
                    project_id=models.ProjectId(nt_project_id),
                    author_id=models.Id16ReadOnly(id16()),
                    created_at=models.TimestampReadOnly(1),
                    last_activity_at=models.TimestampReadOnly(1),
                    project_section_id=models.Id16Nullable(sections_mapping.get(task.get("group"))),
                    project_position=1.0,
                    due_at=task.get("due_at"),
                    is_all_day=task.get("is_all_day"),
                    responsible_id=author_id if task.get("due_at") else None,
                )
            )
        ):
            _import_comments(nt_client, monday_client, str(nt_task.id), task.get("id"))


# pylint: enable=too-many-arguments


def _import_comments(nt_client, monday_client, nt_task_id: str, tr_task_id: str):
    """Import task-related comments"""
    nt_api_comments = apis.CommentsApi(nt_client)
    for comment in sorted(
        monday_client.comments(tr_task_id),
        key=lambda elt: isoparse(elt.get("created_at")).timestamp(),
    ):
        nt_api_comments.post_comment(
            strip_readonly(
                models.Comment(
                    body=comment.get("text_body"),
                    task_id=models.Id16(nt_task_id),
                    created_at=models.TimestampReadOnly(1),
                    author_id=models.Id16ReadOnly(id16()),
                    extra="",
                )
            )
        )


# TODO import team members

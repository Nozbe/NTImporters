"""Monday -> Nozbe Teams importer"""
import json
from typing import Optional, Tuple

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.monday.monday_api import MondayClient
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException
from openapi_client.model.id16_read_only import Id16ReadOnly
from openapi_client.model.id16_read_only_nullable import Id16ReadOnlyNullable
from openapi_client.model.timestamp_read_only import TimestampReadOnly
from openapi_client.model_utils import ModelNormal

SPEC = {
    "code": "monday",  # codename / ID of importer
    "name": "Monday",  # name of application
    "url": "https://api.developer.monday.com/docs",
    "input_fields": ("team_id", "nt_auth_token", "app_key"),
}


class ImportException(Exception):
    """Import exception"""


def strip_readonly(model: ModelNormal):
    """Strip read only fields before sending to server"""
    for field in [
        elt
        for elt in model.attribute_map.values()
        if hasattr(model, elt)
        and isinstance(getattr(model, elt), (Id16ReadOnly, Id16ReadOnlyNullable, TimestampReadOnly))
    ]:
        del model.__dict__.get("_data_store")[field]
    return model


def id16():
    """Generate random string"""
    return 16 * "a"


# main method called by Nozbe Teams app
def run_import(nt_auth_token: str, app_key: str, team_id: str) -> Optional[str]:
    """Perform import from monday to Nozbe Teams"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not app_key:
        return "Missing 'app_key'"

    try:
        _import_data(
            nt.ApiClient(
                configuration=nt.Configuration(
                    # host="http://localhost:8888/v1/api",
                    host="https://api4.nozbe.com/v1/api",
                    api_key={"ApiKeyAuth": nt_auth_token},
                )
            ),
            MondayClient(app_key),
            team_id,
        )

    except (ImportException, OpenApiException) as exc:
        return str(exc)
    return None


def _import_data(nt_client: nt.ApiClient, monday_client, team_id: str):
    """Import everything from monday to Nozbe Teams"""
    limits = nt_limits(nt_client, team_id)
    print(f"{limits=}")
    projects_api = apis.ProjectsApi(nt_client)

    def _import_project(project: dict):
        """Import monday project"""
        project_model = models.Project(
            id=models.Id16ReadOnly(id16()),
            name=models.NameAllowEmpty(project.get("name")),
            team_id=models.Id16(team_id),
            author_id=models.Id16ReadOnly(id16()),
            created_at=models.TimestampReadOnly(1),
            last_event_at=models.TimestampReadOnly(1),
            ended_at=models.TimestampNullable(1)
            if project.get("state") in ("archived", "deleted")
            else None,
            description=project.get("description"),
            is_open=project.get("board_kind") == "public",
            extra="",
        )
        nt_project = projects_api.post_project(strip_readonly(project_model)) or {}
        if not (nt_project_id := str(nt_project.get("id"))):
            return

        _import_project_sections(
            nt_client, monday_client, nt_project_id, project, nt_members_by_email(nt_client), limits
        )

    nt_projects = [elt.get("id") for elt in projects_api.get_projects() if elt.is_open]
    monday_projects = monday_client.projects()
    monday_projects_open = [
        elt.get("id") for elt in monday_projects if elt.get("board_kind") == "public"
    ]
    if len(monday_projects_open) + len(nt_projects) > limits.get("projects_open") > 0:
        raise ImportException("LIMIT projects_open")
    for project in monday_projects:
        _import_project(project)


# pylint: disable=too-many-arguments
def _import_project_sections(
    nt_client, monday_client, nt_project_id, project, nt_members: tuple, limits: dict
):
    """Import monday lists as project sections"""
    nt_api_sections = apis.ProjectSectionsApi(nt_client)

    def _parse_timestamp(monday_timestamp: Optional[str]) -> Optional[models.TimestampNullable]:
        """Parses monday timestamp into NT timestamp format"""
        if not monday_timestamp:
            return None
        return models.TimestampNullable(int(isoparse(monday_timestamp).timestamp() * 1000))

    sections_mapping = {}
    if (
        len(monday_sections := monday_client.sections(project.get("id")))
        > limits.get("project_sections", 0)
        > 0
    ):
        raise ImportException("LIMIT project sections")
    for section in monday_sections:
        if nt_section := nt_api_sections.post_project_section(
            strip_readonly(
                models.ProjectSection(
                    models.Id16ReadOnly(id16()),
                    models.Id16(nt_project_id),
                    models.Name(section.get("title")),
                    models.TimestampReadOnly(1),
                    archived_at=models.TimestampReadOnly(1) if section.get("archived") else None,
                    position=float(section.get("position") or 1.0),
                )
            )
        ):
            sections_mapping[section.get("id")] = str(nt_section.get("id"))
    _import_tasks(
        nt_members, nt_client, monday_client, sections_mapping, project.get("id"), nt_project_id
    )


def _import_tasks(
    nt_members: tuple, nt_client, monday_client, sections_mapping, m_project_id, nt_project_id
):
    """Import tasks"""
    nt_api_tasks = apis.TasksApi(nt_client)
    _, author_id = nt_members
    for task in monday_client.tasks(m_project_id):
        due_at, responsible_id = task.get("due_at"), None
        if due_at:
            due_at = models.TimestampNullable(due_at) if due_at else None
            responsible_id = author_id
        if nt_task := nt_api_tasks.post_task(
            strip_readonly(
                models.Task(
                    id=models.Id16ReadOnly(id16()),
                    name=models.Name(task.get("name")),
                    project_id=models.ProjectId(nt_project_id),
                    author_id=models.Id16ReadOnly(id16()),
                    created_at=models.TimestampReadOnly(1),
                    last_activity_at=models.TimestampReadOnly(1),
                    project_section_id=models.Id16Nullable(sections_mapping.get(task.get("group"))),
                    project_position=1.0,
                    due_at=due_at,
                    responsible_id=models.Id16Nullable(responsible_id),
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
        # cannot create author_id read-only field
        nt_api_comments.post_comment(
            strip_readonly(
                models.Comment(
                    id=models.Id16ReadOnly(id16()),
                    body=comment.get("text_body"),
                    task_id=models.Id16(nt_task_id),
                    created_at=models.TimestampReadOnly(1),
                    author_id=models.Id16ReadOnly(id16()),
                    extra="",
                )
            )
        )


def nt_members_by_email(nt_client) -> Tuple[dict, str]:
    """Map NT emails to member ids"""
    nt_members = {
        str(elt.user_id): str(elt.id) for elt in apis.TeamMembersApi(nt_client).get_team_members()
    }
    mapping = {}
    current_user_id = None
    for user in apis.UsersApi(nt_client).get_users():
        if hasattr(user, "email"):
            email = user.email
        elif hasattr(user, "invitation_email"):
            email = user.invitation_email
        if bool(user.is_me):
            current_user_id = str(user.id)
        mapping[str(email)] = nt_members.get(str(user.id))
    return mapping, nt_members.get(current_user_id)


def nt_limits(nt_client, team_id: str):
    """Check Nozbe Teams limits"""
    if (team := apis.TeamsApi(nt_client).get_team_by_id(team_id)) and hasattr(team, "limits"):
        return json.loads(team.limits)
    return {}


# TODO import team members

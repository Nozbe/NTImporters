"""Monday -> Nozbe importer"""
import re
from typing import Optional

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.monday.monday_api import MondayClient
from ntimporters.utils import (
    API_HOST,
    add_to_project_group,
    check_limits,
    current_nt_member,
    exists,
    get_imported_entities,
    id16,
    match_nt_users,
    nt_open_projects_len,
    set_unassigned_tag,
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
IMPORT_NAME = "Imported from Monday"


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
            nt_auth_token,
        )

    except Exception as exc:
        return exc
    return None


def _import_data(nt_client: nt.ApiClient, monday_client, team_id: str, nt_auth_token: str):
    """Import everything from monday to Nozbe"""
    projects_api = apis.ProjectsApi(nt_client)
    curr_member = current_nt_member(nt_client)
    imported = get_imported_entities(nt_client, team_id, IMPORT_NAME)

    def _import_project(project: dict, curr_member: str):
        """Import monday project"""
        if project.get("name", "").startswith("Subitems of"):
            return
        project_model = models.Project(
            name=models.NameAllowEmpty(name := trim(project.get("name", ""))),
            team_id=models.Id16(team_id),
            author_id=models.Id16ReadOnly(id16()),
            created_at=models.TimestampReadOnly(1),
            last_event_at=models.TimestampReadOnly(1),
            is_template=False,
            ended_at=models.TimestampNullable(1)
            if project.get("state") in ("archived", "deleted")
            else None,
            sidebar_position=1.0,
            description=project.get("description"),
            is_open=project.get("board_kind") == "public",
            extra="",
        )
        nt_project = (
            exists("projects", name, imported)
            or projects_api.post_project(strip_readonly(project_model))
            or {}
        )
        if not (nt_project_id := str(nt_project.get("id"))):
            return
        add_to_project_group(nt_client, team_id, nt_project_id, IMPORT_NAME)

        _import_project_sections(
            nt_client,
            monday_client,
            nt_project_id,
            project,
            curr_member,
            team_id,
            nt_auth_token,
            imported=imported,
        )

    monday_projects = monday_client.projects()
    monday_projects_open = [
        elt.get("id") for elt in monday_projects if elt.get("board_kind") == "public"
    ]
    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "projects_open",
        len(monday_projects_open) + nt_open_projects_len(nt_client, team_id),
    )

    for project in monday_projects:
        if project.get("state") in ("archived", "deleted"):
            continue
        _import_project(project, curr_member)


# pylint: disable=too-many-arguments
def _import_project_sections(
    nt_client,
    monday_client,
    nt_project_id,
    project,
    curr_member: str,
    team_id: str,
    nt_auth_token: str,
    imported=None,
):
    """Import monday lists as project sections"""
    nt_api_sections = apis.ProjectSectionsApi(nt_client)
    imported = imported or {}

    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "project_sections",
        len(monday_sections := monday_client.sections(project.get("id"))),
    )
    sections_mapping = {}
    for section in monday_sections:
        try:
            if nt_section := exists(
                "project_sections", name := trim(section.get("title", "")), imported
            ) or nt_api_sections.post_project_section(
                strip_readonly(
                    models.ProjectSection(
                        models.Id16ReadOnly(id16()),
                        models.Id16(nt_project_id),
                        models.Name(name),
                        models.TimestampReadOnly(1),
                        archived_at=models.TimestampReadOnly(1)
                        if section.get("archived")
                        else None,
                        position=float(section.get("position") or 1.0),
                    )
                )
            ):
                sections_mapping[section.get("id")] = str(nt_section.get("id"))
        except OpenApiException:
            pass
    _import_tasks(
        nt_client,
        monday_client,
        sections_mapping,
        project.get("id"),
        nt_project_id,
        curr_member,
        imported=imported,
    )


def _import_tasks(
    nt_client,
    monday_client,
    sections_mapping,
    m_project_id,
    nt_project_id,
    author_id,
    imported=None,
):
    """Import tasks"""
    nt_api_tasks = apis.TasksApi(nt_client)
    monday_users = monday_client.users()
    nt_members = match_nt_users(nt_client, monday_users.values())
    for task in monday_client.tasks(m_project_id):
        responsible_id = None
        if task.get("assigned"):
            for resp in task.get("assigned") or []:
                email = monday_users.get(str(resp.get("id")))
                if responsible_id := nt_members.get(email):
                    break

        if nt_task := exists(
            "tasks", name := trim(task.get("name", "")), imported
        ) or nt_api_tasks.post_task(
            strip_readonly(
                models.Task(
                    is_followed=False,
                    is_abandoned=False,
                    missed_repeats=0,
                    name=models.Name(name),
                    project_id=models.ProjectId(nt_project_id),
                    author_id=models.Id16ReadOnly(id16()),
                    created_at=models.TimestampReadOnly(1),
                    last_activity_at=models.TimestampReadOnly(1),
                    project_section_id=models.Id16Nullable(sections_mapping.get(task.get("group"))),
                    project_position=float(task.get("position") or 1.0),
                    due_at=task.get("due_at"),
                    is_all_day=task.get("is_all_day"),
                    responsible_id=responsible_id if task.get("due_at") else None,
                )
            )
        ):
            if task.get("due_at") and not responsible_id:
                set_unassigned_tag(nt_client, str(nt_task.id))
            _import_comments(
                nt_client, monday_client, str(nt_task.id), task.get("id"), imported=imported
            )


# pylint: enable=too-many-arguments


def _import_comments(nt_client, monday_client, nt_task_id: str, tr_task_id: str, imported=None):
    """Import task-related comments"""
    nt_api_comments = apis.CommentsApi(nt_client)
    for comment in sorted(
        monday_client.comments(tr_task_id),
        key=lambda elt: isoparse(elt.get("created_at")).timestamp(),
    ):
        if not exists("comments", body := format_body(comment.get("text_body") or "…"), imported):
            nt_api_comments.post_comment(
                strip_readonly(
                    models.Comment(
                        is_pinned=False,
                        is_team=False,
                        body=body,
                        task_id=models.Id16(nt_task_id),
                        created_at=models.TimestampReadOnly(1),
                        author_id=models.Id16ReadOnly(id16()),
                        extra="",
                    )
                )
            )


def format_body(body) -> str:
    return re.sub(r"\* ", "- ", body)


# TODO import team members

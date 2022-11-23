"""Todoist -> Nozbe importer"""
import functools
from dataclasses import dataclass
from typing import Optional

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.rate_limiting import RLProxy
from ntimporters.utils import (
    API_HOST,
    add_to_project_group,
    check_limits,
    exists,
    get_imported_entities,
    get_single_tasks_project_id,
    id16,
    match_nt_users,
    nt_members_by_email,
    nt_open_projects_len,
    post_tag,
    set_unassigned_tag,
    strip_readonly,
    trim,
)
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException
from todoist_api_python.api import TodoistAPI

from todoist import TodoistAPI as TodoistAPISync

SPEC = {
    "code": "todoist",  # codename / ID of importer
    "name": "Todoist",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#todoist",
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}
IMPORT_NAME = "Imported from Todoist"

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
                )
            ),
            RLProxy(TodoistAPI(auth_token)),
            TodoistAPISync(auth_token),
            team_id,
            nt_auth_token,
        )

    except Exception as exc:
        return exc
    return None


def _import_data(
    nt_client: nt.ApiClient, todoist_client, todoist_sync_client, team_id: str, nt_auth_token: str
):
    """Import everything from todoist to Nozbe"""
    nt_project_api = apis.ProjectsApi(nt_client)
    single_tasks_id = get_single_tasks_project_id(nt_client, team_id)
    imported = get_imported_entities(nt_client, team_id, IMPORT_NAME)

    def _import_project(project: dict):
        """Import todoist project"""
        if project.name != "Inbox":
            project_model = models.Project(
                name=models.NameAllowEmpty(name := trim(project.name)),
                is_template=False,
                team_id=models.Id16(team_id),
                author_id=models.Id16ReadOnly(id16()),
                created_at=models.TimestampReadOnly(1),
                last_event_at=models.TimestampReadOnly(1),
                is_favorite=project.is_favorite,
                sidebar_position=1.0,
                is_open=True,
                extra="",
            )
            nt_project = (
                exists("projects", name, imported)
                or nt_project_api.post_project(strip_readonly(project_model))
                or {}
            )

            if not (nt_project_id := str(nt_project.get("id"))):
                return
            add_to_project_group(nt_client, team_id, nt_project_id, "Imported from Todoist")
        else:
            nt_project_id = single_tasks_id

        _import_project_sections(
            nt_client,
            todoist_client,
            todoist_sync_client,
            nt_project_id,
            project,
            nt_members_by_email(nt_client),
            team_id,
            nt_auth_token,
            is_sap=nt_project_id == single_tasks_id,
            imported=imported,
        )

    todoist_projects = todoist_client.get_projects()
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
    nt_team_members_api = apis.TeamMembersApi(nt_client)
    active_nt_members = sum(
        [True for elt in nt_team_members_api.get_team_members() if elt.get("status") == "active"]
    )
    uniq_emails = set()
    for project in todoist_projects:
        uniq_emails.update(todoist_members(todoist_client, project.id).values())
    uniq_emails -= set(nt_members_by_email(nt_client)[0])
    print(f"would import {uniq_emails=}")
    # TODO
    # check_limits(
    # nt_auth_token,
    # team_id,
    # nt_client,
    # "team_members", active_nt_members + len(uniq_emails))
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
    team_id: str,
    nt_auth_token: str,
    is_sap: bool = False,
    imported=None,
):
    """Import todoist lists as project sections"""
    nt_api_sections = apis.ProjectSectionsApi(nt_client)

    # import project sections
    mapping = {}
    if project.name != "Inbox":
        for section in todoist_client.get_sections(project_id=project.id):
            try:
                if nt_section := exists(
                    "project_sections", name := trim(section.name), imported
                ) or nt_api_sections.post_project_section(
                    strip_readonly(
                        models.ProjectSection(
                            models.Id16ReadOnly(id16()),
                            models.Id16(nt_project_id),
                            models.Name(name),
                            models.TimestampReadOnly(1),
                            position=float(section.order),
                        )
                    )
                ):
                    mapping[section.id] = str(nt_section.get("id"))
            except OpenApiException:
                pass
    _import_tasks(
        nt_client,
        todoist_client,
        todoist_sync_client,
        mapping,
        nt_members,
        nt_project_id,
        project.id,
        team_id,
        nt_auth_token,
        is_sap,
        imported=imported,
    )


def _import_tasks(
    nt_client,
    todoist_client,
    todoist_sync_client,
    sections_mapping: dict,
    nt_members: dict,
    nt_project_id: str,
    to_project_id: str,
    team_id,
    nt_auth_token,
    is_sap: bool = False,
    imported=None,
):
    nt_api_tag_assignments = apis.TagAssignmentsApi(nt_client)
    nt_api_tasks = apis.TasksApi(nt_client)
    tags_mapping = _import_tags(nt_client, todoist_client, team_id, nt_auth_token)

    def _parse_timestamp(todoist_date) -> Optional[models.TimestampNullable]:
        """Parses todoist timestamp into NT timestamp format"""
        if isinstance(todoist_date, str):
            return (
                models.TimestampNullable(int(isoparse(todoist_date).timestamp() * 1000)),
                len(todoist_date) == 10,
            )

        if not todoist_date or not any((todoist_date.get("date"), todoist_date.get("datetime"))):
            return None, False
        return (
            models.TimestampNullable(
                int(
                    isoparse(todoist_date.get("datetime") or todoist_date.get("date")).timestamp()
                    * 1000
                )
            ),
            todoist_date.get("datetime", None) is None,
        )

    def _get_responsible_id(task: dict):
        """Get NT responsible_id given todoist assignee id"""
        should_set_tag, responsible_id = False, None
        if task.get("assignee_id"):
            t_members = todoist_members(todoist_client, task.get("project_id"))
            user_matches = match_nt_users(nt_client, t_members.values())
            responsible_id = user_matches.get(t_members.get(task.get("assignee_id")))
        if is_sap and responsible_id and responsible_id != nt_members[1]:
            responsible_id = nt_members[1]
        if not responsible_id and task.get("due"):
            should_set_tag = True
            responsible_id = nt_members[1]

        return should_set_tag, responsible_id

    # get tasks and completed tasks, while completed tasks are fetched from sync api
    for task in todoist_sync_client.completed.get_all(project_id=to_project_id).get("items", []) + [
        task.to_dict() for task in todoist_client.get_tasks(project_id=to_project_id)
    ]:
        due_at, is_all_day = _parse_timestamp(task.get("due"))
        should_set_tag, responsible_id = _get_responsible_id(task)
        if nt_task := exists(
            "tasks", name := trim(task.get("content", "")), imported
        ) or nt_api_tasks.post_task(
            strip_readonly(
                models.Task(
                    is_followed=False,
                    is_abandoned=False,
                    name=models.Name(name),
                    project_id=models.ProjectId(nt_project_id),
                    author_id=models.Id16ReadOnly(id16()),
                    missed_repeats=0,
                    created_at=models.TimestampReadOnly(1),
                    last_activity_at=models.TimestampReadOnly(1),
                    project_section_id=models.Id16Nullable(
                        sections_mapping.get(task.get("section_id"))
                    ),
                    project_position=float(task.get("order") or 1),
                    due_at=due_at,
                    is_all_day=is_all_day,
                    responsible_id=responsible_id,
                    ended_at=_parse_timestamp(task.get("completed_date"))[0],
                )
            )
        ):
            if not is_sap and should_set_tag:
                set_unassigned_tag(nt_client, nt_task.id)
            try:
                _import_comments(
                    nt_client, todoist_client, str(nt_task.id), task, imported=imported
                )
                _import_tags_assignments(
                    nt_api_tag_assignments,
                    str(nt_task.id),
                    tags_mapping,
                    task.get("label_ids") or [],
                )
            except Exception:
                pass


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
            try:
                nt_api_tag_assignments.post_tag_assignment(
                    strip_readonly(
                        models.TagAssignment(
                            id=models.Id16ReadOnly(id16()),
                            tag_id=models.Id16(nt_tag_id),
                            task_id=models.Id16(nt_task_id),
                        )
                    )
                )
            except Exception:
                pass


def _import_tags(nt_client, todoist_client, team_id: str, nt_auth_token: str) -> dict:
    """Import todoist tags and return name -> NT tag id mapping"""
    nt_api_tags = apis.TagsApi(nt_client)
    nt_tags = {
        str(elt.get("name")): str(elt.get("id")) for elt in nt_api_tags.get_tags(fields="id,name")
    }
    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "tags",
        len(todoist_tags := todoist_client.get_labels()) + len(nt_tags),
    )
    mapping = {}
    for tag in todoist_tags:
        if (tag_name := str(tag.name)) not in nt_tags and (
            nt_tag_id := post_tag(nt_client, tag_name, tag.color)
        ):
            mapping[tag.id] = str(nt_tag_id)
        elif tag_name in nt_tags:
            mapping[str(tag.id)] = nt_tags.get(tag_name)
    return mapping


@dataclass
class Comment:
    """Fake Todoist comment class"""

    content: str


def _import_comments(nt_client, todoist_client, nt_task_id: str, task: dict, imported=None):
    """Import task-related comments"""
    nt_api_comments = apis.CommentsApi(nt_client)

    comments = sorted(
        todoist_client.get_comments(task_id=task.get("id")),
        key=lambda elt: isoparse(elt.posted_at).timestamp(),
    )
    if task.get("description"):
        comments.insert(0, Comment(content=task.get("description")))
    for comment in comments:
        if not exists("comments", body := str(comment.content or "…"), imported):
            nt_api_comments.post_comment(
                strip_readonly(
                    models.Comment(
                        is_team=False,
                        is_pinned=False,
                        body=body,
                        task_id=models.Id16(nt_task_id),
                        author_id=models.Id16ReadOnly(id16()),
                        is_pinned=False,
                        created_at=models.TimestampReadOnly(1),
                        # FIXME impossible to set ReadOnly for current API impl
                        extra="",
                    )
                )
            )

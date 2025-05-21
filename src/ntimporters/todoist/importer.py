"""Todoist -> Nozbe importer"""

import functools
from dataclasses import dataclass
from typing import Optional

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.rate_limiting import RLProxy
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
from openapi_client.exceptions import OpenApiException
from todoist_api_python.api import TodoistAPI

from todoist import TodoistAPI as TodoistAPISync
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
            TodoistAPISync(auth_token, api_version="v9"),
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
            todoist_sync_client,
            nt_project_id,
            project,
            nt_members_by_email(nt_client, team_id),
            team_id,
            nt_auth_token,
            is_sap=nt_project_id == single_tasks_id,
            imported=imported,
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
    nt_api_sections = api.ProjectSectionsApi(nt_client)

    # import project sections
    mapping = {}
    if project.name != "Inbox":
        for section in unpack(todoist_client.get_sections(project_id=project.id)):
            try:
                if nt_section := exists(
                    "project_sections", name := trim(section.name), imported
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
    nt_api_tag_assignments = api.TagAssignmentsApi(nt_client)
    nt_api_tasks = api.TasksApi(nt_client)
    tags_mapping = _import_tags(nt_client, todoist_client, team_id, nt_auth_token)
    author_id = nt_members[1]

    def _parse_timestamp(todoist_date):
        """Parses todoist timestamp into NT timestamp format"""
        if isinstance(todoist_date, str):
            return int(isoparse(todoist_date).timestamp() * 1000), len(todoist_date) == 10

        if not todoist_date or not any((todoist_date.get("date"), todoist_date.get("datetime"))):
            return None, False
        return (
            int(
                isoparse(todoist_date.get("datetime") or todoist_date.get("date")).timestamp()
                * 1000
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
        if is_sap and responsible_id and responsible_id != author_id:
            responsible_id = author_id
        if not responsible_id and task.get("due"):
            should_set_tag = True
            responsible_id = author_id

        return should_set_tag, responsible_id

    # get tasks and completed tasks, while completed tasks are fetched from sync api
    for task in todoist_sync_client.completed.get_all(project_id=to_project_id).get("items", []) + [
        task.to_dict() for task in unpack(todoist_client.get_tasks(project_id=to_project_id))
    ]:
        due_at, is_all_day = _parse_timestamp(task.get("due"))
        should_set_tag, responsible_id = _get_responsible_id(task)
        if nt_task := exists(
            "tasks", name := trim(task.get("content", "")), imported
        ) or nt_api_tasks.post_task(
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
                ended_at=_parse_timestamp(task.get("completed_date"))[0],
            )
        ):
            if not is_sap and should_set_tag:
                set_unassigned_tag(nt_client, nt_task.id)
            try:
                _import_comments(
                    nt_client,
                    todoist_client,
                    str(nt_task.id),
                    task,
                    imported=imported,
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
    return {elt.id: elt.email for elt in todoist_client.get_collaborators(project_id=project_id)}


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


@dataclass
class Comment:
    """Fake Todoist comment class"""

    content: str


def _import_comments(
    nt_client, todoist_client, nt_task_id: str, task: dict, imported=None, author_id=None
):
    """Import task-related comments"""
    nt_api_comments = api.CommentsApi(nt_client)

    comments = sorted(
        unpack(todoist_client.get_comments(task_id=task.get("id"))), key=lambda elt: elt.posted_at
    )
    if task.get("description"):
        comments.insert(0, Comment(content=task.get("description")))
    for comment in comments:
        if not exists("comments", body := str(comment.content or "…"), imported):
            nt_api_comments.post_comment(
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

"""Trello -> Nozbe importer"""
from typing import Optional

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.trello.trello_api import TrelloClient
from ntimporters.utils import (
    ImportException,
    check_limits,
    current_nt_member,
    get_projects_per_team,
    id16,
    map_color,
    nt_limits,
    strip_readonly,
)
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException

SPEC = {
    "code": "trello",  # codename / ID of importer
    "name": "Trello",  # name of application
    "url": "https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/",
    "input_fields": ("nt_auth_token", "auth_token", "app_key", "team_id"),
}

# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, app_key: str, team_id: str) -> Optional[str]:
    """Perform import from Trello to Nozbe"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not auth_token:
        return "Missing 'auth_token'"
    if not app_key:
        return "Missing 'app_key'"

    try:
        _import_data(
            nt.ApiClient(
                configuration=nt.Configuration(
                    host="https://api4.nozbe.com/v1/api",
                    api_key={"ApiKeyAuth": nt_auth_token},
                )
            ),
            TrelloClient(app_key, auth_token),
            team_id,
        )

    except (ImportException, OpenApiException) as exc:
        return str(exc)
    return None


def _import_data(nt_client: nt.ApiClient, trello_client, team_id: str):
    """Import everything from Trello to Nozbe"""
    limits = nt_limits(nt_client, team_id)
    projects_api = apis.ProjectsApi(nt_client)
    curr_member = current_nt_member(nt_client)

    def _import_project(project: dict, curr_member: str):
        """Import trello project"""
        project_model = models.Project(
            id=models.Id16ReadOnly(id16()),
            name=models.NameAllowEmpty(project.get("name")),
            team_id=models.Id16(team_id),
            author_id=models.Id16ReadOnly(id16()),
            created_at=models.TimestampReadOnly(1),
            last_event_at=models.TimestampReadOnly(1),
            color=map_color(project.get("backgroundTopColor")),
            description=str(project.get("desc") or ""),
            is_favorite=project.get("is_fav"),
            sidebar_position=None if not project.get("is_fav") else 1.0,
            is_open=True,
            extra="",
        )
        nt_project = projects_api.post_project(strip_readonly(project_model)) or {}

        if not (nt_project_id := str(nt_project.get("id"))):
            raise ImportException("creating project failed")

        _import_project_sections(
            nt_client,
            trello_client,
            nt_project_id,
            project,
            curr_member,
            limits,
        )

    nt_projects = get_projects_per_team(nt_client, team_id)
    check_limits(
        limits,
        "projects_open",
        len(trello_projects := trello_client.projects())
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
    for project in trello_projects:
        try:
            _import_project(project, curr_member)
        except ImportException as error:
            print(error)


# pylint: disable=too-many-arguments
def _import_project_sections(
    nt_client,
    trello_client,
    nt_project_id: str,
    project: dict,
    nt_member_id: str,
    limits: dict,
):
    """Import trello lists as project sections"""
    nt_api_sections = apis.ProjectSectionsApi(nt_client)
    nt_api_tasks = apis.TasksApi(nt_client)
    tags_mapping = _import_tags_per_project(nt_client, trello_client, project, limits)

    def _parse_timestamp(trello_timestamp: Optional[str]) -> Optional[models.TimestampNullable]:
        """Parses Trello timestamp into NT timestamp format"""
        if not trello_timestamp:
            return None
        return models.TimestampNullable(int(isoparse(trello_timestamp).timestamp() * 1000))

    # import project sections
    check_limits(
        limits,
        "project_sections",
        len(trello_sections := trello_client.sections(project.get("id"))),
    )
    for section in trello_sections:
        if nt_section := nt_api_sections.post_project_section(
            strip_readonly(
                models.ProjectSection(
                    models.Id16ReadOnly(id16()),
                    models.Id16(nt_project_id),
                    models.Name(section.get("name")),
                    models.TimestampReadOnly(1),
                    archived_at=models.TimestampNullable(1) if section.get("closed") else None,
                    position=1.0,
                )
            )
        ):
            for task in trello_client.tasks(section.get("id")):
                if nt_task := nt_api_tasks.post_task(
                    strip_readonly(
                        models.Task(
                            id=models.Id16ReadOnly(id16()),
                            name=models.Name(task.get("name")),
                            project_id=models.ProjectId(nt_project_id),
                            author_id=models.Id16ReadOnly(id16()),
                            created_at=models.TimestampReadOnly(1),
                            last_activity_at=models.TimestampReadOnly(1),
                            project_section_id=models.Id16Nullable(str(nt_section.id)),
                            project_position=1.0,
                            due_at=_parse_timestamp(task.get("due")),
                            responsible_id=models.Id16Nullable(
                                nt_member_id if task.get("due") else None
                            ),
                            ended_at=None
                            if not task.get("dueComplete")
                            else _parse_timestamp(task.get("due")),
                            # there is no ended_at time @ trello
                        )
                    )
                ):
                    _import_tags(nt_client, str(nt_task.id), task, tags_mapping)
                    _import_comments(nt_client, trello_client, str(nt_task.id), task.get("id"))
                    # TODO import attachments, reminders?


# pylint: enable=too-many-arguments


def _import_tags_per_project(nt_client, trello_client, project: dict, limits: dict) -> dict:
    """Import trello tags and return name -> NT tag id mapping"""
    nt_api_tags = apis.TagsApi(nt_client)
    nt_tags = {
        str(elt.get("name")): str(elt.get("id")) for elt in nt_api_tags.get_tags(fields="id,name")
    }
    check_limits(
        limits, "tags", len(trello_tags := trello_client.tags(project.get("id"))) + len(nt_tags)
    )
    for tag in trello_tags:
        if (tag_name := tag.get("name")) not in nt_tags and (
            nt_tag := nt_api_tags.post_tag(
                strip_readonly(
                    models.Tag(
                        models.Id16ReadOnly(id16()),
                        models.Name(tag_name),
                        color=map_color(tag.get("color")),
                    )
                )
            )
        ):
            nt_tags[tag_name] = str(nt_tag.id)
    return nt_tags


def _import_tags(nt_client, nt_task_id: str, task: dict, tags_mapping):
    """Assign tags to task"""
    nt_api_tag_assignments = apis.TagAssignmentsApi(nt_client)
    for tag in task.get("labels"):
        if nt_tag_id := tags_mapping.get(tag.get("name")):
            nt_api_tag_assignments.post_tag_assignment(
                strip_readonly(
                    models.TagAssignment(
                        id=models.Id16ReadOnly(id16()),
                        tag_id=models.Id16(nt_tag_id),
                        task_id=models.Id16(nt_task_id),
                    )
                )
            )


def _import_comments(nt_client, trello_client, nt_task_id: str, tr_task_id: str):
    """Import task-related comments"""
    nt_api_comments = apis.CommentsApi(nt_client)
    for comment in sorted(
        trello_client.comments(tr_task_id), key=lambda elt: isoparse(elt.get("date")).timestamp()
    ):
        nt_api_comments.post_comment(
            strip_readonly(
                models.Comment(
                    id=models.Id16ReadOnly(id16()),
                    body=comment.get("text"),
                    task_id=models.Id16(nt_task_id),
                    author_id=models.Id16ReadOnly(id16()),
                    created_at=models.TimestampReadOnly(1),
                    extra="",
                )
            )
        )


# def _import_members(nt_client, trello_client, team_id: str, limits: dict):
#     """ Invite Trello members to Nozbe """
#     nt_team_members = apis.TeamMembersApi(nt_client)
#     current_members_len = len(
#         [
#             elt.get("id")
#             for elt in nt_team_members.get_team_members()
#             if elt.get("status") == "active"
#         ]
#     )
#
# check_limits(
#     limits,
#     "team_members",
#      len(emails_to_invite := trello_client.members_emails()) + current_members_len
#
# )
#     for email in emails_to_invite:
#         print("inviting", email)
#         user_model = models.User(
#             id=models.Id16ReadOnly(id16()),
#             invitation_email=email,
#             name=models.Name(email),
#             color="avatarColor1",
#             is_placeholder=True,
#         )
#         if nt_user := apis.UsersApi(nt_client).post_user(strip_readonly(user_model)):
#             team_member_model = models.TeamMember(
#                 id=models.Id16ReadOnly(id16()),
#                 team_id=models.Id16(team_id),
#                 user_id=models.Id16(str(nt_user.id)),
#                 role="member",
#                 status="pending",
#             )
#             nt_member = apis.TeamMembersApi(nt_client).post_team_member(
#                 strip_readonly(team_member_model)
#             )

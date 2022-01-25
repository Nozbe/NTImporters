"""Trello -> Nozbe Teams importer"""
import random
import json
from typing import Optional, Tuple

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.trello.trello_api import TrelloClient
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException
from openapi_client.model.id16_read_only import Id16ReadOnly
from openapi_client.model.id16_read_only_nullable import Id16ReadOnlyNullable
from openapi_client.model.timestamp_read_only import TimestampReadOnly
from openapi_client.model_utils import ModelNormal


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


SPEC = {
    "code": "trello",  # codename / ID of importer
    "name": "Trello",  # name of application
    "url": "https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/",
    "input_fields": ("nt_auth_token", "auth_token", "app_key"),
}
COLORS = [
    "aquamarine",
    "aubergine",
    "blue",
    "brown",
    "burntsienna",
    "darkgreen",
    "deeppurple",
    "dustpink",
    "green",
    "heather",
    "indigo",
    "karmin",
    "lightblue",
    "lightpink",
    "mauve",
    "midnight",
    "navy",
    "ocean",
    "ocher",
    "olive",
    "orange",
    "pink",
    "purple",
    "red",
    "sand",
    "stone",
    "taupe",
    "teal",
    "ultramarine",
]


# main method called by Nozbe Teams app
def run_import(nt_auth_token: str, auth_token: str, app_key: str, team_id: str) -> Optional[str]:
    """Perform import from Trello to Nozbe Teams"""
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
                    host="http://api4.nozbe.com/v1/api",
                    api_key={"ApiKeyAuth": nt_auth_token},
                )
            ),
            TrelloClient(app_key, auth_token),
            team_id,
        )

    except (Exception, OpenApiException) as exc:
        return str(exc)
    return None


def _import_data(nt_client: nt.ApiClient, trello_client, team_id: str):
    """Import everything from Trello to Nozbe Teams"""
    limits = nt_limits(nt_client, team_id)
    projects_api = apis.ProjectsApi(nt_client)

    def _import_project(project: dict):
        """Import trello project"""
        project_model = models.Project(
            id=models.Id16ReadOnly(id16()),
            name=models.NameAllowEmpty(project.get("name")),
            team_id=models.Id16(team_id),
            author_id=models.Id16ReadOnly(id16()),
            created_at=models.TimestampReadOnly(1),
            last_event_at=models.TimestampReadOnly(1),
            color=_map_color(project.get("backgroundTopColor")),
            description=str(project.get("desc") or ""),
            is_favorite=project.get("is_fav"),
            sidebar_position=None if not project.get("is_fav") else 1.0,
            is_open=True,
            extra="",
        )
        nt_project = projects_api.post_project(strip_readonly(project_model)) or {}

        if not (nt_project_id := str(nt_project.get("id"))):
            raise Exception("creating project failed")

        if error := _import_project_sections(
            nt_client, trello_client, nt_project_id, project, nt_members_by_email(nt_client), limits
        ):
            raise Exception(error)

    nt_projects = [elt.get("id") for elt in projects_api.get_projects() if elt.is_open]
    if len(trello_projects := trello_client.projects()) + len(nt_projects) > 1000 > 0:
        raise Exception("LIMIT projects")
    for project in trello_projects:
        if error := _import_project(project):
            raise Exception(error)


def _import_project_sections(
    nt_client,
    trello_client,
    nt_project_id: str,
    project: dict,
    nt_members: tuple[dict, str],
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
    if (
        len(trello_sections := trello_client.sections(project.get("id")))
        > limits.get("project_sections", 0)
        > 0
    ):
        raise Exception("LIMIT project sections")
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
                                str(nt_members[1]) if task.get("due") else None
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


def _import_tags_per_project(nt_client, trello_client, project: dict, limits: dict) -> dict:
    """Import trello tags and return name -> NT tag id mapping"""
    nt_api_tags = apis.TagsApi(nt_client)
    nt_tags = {
        str(elt.get("name")): str(elt.get("id")) for elt in nt_api_tags.get_tags(fields="id,name")
    }
    if (
        len(trello_tags := trello_client.tags(project.get("id"))) + len(nt_tags)
        > limits.get("tags")
        > -1
    ):
        raise Exception("LIMIT tags")
    for tag in trello_tags:
        if (tag_name := tag.get("name")) not in nt_tags and (
            nt_tag := nt_api_tags.post_tag(
                strip_readonly(
                    models.Tag(
                        models.Id16ReadOnly(id16()),
                        models.Name(tag_name),
                        color=_map_color(tag.get("color")),
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


def _map_color(trello_color: Optional[str]) -> models.Color:
    """Maps Trello color onto Nozbe Teams color"""
    return models.Color(trello_color if trello_color in COLORS else random.choice(COLORS))  # nosec


def nt_limits(nt_client, team_id: str):
    """Check Nozbe Teams limits"""
    if (team := apis.TeamsApi(nt_client).get_team_by_id(team_id)) and hasattr(team, "limits"):
        return json.loads(team.limits)
    return {}


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
#     if (
#         len(emails_to_invite := trello_client.members_emails()) + current_members_len
#         > limits.get("team_members", 0)
#         > 0
#     ):
#         raise Exception("LIMIT team members")
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

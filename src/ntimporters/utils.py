""" Common helper functions """
import functools
import json
import random
from typing import Optional, Tuple

from dateutil.parser import isoparse
from openapi_client import apis, models
from openapi_client.model.color import Color
from openapi_client.model_utils import ModelNormal

API_HOST = "https://api4.nozbe.com/v1/api"
# API_HOST = "http://localhost:8888/v1/api"


def id16():
    """Generate random string"""
    return 16 * "a"


class ImportException(Exception):
    """Importer exception"""


def check_limits(limits: dict, limit_name: str, current_len: int):
    """Raise an exception if limits exceeded"""
    if current_len > (limit := limits.get(limit_name, 0)) > -1:
        raise ImportException(f"LIMIT {limit_name} : {current_len} > {limit}")


def strip_readonly(model: ModelNormal):
    """Strip read only fields before sending to server"""
    for field in [
        elt
        for elt in model.attribute_map.values()
        if hasattr(model, elt)
        and isinstance(
            getattr(model, elt),
            (models.Id16ReadOnly, models.Id16ReadOnlyNullable, models.TimestampReadOnly),
        )
    ]:
        del model.__dict__.get("_data_store")[field]
    return model


def set_unassigned_tag(nt_client, task_id: str) -> Optional[str]:
    """set 'missing responsability' tag"""
    tag_name, tag_id = "missing responsibility", None
    st_tags = _get_with_query(
        nt_client, apis.TagsApi(nt_client).get_tags_endpoint, [("limit", "1"), ("name", tag_name)]
    )
    tag_id = st_tags[0].get("id") if st_tags and st_tags[0] else None
    if not tag_id and (
        tag := apis.TagsApi(nt_client).post_tag(
            strip_readonly(
                models.Tag(
                    models.Id16ReadOnly(id16()),
                    models.Name(tag_name),
                    color=map_color(map_color(None)),
                    is_favorite=False,
                )
            )
        )
    ):
        tag_id = tag.get("id")
    if tag_id:
        assignment = strip_readonly(
            models.TagAssignment(
                id=models.Id16ReadOnly(id16()),
                tag_id=models.Id16(str(tag_id)),
                task_id=models.Id16(str(task_id)),
            )
        )
        apis.TagAssignmentsApi(nt_client).post_tag_assignment(assignment)


def nt_limits(nt_client, team_id: str):
    """Check Nozbe limits"""
    if (team := apis.TeamsApi(nt_client).get_team_by_id(team_id)) and hasattr(team, "limits"):
        return json.loads(team.limits)
    return {}


def map_color(color: Optional[str]) -> Color:
    """Maps color onto Nozbe color"""
    colors = list(list(Color.allowed_values.values())[0].values())
    colors.remove("null")
    return Color(color if color in colors else random.choice(colors))  # nosec


def get_projects_per_team(nt_client, team_id: str) -> Optional[str]:
    """Get team-related projects"""
    # temporary solution
    nt_project_api = apis.ProjectsApi(nt_client)
    return [
        project
        for project in nt_project_api.get_projects(
            limit=10000,
            fields="id,name,author_id,created_at,last_event_at,ended_at,team_id,is_open",
        )
        if str(project.team_id) == team_id
    ]


def _get_with_query(nt_client, api, query: list):
    settings = api.settings
    return nt_client.call_api(
        settings["endpoint_path"],
        settings["http_method"],
        None,
        query,
        {"Accept": "application/json"},
        response_type=settings["response_type"],
        auth_settings=settings["auth"],
        _check_type=True,
        _return_http_data_only=True,
        _preload_content=True,
    )


def get_single_tasks_project_id(nt_client, team_id: str) -> Optional[str]:
    """Returns NT Single Tasks's project ID"""
    st_projects = _get_with_query(
        nt_client,
        apis.ProjectsApi(nt_client).get_projects_endpoint,
        [("team_id", team_id), ("is_single_actions", True)],
    )
    return str(st_projects[0].get("id")) if st_projects and st_projects[0] else None


def current_nt_member(nt_client) -> Optional[str]:
    """Map current NT member id"""
    return nt_members_by_email(nt_client)[1]


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


def trim(name: str):
    """Return max 255 characters"""
    if isinstance(name, str):
        return name[:255]
    return name


def parse_timestamp(datetime: Optional[str]) -> Optional[models.TimestampNullable]:
    """Parses date string into timestamp"""
    if not datetime:
        return None
    return models.TimestampNullable(int(isoparse(datetime).timestamp() * 1000))

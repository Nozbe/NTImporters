""" Common helper functions """
import functools
import hashlib
from os import getenv
import json
import random
from collections import UserDict
from typing import Optional, Tuple

import requests
from dateutil.parser import isoparse
from openapi_client import apis, models
from openapi_client.model.color import Color
from openapi_client.model_utils import ModelNormal

HOST = "api4"
if getenv("DEV_ACCESS_TOKEN"):
    HOST = f"dev{HOST}"
API_HOST = f"https://{HOST}.nozbe.com/v1/api"
# API_HOST = f"http://localhost:8888/v1/api"


def id16():
    """Generate random string"""
    return 16 * "a"


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
        True
        for elt in get_projects_per_team(nt_client, team_id)
        if all(
            (
                elt.get("is_open"),
                (not hasattr(elt, "ended_at") or not bool(elt.get("ended_at"))),
                not elt.get("is_template"),
                not elt.get("is_single_actions"),
            )
        )
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


def get_group_id(nt_client, team_id: str, group_name: str) -> str | None:
    """Get project group id if any"""
    st_groups = _get_with_query(
        nt_client,
        apis.ProjectGroupsApi(nt_client).get_project_groups_endpoint,
        [("limit", "1"), ("name", group_name), ("team_id", team_id)],
    )
    return str(st_groups[0].get("id")) if st_groups and st_groups[0] else None


def exists(entity_type: str, name: str, imported_entities: dict[str, tuple[str, str]]) -> dict:
    """Check if entity already exists and return its id"""
    if imported_entities:
        if (records := imported_entities.get(entity_type)) and (record := records.get(name)):
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


def get_imported_entities(nt_client, team_id, group_name) -> dict[str, list]:
    """Get already imported records"""
    already_imported = []
    if group_id := get_group_id(nt_client, team_id, group_name):
        for pgroup in _get_with_query(
            nt_client,
            apis.GroupAssignmentsApi(nt_client).get_group_assignments_endpoint,
            [("group_id", group_id), ("group_type", "project")],
        ):
            project = apis.ProjectsApi(nt_client).get_project_by_id(str(pgroup.get("object_id")))
            already_imported.append(("project", project))
            for section in _get_with_query(
                nt_client,
                apis.ProjectSectionsApi(nt_client).get_project_sections_endpoint,
                [("project_id", str(project.get("id")))],
            ):
                already_imported.append(("project_section", section))
            for task in _get_with_query(
                nt_client,
                apis.TasksApi(nt_client).get_tasks_endpoint,
                [("project_id", str(project.get("id")))],
            ):
                already_imported.append(("task", task))
                for comment in _get_with_query(
                    nt_client,
                    apis.CommentsApi(nt_client).get_comments_endpoint,
                    [("task_id", str(task.get("id")))],
                ):
                    already_imported.append(("comment", comment))
                for tag in _get_with_query(
                    nt_client,
                    apis.TagsApi(nt_client).get_tags_endpoint,
                    [("task_id", str(task.get("id")))],
                ):
                    already_imported.append(("tag", tag))
    entities = {
        "comments": {
            str(elt[1].get("body")): Dict({"id": elt[1].get("id")})
            for elt in already_imported
            if elt[0] == "comment"
        }
    }
    for rtype in ("task", "tag", "project", "project_section"):
        entities[f"{rtype}s"] = {
            str(elt[1].get("name")): Dict({"id": elt[1].get("id")})
            for elt in already_imported
            if elt[0] == rtype
        }
    return entities


def add_to_project_group(nt_client, team_id: str, project_id: str, group_name: str):
    """Add project to project' group"""
    group_id = get_group_id(nt_client, team_id, group_name)

    try:
        if not group_id and (
            group := apis.ProjectGroupsApi(nt_client).post_project_group(
                strip_readonly(
                    models.ProjectGroup(
                        name=models.Name(group_name), team_id=models.Id16(team_id), is_private=True
                    )
                )
            )
        ):
            group_id = group.get("id")
        if group_id:
            assignment = strip_readonly(
                models.GroupAssignment(
                    object_id=models.Id16(str(project_id)),
                    group_id=models.Id16(str(group_id)),
                    group_type="project",
                )
            )
            apis.GroupAssignmentsApi(nt_client).post_group_assignment(assignment)
    except Exception:
        pass


def set_unassigned_tag(nt_client, task_id: str):
    """set 'missing responsibility' tag"""
    tag_name, tag_id = "missing responsibility", None
    st_tags = _get_with_query(
        nt_client, apis.TagsApi(nt_client).get_tags_endpoint, [("limit", "1"), ("name", tag_name)]
    )
    tag_id = st_tags[0].get("id") if st_tags and st_tags[0] else post_tag(nt_client, tag_name, None)
    if tag_id:
        assignment = strip_readonly(
            models.TagAssignment(
                id=models.Id16ReadOnly(id16()),
                tag_id=models.Id16(str(tag_id)),
                task_id=models.Id16(str(task_id)),
            )
        )
        try:
            apis.TagAssignmentsApi(nt_client).post_tag_assignment(assignment)
        except Exception:
            pass


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
            fields=(
                "id,name,author_id,created_at,last_event_at,ended_at,"
                "team_id,is_open,is_single_actions"
            ),
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
    # return (name or "Untitled")[:255]
    if isinstance(name, str):
        return name[:255] or "Untitled"
    return name or "Untitled"


def parse_timestamp(datetime: Optional[str]) -> Optional[models.TimestampNullable]:
    """Parses date string into timestamp"""
    if not datetime:
        return None
    return models.TimestampNullable(int(isoparse(datetime).timestamp() * 1000))


def post_tag(nt_client, tag_name: str, color: str):
    """Post tag to Nozbe"""
    try:
        nt_tag = apis.TagsApi(nt_client).post_tag(
            strip_readonly(
                models.Tag(
                    models.Id16ReadOnly(id16()),
                    models.Name(trim(tag_name)),
                    color=map_color(color),
                )
            )
        )
        return str(nt_tag.id) if nt_tag else None
    except Exception:
        pass
    return None


def match_nt_users(nt_client, emails: list) -> dict:
    """Match 3rd party with Nozbe users and return email,member id pairs"""

    def md5(email: str, user_id: str):
        "Calculate hash"
        return hashlib.md5((user_id + email.lower()).encode(encoding="utf-8")).hexdigest()  # nosec

    nt_users = [
        (str(elt.email if hasattr(elt, "email") else elt.invitation_email), str(elt.id))
        for elt in apis.UsersApi(nt_client).get_users()
        if any((hasattr(elt, "email"), hasattr(elt, "invitation_email")))
    ]
    pairs = []
    for email in emails:
        if not email:
            continue
        for nt_user in nt_users:
            l_email = email.lower()
            if nt_user[0] == l_email or nt_user[0] == md5(l_email, nt_user[1]):
                pairs.append((l_email, nt_user[1]))
                break
    if pairs:
        nt_members = {
            str(elt.user_id): str(elt.id)
            for elt in apis.TeamMembersApi(nt_client).get_team_members()
        }
        return {elt[0]: nt_members.get(elt[1]) for elt in pairs if elt[1] in nt_members}
    return {}

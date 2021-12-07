"""Asana -> Nozbe Teams importer"""

from typing import Optional

import asana
from asana.error import AsanaError
from dateutil.parser import isoparse

import openapi_client as nt
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException

SPEC = {
    "code": "asana",  # codename / ID of importer
    "name": "Asana",  # name of application
    "url": "https://developers.asana.com/docs/asana",  # link to documentation / specs / API
}

FAKE_ID16 = 16 * "a"
COLOR_MAP = {
    "light-green": "green",
    "dark-green": "darkgreen",
    "light-red": "red",
    "dark-red": "red",
    "light-orange": "orange",
    "dark-orange": "orange",
    "light-teal": "teal",
    "dark-teal": "teal",
    "light-purple": "purple",
    "dark-purple": "deeppurple",
    "light-pink": "lightpink",
    "dark-pink": "pink",
    "light-blue": "lightblue",
    "dark-brown": "brown",
    "light-warm-gray": "stone",
}


# main method called by Nozbe Teams app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Optional[str]:
    """Perform import from Asana to Nozbe Teams"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not auth_token:
        return "Missing 'auth_token'"

    nt_client = nt.ApiClient(configuration=nt.Configuration(
        host="https://api4.nozbe.com/v1/api",
        api_key={"ApiKeyAuth": nt_auth_token},
        access_token=nt_auth_token,
    ))
    asana_client = asana.Client.access_token(auth_token)
    try:
        _import_data(nt_client, asana_client, team_id)
    except (AsanaError, OpenApiException) as exc:
        return str(exc)


def _import_data(nt_client: nt.ApiClient, asana_client: asana.Client, team_id: str):
    """Import everything from Asana to Nozbe Teams"""
    nt_api_tags = apis.TagsApi(nt_client)
    nt_api_projects = apis.ProjectsApi(nt_client)
    nt_api_sections = apis.ProjectSectionsApi(nt_client)

    for workspace in asana_client.workspaces.find_all(full_payload=True):

        # import tags
        map_tag_id = {}
        for tag in asana_client.tags.find_by_workspace(workspace["gid"]):
            tag_full = asana_client.tags.find_by_id(tag["gid"])
            nt_tag = nt_api_tags.post_tag(
                models.Tag(
                    models.Id16ReadOnly(FAKE_ID16),
                    models.Name(tag_full.get("name")),
                    team_id=models.Id16Nullable(team_id),
                    color=_map_color(tag_full.get("color")),
                )
            )
            if nt_tag:
                map_tag_id[tag["gid"]] = str(nt_tag.get("id"))

        # import projects
        for project in asana_client.projects.find_by_workspace(workspace["gid"]):
            project_full = asana_client.projects.find_by_id(project["gid"])
            nt_project = nt_api_projects.post_project(
                models.Project(
                    models.Id16ReadOnly(FAKE_ID16),
                    models.NameAllowEmpty(project_full.get("name")),
                    models.Id16(team_id),
                    models.Id16ReadOnly(FAKE_ID16),
                    models.TimestampReadOnly(1),
                    models.TimestampReadOnly(1),
                    ended_at=models.TimestampNullable(1) if project_full.get("archived") else None,
                    color=_map_color(project_full.get("color")),
                    is_open=True,  # TODO set is_open based on 'public' and 'members' properties
                )
            )
            if not nt_project:
                continue
            nt_project_id = str(nt_project.get("id"))

            # import project sections
            map_section_id = {}
            for section in asana_client.sections.find_by_project(project["gid"]):
                section_full = asana_client.sections.find_by_id(section["gid"])
                nt_section = nt_api_sections.post_project_section(
                    models.ProjectSection(
                        models.Id16ReadOnly(FAKE_ID16),
                        models.Id16(nt_project_id),
                        models.Name(section_full.get("name")),
                        models.TimestampReadOnly(1),
                        archived_at=
                        models.TimestampNullable(1) if section_full.get("archived") else None,
                    )
                )
                if nt_section:
                    map_section_id[section["gid"]] = str(nt_section.get("id"))

            # import project tasks
            _import_tasks(
                nt_client,
                asana_client,
                asana_client.tasks.find_by_project(project["gid"]),
                nt_project_id,
                map_section_id,
                map_tag_id,
            )

        # import loose tasks to Single Tasks project
        me = asana_client.users.me()
        _import_tasks(
            nt_client,
            asana_client,
            asana_client.tasks.find_all({"workspace": workspace["gid"], "assignee": me["gid"]}),
            _get_single_tasks_project_id(nt_client, team_id),
            {},
            map_tag_id,
        )


def _import_tasks(
    nt_client: nt.ApiClient,
    asana_client: asana.Client,
    asana_tasks: list,
    nt_project_id: str,
    map_section_id: dict,
    map_tag_id: dict,
):
    """Import task from Asana to Nozbe Teams"""
    nt_api_tasks = apis.TasksApi(nt_client)
    nt_api_tag_assignments = apis.TagAssignmentsApi(nt_client)
    nt_api_comments = apis.CommentsApi(nt_client)
    for task in asana_tasks:
        task_full = asana_client.tasks.find_by_id(task["gid"])
        nt_task = nt_api_tasks.post_task(
            models.Task(
                models.Id16ReadOnly(FAKE_ID16),
                models.Name(task_full.get("name")),
                models.ProjectId(nt_project_id),
                models.Id16ReadOnly(FAKE_ID16),
                models.TimestampReadOnly(1),
                models.TimestampReadOnly(1),
                project_section_id=_map_section_id(task_full, map_section_id),
                due_at=_parse_timestamp(task_full.get("due_at")),
                ended_at=_parse_timestamp(task_full.get("completed_at")),
            )
        )
        if not nt_task:
            continue
        nt_task_id = str(nt_task.get("id"))

        # import tag_assignments
        for tag in task_full.get("tags") or []:
            nt_api_tag_assignments.post_tag_assignment(
                models.TagAssignment(
                    models.Id16ReadOnly(FAKE_ID16),
                    models.Id16(map_tag_id.get(tag["gid"])),
                    models.Id16(nt_task_id),
                )
            )

        # import comments
        for story in asana_client.stories.find_by_task(task["gid"]):
            if story.get("type") == "comment":
                nt_api_comments.post_comment(
                    models.Comment(
                        models.Id16ReadOnly(FAKE_ID16),
                        story.get("text"),
                        models.Id16(nt_task_id),
                        models.Id16ReadOnly(FAKE_ID16),
                        models.TimestampReadOnly(1),
                    )
                )

        # TODO import attachments
        # for attachment in asana_client.attachments.find_by_task(task["gid"]):
        #     pass


def _get_single_tasks_project_id(nt_client: nt.ApiClient, team_id: str) -> Optional[str]:
    """Returns NT Single Tasks's project ID"""
    params = {
        "header": {"Accept": "application/json"},
        "query": [("team_id", team_id), ("is_single_actions", True)]
    }
    settings = apis.ProjectsApi(nt_client).get_projects_endpoint.settings
    st_projects = nt_client.call_api(
        settings['endpoint_path'],
        settings['http_method'],
        None,
        params["query"],
        params['header'],
        response_type=settings['response_type'],
        auth_settings=settings['auth'],
        _check_type=True,
        _return_http_data_only=True,
        _preload_content=True,
    )
    return str(st_projects[0].get("id")) if st_projects and st_projects[0] else None


def _parse_timestamp(asana_timestamp: Optional[str]) -> Optional[models.TimestampNullable]:
    """Parses Asana timestamp into NT timestamp format"""
    if not asana_timestamp:
        return None
    return models.TimestampNullable(int(isoparse(asana_timestamp).timestamp() * 1000))


def _map_color(asana_color: Optional[str]) -> Optional[models.Color]:
    """Maps Asana color onto Nozbe Teams color"""
    if not asana_color:
        return None
    return models.Color(COLOR_MAP.get(asana_color)) if asana_color in COLOR_MAP else None


def _map_section_id(asana_task: dict, map_section_id: dict) -> models.Id16Nullable:
    """Maps Asana task's section GID onto NT section ID"""
    if not asana_task or not asana_task.get("memberships"):
        return None
    asana_section = asana_task.get("memberships")[0].get("section")
    return models.Id16Nullable(asana_section and map_section_id.get(asana_section.get("gid")))

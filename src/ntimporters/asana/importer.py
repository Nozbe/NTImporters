"""Asana -> Nozbe importer"""

import functools
from typing import Optional

import openapi_client as nt
from ntimporters.utils import (
    API_HOST,
    add_to_project_group,
    check_limits,
    current_nt_member,
    exists,
    get_imported_entities,
    get_single_tasks_project_id,
    id16,
    match_nt_users,
    nt_members_by_email,
    nt_open_projects_len,
    parse_timestamp,
    post_tag,
    set_unassigned_tag,
    trim,
)
from openapi_client import models
from openapi_client import api as apis
from openapi_client.exceptions import OpenApiException

import asana

SPEC = {
    "code": "asana",  # codename / ID of importer
    "name": "Asana",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#asana",  # link to documentation / specs / API
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}

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

IMPORT_NAME = "Imported from Asana"


# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Optional[Exception]:
    """Perform import from Asana to Nozbe"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not auth_token:
        return "Missing 'auth_token'"
    try:
        nt_client = nt.ApiClient(
            configuration=nt.Configuration(
                host=API_HOST,
                api_key={"ApiKeyAuth": nt_auth_token},
                access_token=nt_auth_token,
                username=nt_auth_token.split("_")[0],
            )
        )
        conf = asana.Configuration()
        conf.access_token = auth_token
        asana_client = asana.ApiClient(conf)
        _import_data(nt_client, asana_client, team_id, nt_auth_token)
    except Exception as exc:
        return exc
    return None


def _asana_projects_len(asana_client: asana.ApiClient) -> int:
    """Get number of asana projects"""
    total = 0
    for workspace in asana.WorkspacesApi(asana_client).get_workspaces({}):
        total += len(
            list(asana.ProjectsApi(asana_client).get_projects_for_workspace(workspace["gid"], {}))
        )

    return total


def _import_data(
    nt_client: nt.ApiClient, asana_client: asana.ApiClient, team_id: str, nt_auth_token: str
):
    """Import everything from Asana to Nozbe"""
    nt_api_projects = apis.ProjectsApi(nt_client)
    nt_api_sections = apis.ProjectSectionsApi(nt_client)
    nt_member_id = current_nt_member(nt_client)

    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "projects_open",
        _asana_projects_len(asana_client) + nt_open_projects_len(nt_client, team_id),
    )
    imported = get_imported_entities(nt_client, team_id, IMPORT_NAME)
    for workspace in asana.WorkspacesApi(asana_client).get_workspaces({}):
        # import tags
        map_tag_id = {}
        tags_api = asana.TagsApi(asana_client)
        for tag in tags_api.get_tags_for_workspace(workspace["gid"], {}):
            tag_full = tags_api.get_tag(tag["gid"], {})
            tag_name = tag_full.get("name", "")
            nt_tag = exists("tags", tag_name, imported)
            if nt_tag_id := nt_tag.get("id") or post_tag(
                nt_client, tag_name, _map_color(tag_full.get("color"))
            ):
                map_tag_id[tag["gid"]] = str(nt_tag_id)

        # import projects
        projects_api = asana.ProjectsApi(asana_client)
        for project in projects_api.get_projects_for_workspace(workspace["gid"], {}):
            project_full = projects_api.get_project(project["gid"], {})
            nt_project = exists(
                "projects", project_name := trim(project_full.get("name", "")), imported
            ) or nt_api_projects.post_project(
                models.Project(
                    name=project_name,
                    team_id=team_id,
                    author_id=id16(),
                    created_at=1,
                    last_event_at=1,
                    ended_at=1 if project_full.get("archived") else None,
                    color=_map_color(project_full.get("color")),
                    is_open=True,  # TODO set is_open based on 'public' and 'members' properties
                    is_template=False,
                    sidebar_position=1.0,
                )
            )
            if not nt_project:
                continue
            nt_project_id = str(nt_project.get("id"))
            add_to_project_group(nt_client, team_id, nt_project_id, IMPORT_NAME)

            # import project sections
            map_section_id = {}
            sections_api = asana.SectionsApi(asana_client)
            for position, section in enumerate(
                sections_api.get_sections_for_project(project["gid"], {})
            ):
                section_full = sections_api.get_section(section["gid"], {})
                if section_full.get("name") == "Untitled section":
                    continue
                try:
                    nt_section = exists(
                        "project_sections",
                        name := trim(section_full.get("name", "")),
                        imported,
                    ) or nt_api_sections.post_project_section(
                        models.ProjectSection(
                            id=id16(),
                            project_id=nt_project_id,
                            name=name,
                            created_at=1,
                            archived_at=1 if section_full.get("archived") else None,
                            position=float(position),
                        )
                    )
                    if nt_section:
                        map_section_id[section["gid"]] = str(nt_section.get("id"))
                except OpenApiException as f:
                    print(f)
                    pass

            # import project tasks
            _import_tasks(
                nt_client,
                asana_client,
                asana.TasksApi(asana_client).get_tasks_for_project(project["gid"], {}),
                nt_project_id,
                map_section_id,
                map_tag_id,
                nt_member_id,
                imported=imported,
            )

        # import loose tasks to Single Tasks project
        me = asana.UsersApi(asana_client).get_user("me", {})
        _import_tasks(
            nt_client,
            asana_client,
            asana.TasksApi(asana_client).get_tasks(
                {"workspace": workspace["gid"], "assignee": me["gid"]}
            ),
            get_single_tasks_project_id(nt_client, team_id),
            {},
            map_tag_id,
            nt_member_id,
            is_sap=True,
            imported=imported,
        )


@functools.cache
def _get_asana_email_by_gid(asana_client, gid):
    if user := asana.UsersApi(asana_client).get_user(gid, {"opt_fields": "email"}):
        return user.get("email")
    return None


def _import_tasks(
    nt_client: nt.ApiClient,
    asana_client: asana.ApiClient,
    asana_tasks: list,
    nt_project_id: str,
    map_section_id: dict,
    map_tag_id: dict,
    nt_member_id: str,
    is_sap: bool = False,
    imported=None,
):
    """Import task from Asana to Nozbe"""
    nt_api_tasks = apis.TasksApi(nt_client)
    nt_api_tag_assignments = apis.TagAssignmentsApi(nt_client)
    nt_api_comments = apis.CommentsApi(nt_client)
    _, nt_member_id = nt_members_by_email(nt_client)
    user_matches = match_nt_users(
        nt_client, [elt.get("email") for elt in asana_users(asana_client)]
    )

    def _get_responsible_id(assignee: dict):
        """Get Nozbe author_id given asana's user"""
        if (
            assignee
            and (gid := assignee.get("gid"))
            and (email := _get_asana_email_by_gid(asana_client, gid))
        ):
            return user_matches.get(email.lower())
        return None

    for task in asana_tasks:
        task_full = asana.TasksApi(asana_client).get_task(task["gid"], {})
        due_at = parse_timestamp(task_full.get("due_at")) or parse_timestamp(
            task_full.get("due_on")
        )
        responsible_id, should_set_tag = nt_member_id, False
        if found_responsible := _get_responsible_id(task_full.get("assignee")):
            responsible_id = found_responsible
        elif due_at:
            should_set_tag = True
        if is_sap and responsible_id != nt_member_id:
            responsible_id = nt_member_id

        if is_sap and task_full.get("projects"):
            # skip tasks from other projects
            continue

        nt_task = exists(
            "tasks", name := trim(task_full.get("name", "")), imported
        ) or nt_api_tasks.post_task(
            models.Task(
                name=name,
                missed_repeats=0,
                is_followed=False,
                is_abandoned=False,
                project_id=nt_project_id,
                author_id=id16(),
                created_at=1,
                last_activity_at=1,
                project_section_id=_map_section_id(task_full, map_section_id),
                due_at=due_at,
                responsible_id=responsible_id,
                is_all_day=not task_full.get("due_at"),
                ended_at=parse_timestamp(task_full.get("completed_at")),
            )
        )
        if not nt_task:
            continue
        nt_task_id = str(nt_task.get("id"))
        if should_set_tag and not is_sap:
            set_unassigned_tag(nt_client, nt_task_id)

        # import tag_assignments
        for tag in task_full.get("tags") or []:
            try:
                nt_api_tag_assignments.post_tag_assignment(
                    models.TagAssignment(
                        id=id16(),
                        tag_id=map_tag_id.get(tag["gid"]),
                        task_id=nt_task_id,
                    )
                )
            except Exception:
                pass

        # import comments

        def _post_comment(body, task_id):
            nt_api_comments.post_comment(
                models.Comment(
                    body=body or "…",
                    is_team=False,
                    is_pinned=False,
                    extra="",
                    task_id=task_id,
                    author_id=id16(),
                    created_at=1,
                )
            )

        if (task_description := task_full.get("notes", "")) and not exists(
            "comments", task_description, imported
        ):
            _post_comment(task_description, nt_task_id)
        checklist = []
        for item in asana.TasksApi(asana_client).get_subtasks_for_task(
            task["gid"], {"opt_fields": "name,completed"}
        ):
            checked = "- [ ]" if not item.get("completed") else "- [x]"
            checklist.append(f"{checked} {item.get('name')}")

        if checklist:
            body = "\n".join(checklist)
            if not exists("comments", body, imported):
                _post_comment(body, nt_task_id)

        for story in asana.StoriesApi(asana_client).get_stories_for_task(task["gid"], {}):
            if (body := story.get("type")) == "comment" and not exists("comments", body, imported):
                _post_comment(story.get("text"), nt_task_id)

        # TODO import attachments
        # for attachment in asana_client.attachments.find_by_task(task["gid"]):
        #     pass


def _map_color(asana_color: Optional[str]) -> Optional[models.Color]:
    """Maps Asana color onto Nozbe color"""
    if not asana_color:
        return None
    return models.Color(COLOR_MAP.get(asana_color)) if asana_color in COLOR_MAP else None


def _map_section_id(asana_task: dict, map_section_id: dict):
    """Maps Asana task's section GID onto NT section ID"""
    if not asana_task or not asana_task.get("memberships"):
        return None
    asana_section = asana_task.get("memberships")[0].get("section")
    return asana_section and map_section_id.get(asana_section.get("gid"))


def asana_users(asana_client):
    """Get asana users from all workspaces"""
    users = []

    for workspace in asana.WorkspacesApi(asana_client).get_workspaces({}):
        users += list(
            asana.UsersApi(asana_client).get_users_for_workspace(
                workspace.get("gid"), {"opt_fields": "email"}
            )
        )
    # gid,email
    return users

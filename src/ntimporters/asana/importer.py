"""Asana -> Nozbe importer"""
import functools
from typing import Optional

import openapi_client as nt
from ntimporters.utils import (
    API_HOST,
    add_to_project_group,
    current_nt_member,
    get_single_tasks_project_id,
    id16,
    nt_members_by_email,
    parse_timestamp,
    post_tag,
    set_unassigned_tag,
    strip_readonly,
    trim,
)
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException

import asana
from asana.error import AsanaError

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


# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Optional[Exception]:
    """Perform import from Asana to Nozbe"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not auth_token:
        return "Missing 'auth_token'"

    nt_client = nt.ApiClient(
        configuration=nt.Configuration(
            host=API_HOST,
            api_key={"ApiKeyAuth": nt_auth_token},
            access_token=nt_auth_token,
        )
    )
    asana_client = asana.Client.access_token(auth_token)
    try:
        _import_data(nt_client, asana_client, team_id)
    except (AsanaError, OpenApiException) as exc:
        return exc


def _import_data(nt_client: nt.ApiClient, asana_client: asana.Client, team_id: str):
    """Import everything from Asana to Nozbe"""
    nt_api_projects = apis.ProjectsApi(nt_client)
    nt_api_sections = apis.ProjectSectionsApi(nt_client)
    nt_member_id = current_nt_member(nt_client)

    for workspace in asana_client.workspaces.find_all(full_payload=True):
        # import tags
        map_tag_id = {}
        for tag in asana_client.tags.find_by_workspace(workspace["gid"]):
            tag_full = asana_client.tags.find_by_id(tag["gid"])
            nt_tag_id = post_tag(
                nt_client, tag_full.get("name", ""), _map_color(tag_full.get("color"))
            )
            if nt_tag_id:
                map_tag_id[tag["gid"]] = str(nt_tag_id)

        # import projects
        for project in asana_client.projects.find_by_workspace(workspace["gid"]):
            project_full = asana_client.projects.find_by_id(project["gid"])
            nt_project = nt_api_projects.post_project(
                strip_readonly(
                    models.Project(
                        name=models.NameAllowEmpty(trim(project_full.get("name", ""))),
                        team_id=models.Id16(team_id),
                        author_id=models.Id16ReadOnly(id16()),
                        created_at=models.TimestampReadOnly(1),
                        last_event_at=models.TimestampReadOnly(1),
                        ended_at=models.TimestampNullable(
                            1 if project_full.get("archived") else None
                        ),
                        color=_map_color(project_full.get("color")),
                        is_open=True,  # TODO set is_open based on 'public' and 'members' properties
                        sidebar_position=1.0,
                    )
                )
            )
            if not nt_project:
                continue
            nt_project_id = str(nt_project.get("id"))
            add_to_project_group(nt_client, team_id, nt_project_id, "Imported from Asana")

            # import project sections
            map_section_id = {}
            for position, section in enumerate(
                asana_client.sections.find_by_project(project["gid"])
            ):
                section_full = asana_client.sections.find_by_id(section["gid"])
                if section_full.get("name") == "Untitled section":
                    continue
                nt_section = nt_api_sections.post_project_section(
                    strip_readonly(
                        models.ProjectSection(
                            id=models.Id16ReadOnly(id16()),
                            project_id=models.Id16(nt_project_id),
                            name=models.Name(trim(section_full.get("name", ""))),
                            created_at=models.TimestampReadOnly(1),
                            archived_at=models.TimestampNullable(1)
                            if section_full.get("archived")
                            else None,
                            position=float(position),
                        )
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
                nt_member_id,
            )

        # import loose tasks to Single Tasks project
        me = asana_client.users.me()
        _import_tasks(
            nt_client,
            asana_client,
            asana_client.tasks.find_all({"workspace": workspace["gid"], "assignee": me["gid"]}),
            get_single_tasks_project_id(nt_client, team_id),
            {},
            map_tag_id,
            nt_member_id,
        )


@functools.cache
def _get_asana_email_by_gid(asana_client, gid):
    if user := asana_client.users.get_user(gid, opt_fields="email"):
        return user.get("email")
    return None


def _import_tasks(
    nt_client: nt.ApiClient,
    asana_client: asana.Client,
    asana_tasks: list,
    nt_project_id: str,
    map_section_id: dict,
    map_tag_id: dict,
    nt_member_id: str,
):
    """Import task from Asana to Nozbe"""
    nt_api_tasks = apis.TasksApi(nt_client)
    nt_api_tag_assignments = apis.TagAssignmentsApi(nt_client)
    nt_api_comments = apis.CommentsApi(nt_client)
    nt_members, nt_member_id = nt_members_by_email(nt_client)

    def _get_responsible_id(assignee: dict):
        """Get Nozbe author_id given asana's user"""
        if assignee and (gid := assignee.get("gid")):
            if responsible_id := nt_members.get(_get_asana_email_by_gid(asana_client, gid)):
                return responsible_id
        return None

    for task in asana_tasks:
        task_full = asana_client.tasks.find_by_id(task["gid"])

        due_at = parse_timestamp(task_full.get("due_at")) or parse_timestamp(
            task_full.get("due_on")
        )
        responsible_id, should_set_tag = nt_member_id, False
        if found_responsible := _get_responsible_id(task_full.get("assignee")):
            responsible_id = found_responsible
        elif due_at:
            should_set_tag = True

        nt_task = nt_api_tasks.post_task(
            strip_readonly(
                models.Task(
                    name=models.Name(trim(task_full.get("name", ""))),
                    project_id=models.ProjectId(nt_project_id),
                    author_id=models.Id16ReadOnly(id16()),
                    created_at=models.TimestampReadOnly(1),
                    last_activity_at=models.TimestampReadOnly(1),
                    project_section_id=_map_section_id(task_full, map_section_id),
                    due_at=due_at,
                    responsible_id=responsible_id,
                    is_all_day=not task_full.get("due_at"),
                    ended_at=parse_timestamp(task_full.get("completed_at")),
                )
            )
        )
        if not nt_task:
            continue
        nt_task_id = str(nt_task.get("id"))
        if should_set_tag:
            set_unassigned_tag(nt_client, nt_task_id)

        # import tag_assignments
        for tag in task_full.get("tags") or []:
            nt_api_tag_assignments.post_tag_assignment(
                strip_readonly(
                    models.TagAssignment(
                        id=models.Id16(id16()),
                        tag_id=models.Id16(map_tag_id.get(tag["gid"])),
                        task_id=models.Id16(nt_task_id),
                    )
                )
            )

        # import comments

        def _post_comment(body, task_id):
            nt_api_comments.post_comment(
                strip_readonly(
                    models.Comment(
                        body=body,
                        task_id=models.Id16(task_id),
                        author_id=models.Id16ReadOnly(id16()),
                        created_at=models.TimestampReadOnly(1),
                    )
                )
            )

        if task_description := task_full.get("notes", ""):
            _post_comment(task_description, nt_task_id)
        checklist = []
        for item in asana_client.tasks.get_subtasks_for_task(
            task["gid"], opt_fields="name,completed"
        ):
            checked = "- [ ]" if not item.get("completed") else "- [x]"
            checklist.append(f"{checked} {item.get('name')}")

        if checklist:
            _post_comment("\n".join(checklist), nt_task_id)

        for story in asana_client.stories.find_by_task(task["gid"]):
            if story.get("type") == "comment":
                _post_comment(story.get("text"), nt_task_id)

        # TODO import attachments
        # for attachment in asana_client.attachments.find_by_task(task["gid"]):
        #     pass


def _map_color(asana_color: Optional[str]) -> Optional[models.Color]:
    """Maps Asana color onto Nozbe color"""
    if not asana_color:
        return None
    return models.Color(COLOR_MAP.get(asana_color)) if asana_color in COLOR_MAP else None


def _map_section_id(asana_task: dict, map_section_id: dict) -> models.Id16Nullable:
    """Maps Asana task's section GID onto NT section ID"""
    if not asana_task or not asana_task.get("memberships"):
        return None
    asana_section = asana_task.get("memberships")[0].get("section")
    return models.Id16Nullable(asana_section and map_section_id.get(asana_section.get("gid")))

"""Asana -> Nozbe importer"""

import asana

from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.utils import dig, parse_timestamp
from openapi_client import models

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
# Asana Ambassadors workspace
SKIPPED_WORKSPACES = {"1162055570357937"}

IMPORT_NAME = "Imported from Asana"
# everything _import_tasks / _import_comments read, so list endpoints replace per-task get_task
TASK_FIELDS = (
    "name,notes,due_on,due_at,completed_at,assignee,memberships.section,projects,tags,num_subtasks"
)


# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Exception | str | None:
    """Perform import from Asana to Nozbe"""

    def _import():
        conf = asana.Configuration()
        conf.access_token = auth_token
        _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME, with_single_tasks=True),
            asana.ApiClient(conf),
        )

    return run_safely(_import, nt_auth_token=nt_auth_token, auth_token=auth_token)


def _import_data(nz: NozbeImport, asana_client: asana.ApiClient):
    """Import everything from Asana to Nozbe"""
    workspaces = get_workspaces(asana_client)
    projects_api = asana.ProjectsApi(asana_client)
    sections_api = asana.SectionsApi(asana_client)
    tags_api = asana.TagsApi(asana_client)
    tasks_api = asana.TasksApi(asana_client)
    projects = {
        elt["gid"]: list(
            projects_api.get_projects_for_workspace(
                elt["gid"], {"opt_fields": "name,color,archived"}
            )
        )
        for elt in workspaces
    }
    nz.check_open_projects(
        elt.get("name") for elts in projects.values() for elt in elts if not elt.get("archived")
    )
    responsible = nz.members(
        {elt.get("gid"): elt.get("email") for elt in asana_users(asana_client, workspaces)}
    )
    me = asana.UsersApi(asana_client).get_user("me", {})
    for workspace in workspaces:
        tags = {
            tag["gid"]: tag
            for tag in tags_api.get_tags_for_workspace(
                workspace["gid"], {"opt_fields": "name,color"}
            )
        }
        nt_tags = nz.tags(
            (tag.get("name", ""), COLOR_MAP.get(tag.get("color"))) for tag in tags.values()
        )
        tag_ids = {gid: nt_tags.get(tag.get("name", "")) for gid, tag in tags.items()}

        for project in projects.get(workspace["gid"]):
            if not (
                nt_project_id := nz.project(
                    project.get("name", ""),
                    color=_map_color(project.get("color")),
                    ended=bool(project.get("archived")),
                )
            ):
                continue
            section_ids = {}
            for position, section in enumerate(
                sections_api.get_sections_for_project(project["gid"], {"opt_fields": "name"})
            ):
                # Asana sections have no archived state
                if section.get("name") == "Untitled section":
                    continue
                if section_id := nz.section(nt_project_id, section.get("name", ""), position):
                    section_ids[section["gid"]] = section_id
            _import_tasks(
                nz,
                asana_client,
                tasks_api.get_tasks_for_project(project["gid"], {"opt_fields": TASK_FIELDS}),
                nt_project_id,
                section_ids,
                tag_ids,
                responsible,
            )

        # loose tasks assigned to me -> Single Tasks
        _import_tasks(
            nz,
            asana_client,
            tasks_api.get_tasks(
                {"workspace": workspace["gid"], "assignee": me["gid"], "opt_fields": TASK_FIELDS}
            ),
            nz.single_tasks_id,
            {},
            tag_ids,
            responsible,
            loose=True,
        )


def _import_tasks(
    nz: NozbeImport,
    asana_client: asana.ApiClient,
    asana_tasks,
    nt_project_id: str,
    section_ids: dict,
    tag_ids: dict,
    responsible: dict,
    loose: bool = False,
):
    """Import tasks (records with TASK_FIELDS); loose: only those outside any project"""
    for task in asana_tasks:
        if loose and task.get("projects"):
            continue
        nt_task_id, is_new = nz.task(
            nt_project_id,
            task.get("name", ""),
            section_id=section_ids.get(dig(task, "memberships.0.section.gid")),
            due_at=parse_timestamp(task.get("due_at") or task.get("due_on")),
            is_all_day=not task.get("due_at"),
            responsible_id=responsible.get(dig(task, "assignee.gid")),
            assigned=bool(dig(task, "assignee.gid")),
            ended_at=parse_timestamp(task.get("completed_at")),
        )
        if not nt_task_id:
            continue
        nz.assign_tags(
            nt_task_id, (tag_ids.get(tag.get("gid")) for tag in task.get("tags") or []), is_new
        )
        _import_comments(nz, asana_client, nt_task_id, task)


def _import_comments(nz: NozbeImport, asana_client, nt_task_id: str, task: dict):
    """Notes, subtasks as checklist, comment stories, attachments"""
    gid = task.get("gid")
    if notes := task.get("notes"):
        nz.comment(nt_task_id, notes)
    if task.get("num_subtasks") and (
        checklist := "\n".join(
            f"- [{'x' if item.get('completed') else ' '}] {item.get('name')}"
            for item in asana.TasksApi(asana_client).get_subtasks_for_task(
                gid, {"opt_fields": "name,completed"}
            )
        )
    ):
        nz.comment(nt_task_id, checklist)
    for story in asana.StoriesApi(asana_client).get_stories_for_task(
        gid, {"opt_fields": "type,text"}
    ):
        if story.get("type") == "comment":
            nz.comment(nt_task_id, story.get("text"))
    for attachment in asana.AttachmentsApi(asana_client).get_attachments_for_object(
        gid, {"opt_fields": "name,host,download_url,view_url"}
    ):
        is_file = attachment.get("host") == "asana" and bool(attachment.get("download_url"))
        nz.attachment(
            nt_task_id,
            attachment.get("name") or "attachment",
            attachment.get("download_url" if is_file else "view_url"),
            is_file,
        )


def _map_color(asana_color: str | None) -> models.Color | None:
    """Maps Asana color onto Nozbe color"""
    return models.Color(color) if (color := COLOR_MAP.get(asana_color or "")) else None


def asana_users(asana_client, workspaces: list) -> list[dict]:
    """Asana users (gid, email) with email, from all workspaces"""
    return [
        user
        for workspace in workspaces
        for user in asana.UsersApi(asana_client).get_users(
            {"workspace": workspace["gid"], "opt_fields": "gid,email"}
        )
        if user.get("email") is not None
    ]


def get_workspaces(asana_client) -> list:
    """Accessible asana workspaces"""
    return [
        workspace
        for workspace in asana.WorkspacesApi(asana_client).get_workspaces({})
        if workspace["gid"] not in SKIPPED_WORKSPACES
    ]

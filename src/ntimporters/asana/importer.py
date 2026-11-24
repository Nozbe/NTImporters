"""Asana -> Nozbe importer"""

from datetime import date, datetime

import asana
from dateutil.parser import isoparse
from more_itertools import first

from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.utils import checklist, dig, parse_timestamp
from openapi_client import models

SPEC = {
    "code": "asana",
    "name": "Asana",
    "url": "https://nozbe.help/advancedfeatures/importers/#asana",
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
# all _import_tasks / _import_comments read: no per-task get_task
TASK_FIELDS = (
    "name,notes,due_on,due_at,completed_at,assignee,memberships.project,memberships.section,"
    "projects,tags,num_subtasks"
)


# Nozbe app entry point
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Exception | str | None:
    """Asana -> Nozbe"""

    def _import():
        conf = asana.Configuration()
        conf.access_token = auth_token
        _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME, with_single_tasks=True),
            asana.ApiClient(conf),
        )

    return run_safely(_import, nt_auth_token=nt_auth_token, auth_token=auth_token)


def _import_data(nz: NozbeImport, asana_client: asana.ApiClient):
    """per workspace: tags, projects, sections, tasks; my loose tasks -> Single Tasks"""
    workspaces = get_workspaces(asana_client)
    projects_api = asana.ProjectsApi(asana_client)
    sections_api = asana.SectionsApi(asana_client)
    tags_api = asana.TagsApi(asana_client)
    tasks_api = asana.TasksApi(asana_client)
    projects = {
        elt.get("gid"): list(
            projects_api.get_projects_for_workspace(
                elt.get("gid"), {"opt_fields": "name,color,archived"}
            )
        )
        for elt in workspaces
    }
    nz.check_open_projects(
        elt.get("name") for elts in projects.values() for elt in elts if not elt.get("archived")
    )
    me = asana.UsersApi(asana_client).get_user("me", {})
    responsible = nz.members(
        {elt.get("gid"): elt.get("email") for elt in asana_users(asana_client, workspaces)},
        owner=me.get("gid"),
    )
    for workspace in workspaces:
        tags = {
            tag.get("gid"): tag
            for tag in tags_api.get_tags_for_workspace(
                workspace.get("gid"), {"opt_fields": "name,color"}
            )
        }
        nt_tags = nz.tags(
            (tag.get("name", ""), COLOR_MAP.get(tag.get("color"))) for tag in tags.values()
        )
        tag_ids = {gid: nt_tags.get(tag.get("name", "")) for gid, tag in tags.items()}

        for project in projects.get(workspace.get("gid")):
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
                sections_api.get_sections_for_project(project.get("gid"), {"opt_fields": "name"})
            ):
                # no archived state in Asana
                if section.get("name") == "Untitled section":
                    continue
                if section_id := nz.section(nt_project_id, section.get("name", ""), position):
                    section_ids[section.get("gid")] = section_id
            _import_tasks(
                nz,
                asana_client,
                tasks_api.get_tasks_for_project(project.get("gid"), {"opt_fields": TASK_FIELDS}),
                nt_project_id,
                section_ids,
                tag_ids,
                responsible,
                project_gid=project.get("gid"),
            )

        # loose tasks assigned to me -> Single Tasks
        _import_tasks(
            nz,
            asana_client,
            tasks_api.get_tasks(
                {
                    "workspace": workspace.get("gid"),
                    "assignee": me.get("gid"),
                    "opt_fields": TASK_FIELDS,
                }
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
    project_gid: str | None = None,
):
    """records with TASK_FIELDS; loose: skip project tasks; section: membership in project_gid"""
    for task in asana_tasks:
        if loose and task.get("projects"):
            continue
        section_gid = first(
            (
                dig(membership, "section.gid")
                for membership in task.get("memberships") or []
                if dig(membership, "project.gid") == project_gid
            ),
            None,
        )
        nt_task_id, is_new = nz.task(
            nt_project_id,
            task.get("name", ""),
            section_id=section_ids.get(section_gid),
            due=_due(task),
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


def _due(task: dict) -> date | datetime | None:
    """due_at datetime, else due_on date"""
    if due_at := task.get("due_at"):
        return isoparse(due_at)
    if due_on := task.get("due_on"):
        return isoparse(due_on).date()
    return None


def _import_comments(nz: NozbeImport, asana_client, nt_task_id: str, task: dict):
    """notes, subtasks as checklist, comment stories, attachments"""
    gid = task.get("gid")
    if notes := task.get("notes"):
        nz.comment(nt_task_id, notes)
    if task.get("num_subtasks") and (
        items := checklist(
            (item.get("name"), bool(item.get("completed")))
            for item in asana.TasksApi(asana_client).get_subtasks_for_task(
                gid, {"opt_fields": "name,completed"}
            )
        )
    ):
        nz.comment(nt_task_id, items)
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
    """None if unmapped"""
    return models.Color(color) if (color := COLOR_MAP.get(asana_color or "")) else None


def asana_users(asana_client, workspaces: list) -> list[dict]:
    """users (gid, email) having email, all workspaces"""
    return [
        user
        for workspace in workspaces
        for user in asana.UsersApi(asana_client).get_users(
            {"workspace": workspace.get("gid"), "opt_fields": "gid,email"}
        )
        if user.get("email") is not None
    ]


def get_workspaces(asana_client) -> list:
    """accessible, minus SKIPPED_WORKSPACES"""
    return [
        workspace
        for workspace in asana.WorkspacesApi(asana_client).get_workspaces({})
        if workspace.get("gid") not in SKIPPED_WORKSPACES
    ]

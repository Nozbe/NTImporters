"""Trello -> Nozbe importer"""
from typing import Optional

import openapi_client as nt
from dateutil.parser import isoparse
from ntimporters.trello.trello_api import TrelloClient
from ntimporters.utils import (
    API_HOST,
    add_to_project_group,
    check_limits,
    current_nt_member,
    exists,
    get_imported_entities,
    id16,
    map_color,
    match_nt_users,
    nt_open_projects_len,
    parse_timestamp,
    post_tag,
    set_unassigned_tag,
    strip_readonly,
    trim,
)
from openapi_client import apis, models
from openapi_client.exceptions import OpenApiException

SPEC = {
    "code": "trello",  # codename / ID of importer
    "name": "Trello",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/#trello",
    "input_fields": ("nt_auth_token", "auth_token", "app_key", "team_id"),
}
IMPORT_NAME = "Imported from Trello"

# main method called by Nozbe app
def run_import(
    nt_auth_token: str, auth_token: str, app_key: str, team_id: str
) -> Optional[Exception]:
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
                    host=API_HOST,
                    api_key={"ApiKeyAuth": nt_auth_token},
                )
            ),
            TrelloClient(app_key, auth_token),
            team_id,
            nt_auth_token,
        )

    except Exception as exc:
        return exc
    return None


def _import_data(nt_client: nt.ApiClient, trello_client, team_id: str, nt_auth_token: str):
    """Import everything from Trello to Nozbe"""
    projects_api = apis.ProjectsApi(nt_client)
    curr_member = current_nt_member(nt_client)
    imported = get_imported_entities(nt_client, team_id, IMPORT_NAME)

    def _import_project(project: dict, curr_member: str):
        """Import trello project"""
        project_model = models.Project(
            name=models.NameAllowEmpty(name := trim(project.get("name", ""))),
            is_template=False,
            team_id=models.Id16(team_id),
            author_id=models.Id16ReadOnly(id16()),
            created_at=models.TimestampReadOnly(1),
            last_event_at=models.TimestampReadOnly(1),
            color=map_color(project.get("backgroundTopColor")),
            description=str(project.get("desc") or ""),
            is_favorite=project.get("is_fav"),
            sidebar_position=1.0,
            is_open=True,
            extra="",
        )
        nt_project = (
            exists("projects", name, imported)
            or projects_api.post_project(strip_readonly(project_model))
            or {}
        )

        if not (nt_project_id := str(nt_project.get("id"))):
            return
        add_to_project_group(nt_client, team_id, nt_project_id, IMPORT_NAME)

        _import_project_sections(
            nt_client,
            trello_client,
            nt_project_id,
            project,
            curr_member,
            team_id,
            nt_auth_token,
            imported=imported,
        )

    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "projects_open",
        len(trello_projects := trello_client.projects()) + nt_open_projects_len(nt_client, team_id),
    )
    for project in trello_projects:
        try:
            _import_project(project, curr_member)
        except Exception as error:
            return error
    return None


# pylint: disable=too-many-arguments
def _import_project_sections(
    nt_client,
    trello_client,
    nt_project_id: str,
    project: dict,
    nt_member_id: str,
    team_id: str,
    nt_auth_token: str,
    imported=None,
):
    """Import trello lists as project sections"""
    nt_api_sections = apis.ProjectSectionsApi(nt_client)
    nt_api_tasks = apis.TasksApi(nt_client)

    # import project sections
    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "project_sections",
        len(trello_sections := trello_client.sections(project.get("id"))),
    )
    for j, section in enumerate(trello_sections):
        nt_section_id = None
        try:
            nt_section = exists("project_sections", name := trim(section.get("name", "")), imported)
            if nt_section := nt_section or nt_api_sections.post_project_section(
                strip_readonly(
                    models.ProjectSection(
                        models.Id16ReadOnly(id16()),
                        models.Id16(nt_project_id),
                        models.Name(name),
                        models.TimestampReadOnly(1),
                        archived_at=models.TimestampNullable(1) if section.get("closed") else None,
                        position=float(j),
                    )
                )
            ):
                nt_section_id = nt_section.id
        except OpenApiException as exc:
            pass

        trello_members = trello_client.members_emails() or {}
        nt_users = match_nt_users(nt_client, trello_members.values())

        def _get_responsible_id(task: dict):
            if members := task.get("idMembers"):
                for member_id in members:
                    if (
                        (email := trello_members.get(member_id))
                        and (responsible_id := nt_users.get(email))
                        and responsible_id != nt_member_id
                    ):
                        return responsible_id
            return None

        for i, task in enumerate(trello_client.tasks(section.get("id"))):
            responsible_id = _get_responsible_id(task) or nt_member_id if task.get("due") else None

            nt_task = exists("tasks", name := trim(task.get("name", "")), imported)
            if nt_task := nt_task or nt_api_tasks.post_task(
                strip_readonly(
                    models.Task(
                        name=models.Name(name),
                        project_id=models.ProjectId(nt_project_id),
                        author_id=models.Id16ReadOnly(id16()),
                        created_at=models.TimestampReadOnly(1),
                        last_activity_at=models.TimestampReadOnly(1),
                        project_section_id=models.Id16Nullable(str(nt_section_id)),
                        project_position=float(i),
                        due_at=parse_timestamp(task.get("due")),
                        responsible_id=responsible_id,
                        is_all_day=False,  # trello due at has to be specified with time
                        is_followed=False,
                        is_abandoned=False,
                        missed_repeats=0,
                        ended_at=None
                        if not task.get("dueComplete")
                        else parse_timestamp(task.get("due")),
                        # there is no ended_at time @ trello
                    )
                )
            ):
                if task.get("due") and not responsible_id:
                    set_unassigned_tag(nt_client, str(nt_task.id))
                _import_tags(
                    nt_client,
                    str(nt_task.id),
                    task,
                    _import_tags_per_project(
                        nt_client, trello_client, project, team_id, nt_auth_token
                    ),
                )
                _import_comments(nt_client, trello_client, str(nt_task.id), task, imported=imported)
                # TODO import attachments, reminders?


# pylint: enable=too-many-arguments


def _import_tags_per_project(
    nt_client, trello_client, project: dict, team_id: str, nt_auth_token: str
) -> dict:
    """Import trello tags and return name -> NT tag id mapping"""
    nt_api_tags = apis.TagsApi(nt_client)
    nt_tags = {
        str(elt.get("name")): str(elt.get("id")) for elt in nt_api_tags.get_tags(fields="id,name")
    }
    check_limits(
        nt_auth_token,
        team_id,
        nt_client,
        "tags",
        len(trello_tags := trello_client.tags(project.get("id"))) + len(nt_tags),
    )
    for tag in trello_tags:
        if (tag_name := (tag.get("name") or "Unnamed")) not in nt_tags and (
            nt_tag_id := post_tag(nt_client, tag_name, tag.get("color"))
        ):
            nt_tags[tag_name] = str(nt_tag_id)
    return nt_tags


def _import_tags(nt_client, nt_task_id: str, task: dict, tags_mapping):
    """Assign tags to task"""
    nt_api_tag_assignments = apis.TagAssignmentsApi(nt_client)
    assigned = []
    for tag in task.get("labels"):
        if nt_tag_id := tags_mapping.get(tag.get("name") or "Unnamed"):
            if nt_tag_id in assigned:
                continue
            try:
                nt_api_tag_assignments.post_tag_assignment(
                    strip_readonly(
                        models.TagAssignment(
                            id=models.Id16ReadOnly(id16()),
                            tag_id=models.Id16(nt_tag_id),
                            task_id=models.Id16(nt_task_id),
                        )
                    )
                )
                assigned.append(nt_tag_id)
            except Exception:
                pass


def _import_comments(nt_client, trello_client, nt_task_id: str, task, imported=None):
    """Import task-related comments"""
    tr_task_id = task.get("id")
    nt_api_comments = apis.CommentsApi(nt_client)
    comments = [{"text": task.get("desc")}] if task.get("desc") else []
    comments += sorted(
        trello_client.comments(tr_task_id), key=lambda elt: isoparse(elt.get("date")).timestamp()
    )
    for comment in comments:
        if not exists("comments", body := comment.get("text") or "…", imported):
            nt_api_comments.post_comment(
                strip_readonly(
                    models.Comment(
                        body=body,
                        task_id=models.Id16(nt_task_id),
                        author_id=models.Id16ReadOnly(id16()),
                        created_at=models.TimestampReadOnly(1),
                        is_team=False,
                        is_pinned=False,
                        extra="",
                    )
                )
            )


# def _import_members(nt_client, trello_client, team_id: str):
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
# nt_auth_token,
# team_id,
# nt_client,
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

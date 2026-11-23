"""Nozbe side of an import: dedup within the import group and shared write rules"""

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from functools import cached_property
from pathlib import Path

import requests
from more_itertools import first, unique_everseen

from ntimporters.utils import (
    ImportException,
    exists,
    fetch_all,
    get_group_id,
    get_imported_entities,
    id16,
    log,
    map_color,
    nt_api_client,
    subscribe_trial,
    trim,
)
from openapi_client import api, models
from openapi_client.exceptions import OpenApiException

type File = tuple[str, str, dict | None]  # (url, name, download headers)


def run_safely(import_data: Callable[[], object], **required) -> Exception | str | None:
    """None on success; else 'Missing ...' or the exception (Nozbe4Backend reports it)"""
    if missing := first((name for name, value in required.items() if not value), None):
        return f"Missing '{missing}'"
    try:
        import_data()
    except Exception as exc:
        return exc
    return None


class NozbeImport:
    """One import into a Nozbe team, deduplicated against the 'Imported from <app>' group.
    Team data read once per import, kept up to date with own writes."""

    def __init__(self, nt_auth_token: str, team_id: str, group_name: str, with_single_tasks=False):
        self.nt_auth_token, self.team_id, self.group_name = nt_auth_token, team_id, group_name
        self.client = nt_api_client(nt_auth_token)
        self._member_ids = {
            elt.get("user_id"): elt.get("id")
            for elt in fetch_all(self.client, "/team_members", team_id=team_id, fields="id,user_id")
        }
        self.author_id = self._member_ids.get(self.client.configuration.username) or id16()
        self.group_id = get_group_id(self.client, team_id, group_name)
        self.imported = get_imported_entities(
            self.client,
            self.group_id,
            self.author_id,
            self._team_projects,
            self.single_tasks_id if with_single_tasks else None,
        )
        self._tagged = {}  # tag id -> ids of tasks having it
        self._trial = False

    def _post(self, what: str, call: Callable[[], object]) -> str | None:
        """Id of record created by call; None (logged) if API or model refused it"""
        try:
            return call().id
        except OpenApiException, ValueError:
            log.warning("%s not imported", what, exc_info=True)
            return None

    @cached_property
    def _team_projects(self) -> list[dict]:
        return fetch_all(
            self.client,
            "/projects",
            team_id=self.team_id,
            fields="id,name,created_at,is_open,ended_at,is_template,is_single_actions",
        )

    @cached_property
    def single_tasks_id(self) -> str | None:
        """Team's Single Tasks project id"""
        return first(
            (elt.get("id") for elt in self._team_projects if elt.get("is_single_actions")), None
        )

    @cached_property
    def _limits(self) -> dict:
        team = api.TeamsApi(self.client).get_team_by_id(self.team_id)
        return json.loads(getattr(team, "limits", None) or "{}")

    def check_limit(self, name: str, count: int):
        """Raise ImportException if count exceeds team's limit (-1: unlimited) and no trial"""
        if self._trial or not count > (limit := self._limits.get(name, 0)) > -1:
            return
        if not subscribe_trial(self.nt_auth_token, self.team_id):
            raise ImportException(f"LIMIT {name} : {count} > {limit}")
        self._trial = True

    def check_open_projects(self, names: Iterable[str]):
        """Raise ImportException if open projects to create (names, less those imported before)
        exceed team's limit"""
        imported = self.imported.get("projects", {})
        count = sum(
            max(0, number - len(imported.get(name, ())))
            for name, number in Counter(map(trim, names)).items()
        )
        open_projects = sum(
            bool(elt.get("is_open"))
            and not any(elt.get(key) for key in ("ended_at", "is_template", "is_single_actions"))
            for elt in self._team_projects
        )
        self.check_limit("projects_open", count + open_projects)

    @cached_property
    def _team_emails(self) -> list[tuple[str, str]]:
        """(email or invitation email, member id) of team members"""
        return [
            (email, member_id)
            for elt in fetch_all(self.client, "/users", fields="id,email,invitation_email")
            if (email := elt.get("email") or elt.get("invitation_email"))
            and (member_id := self._member_ids.get(elt.get("id")))
        ]

    def members(self, emails: Mapping[str, str | None]) -> dict[str, str]:
        """3rd party id -> NT member id, matched by email (case-insensitive);
        NT email may be md5(user_id + email)"""
        exact = {email.lower(): member_id for email, member_id in self._team_emails}
        users = {member_id: user_id for user_id, member_id in self._member_ids.items()}

        def member(email: str) -> str | None:
            return exact.get(email) or first(
                (
                    member_id
                    for nt_email, member_id in self._team_emails
                    if nt_email == hashlib.md5((users.get(member_id) + email).encode()).hexdigest()  # nosec
                ),
                None,
            )

        return {
            src_id: member_id
            for src_id, email in emails.items()
            if email and (member_id := member(email.lower()))
        }

    def project(
        self,
        name: str,
        *,
        color: models.Color | None = None,
        description: str | None = None,
        is_favorite: bool = False,
        is_open: bool = True,
        ended: bool = False,
    ) -> str | None:
        """Id of project by name in import group; created and grouped if missing"""
        if project_id := exists("projects", name := trim(name), self.imported):
            return project_id
        project_id = self._post(
            f"project {name!r}",
            lambda: api.ProjectsApi(self.client).post_project(
                models.Project(
                    id=id16(),
                    name=name,
                    team_id=self.team_id,
                    author_id=self.author_id,
                    created_at=1,
                    last_event_at=1,
                    ended_at=1 if ended else None,
                    color=color,
                    description=description or "",
                    is_favorite=is_favorite,
                    is_open=is_open,
                    is_template=False,
                    sidebar_position=1.0,
                    extra="",
                )
            ),
        )
        if project_id:
            self._add_to_group(project_id)
        return project_id

    def _add_to_group(self, project_id: str):
        """Add project to import group, created on first use"""
        self.group_id = self.group_id or self._post(
            f"group {self.group_name!r}",
            lambda: api.ProjectGroupsApi(self.client).post_project_group(
                models.ProjectGroup(
                    id=id16(), name=self.group_name, team_id=self.team_id, is_private=True
                )
            ),
        )
        if self.group_id:
            self._post(
                f"project {project_id} in group",
                lambda: api.GroupAssignmentsApi(self.client).post_group_assignment(
                    models.GroupAssignment(
                        id=id16(),
                        object_id=project_id,
                        group_id=self.group_id,
                        group_type="project",
                    )
                ),
            )

    def section(
        self, project_id: str, name: str, position: float, archived: bool = False
    ) -> str | None:
        """Id of section by name in project; created if missing"""
        if section_id := exists("project_sections", name := trim(name), self.imported, project_id):
            return section_id
        return self._post(
            f"section {name!r}",
            lambda: api.ProjectSectionsApi(self.client).post_project_section(
                models.ProjectSection(
                    id=id16(),
                    project_id=project_id,
                    name=name,
                    created_at=1,
                    archived_at=1 if archived else None,
                    position=float(position),
                )
            ),
        )

    def task(
        self,
        project_id: str,
        name: str,
        *,
        section_id: str | None = None,
        position: float | None = None,
        due_at: int | None = None,
        is_all_day: bool = False,
        responsible_id: str | None = None,
        assigned: bool = False,
        ended_at: int | None = None,
    ) -> tuple[str | None, bool]:
        """(id, is_new) of task by name in project; created if missing.
        Responsible only if due: given one, else author (+ 'missing responsibility' tag if
        assigned in source, i.e. assignee not mapped); always author in Single Tasks."""
        if task_id := exists("tasks", name := trim(name), self.imported, project_id):
            return task_id, False
        missing_responsible = False
        if project_id == self.single_tasks_id:
            responsible_id = self.author_id
        elif due_at is None:
            responsible_id = None
        elif not responsible_id:
            responsible_id, missing_responsible = self.author_id, assigned
        task_id = self._post(
            f"task {name!r}",
            lambda: api.TasksApi(self.client).post_task(
                models.PostTaskRequest(
                    id=id16(),
                    name=name,
                    project_id=project_id,
                    project_section_id=section_id,
                    project_position=1.0 if position is None else float(position),
                    author_id=self.author_id,
                    responsible_id=responsible_id,
                    due_at=due_at,
                    is_all_day=bool(is_all_day and due_at is not None),
                    ended_at=ended_at,
                    created_at=1,
                    last_activity_at=1,
                    is_followed=False,
                    is_abandoned=False,
                    missed_repeats=0,
                    extra="",
                )
            ),
        )
        if task_id and missing_responsible:
            self.assign_tags(task_id, [self._tag("missing responsibility")], is_new=True)
        return task_id, task_id is not None

    def comment(self, task_id: str, body: str | None, file: File | None = None) -> str | None:
        """Id of comment, posted unless imported before; file attached unless it has one
        (a run may stop between posting and uploading)"""
        if comment_id := exists("comments", body := body or "…", self.imported, task_id):
            if file and not fetch_all(self.client, f"/comments/{comment_id}/attachments"):
                self._upload(comment_id, *file)
            return comment_id
        comment_id = self._post(
            "comment",
            lambda: api.CommentsApi(self.client).post_comment(
                models.Comment(
                    is_team=False,
                    is_pinned=False,
                    body=body,
                    task_id=task_id,
                    author_id=self.author_id,
                    created_at=1,
                    extra="",
                )
            ),
        )
        if comment_id and file:
            self._upload(comment_id, *file)
        return comment_id

    def _upload(self, comment_id: str, url: str, name: str, headers: dict | None):
        """Download url, attach it to comment as file name"""
        try:
            with (
                requests.get(url, headers=headers or {}, timeout=120, stream=True) as response,
                tempfile.TemporaryDirectory() as tmp,
            ):
                response.raise_for_status()
                response.raw.decode_content = True
                with (path := Path(tmp, Path(name).name or "attachment")).open("wb") as file:
                    shutil.copyfileobj(response.raw, file)
                api.AttachmentsApi(self.client).postattachment_by_id_content2(
                    comment_id, file=str(path)
                )
        except requests.RequestException, OpenApiException, OSError:
            log.warning("attachment %r not uploaded", name, exc_info=True)

    def attachment(
        self, task_id: str, name: str, url: str | None, is_file: bool, headers: dict | None = None
    ):
        """Comment with file name and the file, or with link name and url"""
        if is_file and url:
            self.comment(task_id, name, (url, name, headers))
        else:
            self.comment(task_id, name if not url or name == url else f"{name}\n{url}")

    @cached_property
    def time_zone(self) -> str:
        """Importing user's time zone, UTC if unset"""
        user = api.UsersApi(self.client).get_user_by_id(self.client.configuration.username)
        return getattr(user, "time_zone", None) or "UTC"

    def recurrence(
        self, project_id: str, task_id: str, pattern: str | None, is_all_day: bool, fallback: str
    ):
        """Recurrence (RRULE pattern) of task with due_at; fallback comment if none or refused"""
        if (
            pattern
            and (
                recurrence_id := self._post(
                    f"recurrence {pattern!r}",
                    lambda: api.TaskRecurrencesApi(self.client).post_task_recurrence(
                        models.TaskRecurrence(
                            id=id16(),
                            project_id=project_id,
                            current_task_id=task_id,
                            pattern=pattern,
                        )
                    ),
                )
            )
            and self._post(
                f"recurrence of task {task_id}",
                # PUT /tasks resets is_all_day unless sent
                lambda: api.TasksApi(self.client).put_task_by_id(
                    task_id, models.Task(recurrence_id=recurrence_id, is_all_day=is_all_day)
                ),
            )
        ):
            return
        self.comment(task_id, fallback)

    @cached_property
    def _tags(self) -> dict[str, str]:
        """Team tag name -> id; own posts added"""
        return {
            elt.get("name"): elt.get("id")
            for elt in fetch_all(self.client, "/tags", fields="id,name")
        }

    def _tag(self, name: str, color: str | None = None) -> str | None:
        """Id of tag by name, posted if missing"""
        if (name := trim(name)) not in self._tags and (
            tag_id := self._post(
                f"tag {name!r}",
                lambda: api.TagsApi(self.client).post_tag(
                    models.Tag(id=id16(), name=name, team_id=None, color=map_color(color))
                ),
            )
        ):
            self._tags[name] = tag_id
        return self._tags.get(name)

    def tags(self, labels: Iterable[tuple[str, str | None]]) -> dict[str, str]:
        """Label name -> NT tag id for (name, color) labels; missing ones created"""
        labels = dict(labels)
        self.check_limit("tags", len(self._tags.keys() | set(map(trim, labels))))
        return {
            name: tag_id for name, color in labels.items() if (tag_id := self._tag(name, color))
        }

    def _tasks_tagged(self, tag_id: str) -> set[str]:
        """Ids of tasks having tag, fetched once per tag"""
        if tag_id not in self._tagged:
            self._tagged[tag_id] = {
                elt.get("task_id")
                for elt in fetch_all(
                    self.client, "/tag_assignments", tag_id=tag_id, fields="task_id"
                )
            }
        return self._tagged.get(tag_id)

    def assign_tags(self, task_id: str, tag_ids: Iterable[str | None], is_new: bool):
        """Assign tags to task, skipping assigned ones (none on a new task)"""
        for tag_id in unique_everseen(filter(None, tag_ids)):
            if is_new or task_id not in self._tasks_tagged(tag_id):
                self._post(
                    f"tag {tag_id} on task {task_id}",
                    lambda tag_id=tag_id: api.TagAssignmentsApi(self.client).post_tag_assignment(
                        models.TagAssignment(id=id16(), tag_id=tag_id, task_id=task_id)
                    ),
                )

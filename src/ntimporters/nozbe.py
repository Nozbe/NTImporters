"""Nozbe writes of an import, deduplicated within import group"""

import hashlib
import itertools
import json
import shutil
import tempfile
from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, time
from functools import cached_property
from pathlib import Path

import requests
from more_itertools import first, unique_everseen

from ntimporters.utils import (
    ImportException,
    id16,
    log,
    map_color,
    nt_api_client,
    session,
    subscribe_trial,
    trim,
)
from openapi_client import api, models
from openapi_client.exceptions import ApiException, OpenApiException

type File = tuple[str, str, dict | None]  # (url, name, download headers)


def get_group_id(nt_client, team_id: str, group_name: str) -> str | None:
    """id of project group by name; None if missing"""
    groups = api.ProjectGroupsApi(nt_client).get_project_groups(
        limit=1, name=group_name, team_id=team_id
    )
    return (group := first(groups or [], None)) and group.id


def exists(entity_type: str, name: str, imported: dict, parent: str | None = None) -> str | None:
    """id of next unmatched imported entity by name (under parent), else None;
    ids consumed: n same-named sources match n imported"""
    key = name if parent is None else (parent, name)
    records = imported.get(entity_type, {}).get(key)
    return records.popleft() if records else None


PAGE_SIZE = 10000  # API maximum


def fetch_all(nt_client, path: str, **filters) -> list[dict]:
    """all records of list endpoint path; filters: record fields, applied server-side"""
    records = []
    for offset in itertools.count(0, PAGE_SIZE):
        response = nt_client.call_api(
            *nt_client.param_serialize(
                "GET",
                path,
                query_params=[*filters.items(), ("limit", PAGE_SIZE), ("offset", offset)],
                header_params={"Accept": "application/json"},
                auth_settings=["ApiKeyAuth"],
            )
        )
        response.read()
        if response.status != 200:
            raise ApiException(status=response.status, reason=response.reason, body=response.data)
        records += (page := json.loads(response.data) or [])
        if len(page) < PAGE_SIZE:
            return records


def get_imported_entities(
    nt_client,
    group_id: str | None,
    author_id: str,
    team_projects: list[dict],
    single_tasks: tuple[str, set[str]] | None = None,
) -> dict[str, dict]:
    """ids of group's (+ Single Tasks' imported) entities, creation order: projects by name;
    sections, tasks by (project_id, name); comments by author_id by (task_id, body);
    'recurring': task ids.
    single_tasks: (Single Tasks id, ids of tasks imported there)"""
    imported = {
        kind: defaultdict(deque) for kind in ("projects", "project_sections", "tasks", "comments")
    } | {"recurring": set()}

    def _add(kind: str, records: list[dict], key: Callable):
        for record in sorted(records, key=lambda elt: elt.get("created_at") or 0):
            imported.get(kind)[key(record)].append(record.get("id"))

    def _add_tasks(project_id: str, only: set[str] | None = None) -> set[str]:
        tasks = [
            elt
            for elt in fetch_all(
                nt_client,
                "/tasks",
                project_id=project_id,
                fields="id,name,created_at,recurrence_id",
            )
            if only is None or elt.get("id") in only
        ]
        _add("tasks", tasks, lambda elt: (project_id, elt.get("name")))
        imported.get("recurring").update(elt.get("id") for elt in tasks if elt.get("recurrence_id"))
        return {elt.get("id") for elt in tasks}

    project_ids = set()
    if group_id:
        project_ids = {
            elt.get("object_id")
            for elt in fetch_all(
                nt_client, "/group_assignments", group_id=group_id, group_type="project"
            )
        }
    _add(
        "projects",
        [elt for elt in team_projects if elt.get("id") in project_ids],
        lambda elt: elt.get("name"),
    )
    task_ids = set()
    for project_id in project_ids:
        sections = fetch_all(
            nt_client,
            "/project_sections",
            project_id=project_id,
            fields="id,name,created_at",
        )
        _add(
            "project_sections",
            sections,
            lambda elt, project_id=project_id: (project_id, elt.get("name")),
        )
        task_ids |= _add_tasks(project_id)
    if single_tasks and single_tasks[1]:
        task_ids |= _add_tasks(*single_tasks)
    if task_ids:
        _add(
            "comments",
            [
                elt
                for elt in fetch_all(
                    nt_client, "/comments", author_id=author_id, fields="id,body,task_id,created_at"
                )
                if elt.get("task_id") in task_ids
            ],
            lambda elt: (elt.get("task_id"), elt.get("body")),
        )
    return imported


def due_fields(due: date | datetime | None) -> tuple[int | None, bool]:
    """(due_at ms, is_all_day); date: UTC midnight, all day; naive datetime: UTC"""
    match due:
        case datetime():
            return int((due if due.tzinfo else due.replace(tzinfo=UTC)).timestamp() * 1000), False
        case date():
            return int(datetime.combine(due, time(), UTC).timestamp() * 1000), True
    return None, False


def run_safely(import_data: Callable[[], object], **required) -> Exception | str | None:
    """None on success, else "Missing '<name>'" or raised exception (Nozbe4Backend reports)"""
    if missing := first((name for name, value in required.items() if not value), None):
        return f"Missing '{missing}'"
    try:
        import_data()
    except Exception as exc:
        return exc
    return None


class NozbeImport:
    """import into team, deduped against group_name group; team data read once,
    updated by own writes"""

    def __init__(self, nt_auth_token: str, team_id: str, group_name: str, with_single_tasks=False):
        self.nt_auth_token, self.team_id, self.group_name = nt_auth_token, team_id, group_name
        self.client = nt_api_client(nt_auth_token)
        self._member_ids = {
            elt.get("user_id"): elt.get("id")
            for elt in fetch_all(self.client, "/team_members", team_id=team_id, fields="id,user_id")
        }
        self.author_id = self._member_ids.get(self.client.configuration.username) or id16()
        self.group_id = get_group_id(self.client, team_id, group_name)
        self._tagged = {}  # tag id -> ids of tasks having it
        mark = self._tags.get(group_name) if with_single_tasks else None
        self.imported = get_imported_entities(
            self.client,
            self.group_id,
            self.author_id,
            self._team_projects,
            (self.single_tasks_id, self._tasks_tagged(mark)) if mark else None,
        )

    def _post(self, what: str, call: Callable[[], object]) -> str | None:
        """id of record created by call; None (logged) if refused"""
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
            fields="id,name,created_at,is_single_actions",
        )

    @cached_property
    def single_tasks_id(self) -> str | None:
        """Single Tasks project id"""
        return first(
            (elt.get("id") for elt in self._team_projects if elt.get("is_single_actions")), None
        )

    def check_group(self, has_projects: bool):
        """before any write: import group to create (projects, no group yet) over team's
        project_groups limit (Free: 0) -> trial; refused: ImportException, nothing imported.
        Trial lifts all limits (-1), so no other limit is checked"""
        if self.group_id or not has_projects:
            return
        team = api.TeamsApi(self.client).get_team_by_id(self.team_id)
        limits = json.loads(getattr(team, "limits", None) or "{}")
        if (limit := limits.get("project_groups", -1)) < 0:
            return
        groups = len(fetch_all(self.client, "/project_groups", team_id=self.team_id, fields="id"))
        if groups >= limit and not subscribe_trial(self.nt_auth_token, self.team_id):
            raise ImportException(f"LIMIT project_groups : {groups + 1} > {limit}")

    @cached_property
    def _team_emails(self) -> list[tuple[str, str]]:
        """(email or invitation email, member id) per member"""
        return [
            (email, member_id)
            for elt in fetch_all(self.client, "/users", fields="id,email,invitation_email")
            if (email := elt.get("email") or elt.get("invitation_email"))
            and (member_id := self._member_ids.get(elt.get("id")))
        ]

    def members(self, emails: Mapping[str, str | None], owner: str | None = None) -> dict[str, str]:
        """3rd party id -> member id by email (case-insensitive; NT email may be
        md5(user_id + email)); owner (token's 3rd party id) -> author"""
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
        } | ({owner: self.author_id} if owner else {})

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
        """id of project by name in import group; created + grouped if missing"""
        if project_id := exists("projects", name := trim(name), self.imported):
            return project_id
        self._group()  # first: no project outside group
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

    def _group(self) -> str:
        """import group id, created on first use; ImportException if refused
        (ungrouped projects duplicate on re-run)"""
        self.group_id = self.group_id or self._post(
            f"group {self.group_name!r}",
            lambda: api.ProjectGroupsApi(self.client).post_project_group(
                models.ProjectGroup(
                    id=id16(), name=self.group_name, team_id=self.team_id, is_private=True
                )
            ),
        )
        if not self.group_id:
            raise ImportException(f"Can't create project group {self.group_name!r}")
        return self.group_id

    def _add_to_group(self, project_id: str):
        """new project into import group; refused: project deleted (still empty),
        ImportException (re-run would duplicate)"""
        if self._post(
            f"project {project_id} in group",
            lambda: api.GroupAssignmentsApi(self.client).post_group_assignment(
                models.GroupAssignment(
                    id=id16(), object_id=project_id, group_id=self._group(), group_type="project"
                )
            ),
        ):
            return
        try:
            api.ProjectsApi(self.client).delete_project_by_id(project_id)
        except OpenApiException:
            log.warning("project %s outside group not deleted", project_id, exc_info=True)
        raise ImportException(f"Can't add project to group {self.group_name!r}")

    def section(
        self, project_id: str, name: str, position: float, archived: bool = False
    ) -> str | None:
        """id of section by name in project; created if missing"""
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
        due: date | datetime | None = None,
        responsible_id: str | None = None,
        assigned: bool = False,
        ended_at: int | None = None,
        recurrence: tuple[str | None, str] | None = None,
        remind_at: int | None = None,
    ) -> tuple[str | None, bool]:
        """(id, is_new) of task by name in project; created if missing.
        due: see due_fields. responsible: Single Tasks -> author; no due -> None; unmapped ->
        author (+ 'missing responsibility' tag if assigned).
        recurrence: (RRULE pattern, fallback comment), open + due only. remind_at: ms, absolute.
        New Single Task: tagged group_name.
        Imported task: only missing tag, recurrence, reminder added (run may stop after post)."""
        due_at, is_all_day = due_fields(due)
        missing_responsible = False
        if project_id == self.single_tasks_id:
            responsible_id = self.author_id
        elif due_at is None:
            responsible_id = None
        elif not responsible_id:
            responsible_id, missing_responsible = self.author_id, assigned
        task_id = exists("tasks", name := trim(name), self.imported, project_id)
        if is_new := not task_id:
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
                        is_all_day=is_all_day,
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
            if not task_id:
                return None, False
            if project_id == self.single_tasks_id:  # marks it imported, see __init__
                self.assign_tags(task_id, [self._tag(self.group_name)], is_new=True)
        if missing_responsible:
            self.assign_tags(task_id, [self._tag("missing responsibility")], is_new=is_new)
        if (
            recurrence
            and due_at is not None
            and ended_at is None
            and task_id not in self.imported.get("recurring")
        ):
            pattern, fallback = recurrence
            self.recurrence(project_id, task_id, pattern, is_all_day, fallback)
        if remind_at is not None and (is_new or task_id not in self._reminded):
            self._post(
                f"reminder of task {task_id}",
                lambda: api.RemindersApi(self.client).post_reminder(
                    models.Reminder(
                        id=id16(),
                        task_id=task_id,
                        remind_at=remind_at,
                        is_relative=False,
                        is_all_day=False,
                    )
                ),
            )
        return task_id, is_new

    @cached_property
    def _reminded(self) -> set[str]:
        """ids of tasks with reminder; /reminders filters by task only: all fetched once"""
        return {
            elt.get("task_id") for elt in fetch_all(self.client, "/reminders", fields="task_id")
        }

    def comment(self, task_id: str, body: str | None, file: File | None = None) -> str | None:
        """comment id; posted unless imported; file attached unless present
        (run may stop between post and upload)"""
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

    @cached_property
    def _downloads(self) -> requests.Session:
        """attachment download session; rate limits waited out"""
        return session({})

    def _upload(self, comment_id: str, url: str, name: str, headers: dict | None):
        """url downloaded, attached to comment as name"""
        base = Path(name).name
        base = base if base not in ("", ".", "..") else "attachment"
        try:
            with (
                self._downloads.get(url, headers=headers, timeout=120, stream=True) as response,
                tempfile.TemporaryDirectory() as tmp,
            ):
                response.raise_for_status()
                response.raw.decode_content = True
                with (path := Path(tmp, base)).open("wb") as file:
                    shutil.copyfileobj(response.raw, file)
                api.AttachmentsApi(self.client).postattachment_by_id_content2(
                    comment_id, file=str(path)
                )
        except requests.RequestException, OpenApiException, OSError:
            log.warning("attachment %r not uploaded", name, exc_info=True)

    def attachment(
        self,
        task_id: str,
        name: str | None,
        url: str | None,
        is_file: bool,
        headers: dict | None = None,
    ):
        """comment: name ('attachment' if empty) + file if is_file, else name + url"""
        name = name or "attachment"
        if is_file and url:
            self.comment(task_id, name, (url, name, headers))
        else:
            self.comment(task_id, name if not url or name == url else f"{name}\n{url}")

    @cached_property
    def time_zone(self) -> str:
        """importing user's time zone; UTC if unset or unreadable"""
        try:
            user = api.UsersApi(self.client).get_user_by_id(self.client.configuration.username)
        except OpenApiException:
            log.warning("user's time zone not read, UTC used", exc_info=True)
            return "UTC"
        return getattr(user, "time_zone", None) or "UTC"

    def recurrence(
        self, project_id: str, task_id: str, pattern: str | None, is_all_day: bool, fallback: str
    ):
        """RRULE pattern on task with due_at; fallback comment if None or refused"""
        recurrence_id = pattern and self._post(
            f"recurrence {pattern!r}",
            lambda: api.TaskRecurrencesApi(self.client).post_task_recurrence(
                models.TaskRecurrence(
                    id=id16(), project_id=project_id, current_task_id=task_id, pattern=pattern
                )
            ),
        )
        if not recurrence_id or not self._post(
            f"recurrence of task {task_id}",
            # PUT /tasks resets is_all_day unless sent; None: flags left as they are
            lambda: api.TasksApi(self.client).put_task_by_id(
                task_id,
                models.Task(
                    recurrence_id=recurrence_id,
                    is_all_day=is_all_day,
                    is_followed=None,
                    is_abandoned=None,
                ),
            ),
        ):
            self.comment(task_id, fallback)

    @cached_property
    def _tags(self) -> dict[str, str]:
        """name -> id of tags visible in team (private + team's); own posts added"""
        return {
            elt.get("name"): elt.get("id")
            for elt in fetch_all(self.client, "/tags", fields="id,name,team_id")
            if elt.get("team_id") in (None, self.team_id)
        }

    def _tag(self, name: str, color: str | None = None) -> str | None:
        """id of tag by name; posted if missing"""
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
        """(name, color) labels -> name -> tag id; missing created"""
        return {
            name: tag_id
            for name, color in dict(labels).items()
            if (tag_id := self._tag(name, color))
        }

    def _tasks_tagged(self, tag_id: str) -> set[str]:
        """ids of tasks with tag; fetched once per tag"""
        if tag_id not in self._tagged:
            self._tagged[tag_id] = {
                elt.get("task_id")
                for elt in fetch_all(
                    self.client, "/tag_assignments", tag_id=tag_id, fields="task_id"
                )
            }
        return self._tagged.get(tag_id)

    def assign_tags(self, task_id: str, tag_ids: Iterable[str | None], is_new: bool):
        """tags assigned to task unless present (none on new task)"""
        for tag_id in unique_everseen(filter(None, tag_ids)):
            if is_new or task_id not in self._tasks_tagged(tag_id):
                self._post(
                    f"tag {tag_id} on task {task_id}",
                    lambda tag_id=tag_id: api.TagAssignmentsApi(self.client).post_tag_assignment(
                        models.TagAssignment(id=id16(), tag_id=tag_id, task_id=task_id)
                    ),
                )

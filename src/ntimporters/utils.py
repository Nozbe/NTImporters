"""Common helper functions"""

import itertools
import json
import logging
import random
import string
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC
from os import getenv

import requests
from dateutil.parser import isoparse
from more_itertools import first
from urllib3.util.retry import Retry

import openapi_client as nt
from openapi_client import Color, api
from openapi_client.exceptions import ApiException

log = logging.getLogger("ntimporters")

HOST = "api4"
if getenv("DEV_ACCESS_TOKEN"):
    HOST = f"dev{HOST}"
API_HOST = getenv("CUSTOM_API_HOST") or f"https://{HOST}.nozbe.com/v1/api"


def nt_api_client(nt_auth_token: str) -> nt.ApiClient:
    """NT API client: current API version, dev token, 429 retried every 10 s up to 36 times"""
    configuration = nt.Configuration(
        host=API_HOST,
        api_key={"ApiKeyAuth": nt_auth_token},
        username=nt_auth_token.split("_")[0],
    )
    configuration.retries = Retry(
        total=36,
        status_forcelist=[429],
        allowed_methods=None,
        backoff_factor=10,
        backoff_max=10,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    client = nt.ApiClient(configuration)
    client.set_default_header("Api-Version", "current")
    if devtoken := getenv("DEV_ACCESS_TOKEN"):
        client.set_default_header("X-DevToken", devtoken)
    return client


def dig(data, path: str, default=None):
    """Value at dotted path ("data.boards.0.groups"), default if missing or None"""
    for key in path.split("."):
        match data:
            case dict():
                data = data.get(key)
            case list() if key.isdigit() and int(key) < len(data):
                data = data[int(key)]
            case _:
                return default
    return default if data is None else data


def id16():
    """Generate random string"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


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


def get_group_id(nt_client, team_id: str, group_name: str) -> str | None:
    """Get project group id if any"""
    groups = api.ProjectGroupsApi(nt_client).get_project_groups(
        limit=1, name=group_name, team_id=team_id
    )
    return (group := first(groups or [], None)) and group.id


def exists(entity_type: str, name: str, imported: dict, parent: str | None = None) -> str | None:
    """Id of next not yet matched imported entity by name (under parent id), or None.
    Matched ids are used up, so n same-named source entities match n imported ones."""
    key = name if parent is None else (parent, name)
    records = imported.get(entity_type, {}).get(key)
    return records.popleft() if records else None


PAGE_SIZE = 10000  # API maximum


def fetch_all(nt_client, path: str, **filters) -> list[dict]:
    """All records of Nozbe list endpoint path; filters on record fields run in backend's SQL"""
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
    single_tasks_id: str | None = None,
) -> dict[str, dict]:
    """Ids of group's projects (and Single Tasks' tasks), in creation order: projects by name,
    sections and tasks by (project_id, name), comments by (task_id, body).
    Only group's data is fetched; comments: those by author_id (importer posts as author)."""
    imported = {
        kind: defaultdict(deque) for kind in ("projects", "project_sections", "tasks", "comments")
    }

    def _add(kind: str, records: list[dict], key: Callable):
        for record in sorted(records, key=lambda elt: elt.get("created_at") or 0):
            imported.get(kind)[key(record)].append(record.get("id"))

    def _add_tasks(project_id: str) -> set[str]:
        tasks = fetch_all(nt_client, "/tasks", project_id=project_id, fields="id,name,created_at")
        _add("tasks", tasks, lambda elt: (project_id, elt.get("name")))
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
        _add(
            "project_sections",
            fetch_all(
                nt_client, "/project_sections", project_id=project_id, fields="id,name,created_at"
            ),
            lambda elt, project_id=project_id: (project_id, elt.get("name")),
        )
        task_ids |= _add_tasks(project_id)
    if single_tasks_id:
        task_ids |= _add_tasks(single_tasks_id)
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


def map_color(color: str | None) -> Color:
    """Maps color onto Nozbe color"""
    colors = [elt.value for elt in Color if elt.value != "null"]
    return Color(color if color in colors else random.choice(colors))  # nosec


def trim(name: str | None) -> str:
    """First 255 characters, "Untitled" if empty"""
    return (name or "")[:255] or "Untitled"


def parse_timestamp(datetime: str | None) -> int | None:
    """ISO date/datetime -> ms; date-only or naive as UTC"""
    if not datetime:
        return None
    moment = isoparse(datetime)
    return int((moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp() * 1000)

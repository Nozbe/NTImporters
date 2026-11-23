from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from ntimporters.utils import exists, get_imported_entities, nt_api_client, parse_timestamp


def test_imported_entities_chain():
    """Same task name / comment body under different parents (incl. Single Tasks) stay distinct"""
    nt_api = MagicMock()
    nt_api.GroupAssignmentsApi().get_group_assignments.return_value = [
        NS(object_id="home"),
        NS(object_id="work"),
    ]
    nt_api.ProjectsApi().get_project_by_id.side_effect = lambda pid: NS(id=pid, name=pid.title())
    nt_api.ProjectSectionsApi().get_project_sections.return_value = []
    nt_api.TasksApi().get_tasks.side_effect = lambda project_id: [
        NS(id=f"{project_id}-call", name="Call mom")
    ]
    nt_api.CommentsApi().get_comments.side_effect = lambda task_id: (
        [NS(id="c1", body="ok")] if task_id == "home-call" else []
    )
    nt_api.TagsApi().get_tags.return_value = []
    with (
        patch("ntimporters.utils.api", nt_api),
        patch("ntimporters.utils.get_group_id", return_value="group"),
        patch("ntimporters.utils.get_single_tasks_project_id", return_value="sap"),
    ):
        imported = get_imported_entities(
            None, "team", "Imported from Todoist", with_single_tasks=True
        )

    assert exists("projects", "Work", imported).id == "work"
    assert exists("tasks", "Call mom", imported, "home").id == "home-call"
    assert exists("tasks", "Call mom", imported, "work").id == "work-call"
    assert exists("tasks", "Call mom", imported, "sap").id == "sap-call"
    assert not exists("tasks", "Call mom", imported)
    assert exists("comments", "ok", imported, "home-call")
    assert not exists("comments", "ok", imported, "work-call")


def test_parse_timestamp_utc():
    """Date-only and naive values are UTC, aware ones kept"""
    assert parse_timestamp("2026-11-26") == 1795651200000
    assert parse_timestamp("2026-11-24T14:30:00") == parse_timestamp("2026-11-24T15:30:00+01:00")
    assert parse_timestamp(None) is None


def test_nt_api_client(monkeypatch):
    """Api-Version, dev token headers and 429 retries set outside generated code"""
    monkeypatch.setenv("DEV_ACCESS_TOKEN", "dev")
    client = nt_api_client("user_key")
    assert client.default_headers.get("Api-Version") == "current"
    assert client.default_headers.get("X-DevToken") == "dev"
    assert client.configuration.username == "user"
    assert 429 in client.configuration.retries.status_forcelist

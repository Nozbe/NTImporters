from ntimporters.utils import dig, exists, get_imported_entities, nt_api_client, parse_timestamp


def test_imported_entities_chain(nt):
    """Same names under different parents (incl. Single Tasks) stay distinct; under one parent
    each imported record matches once; only group's data and author's comments fetched"""
    nt.records = {
        "/tasks": [
            {"id": "home-call", "name": "Call mom", "created_at": 2, "project_id": "home"},
            {"id": "home-call-1", "name": "Call mom", "created_at": 1, "project_id": "home"},
            {"id": "work-call", "name": "Call mom", "project_id": "work"},
            {"id": "sap-call", "name": "Call mom", "project_id": "sap"},
            {"id": "other-call", "name": "Call mom", "project_id": "other"},
        ],
        "/group_assignments": [
            {"object_id": "home", "group_id": "group"},
            {"object_id": "work", "group_id": "group"},
            {"object_id": "other", "group_id": "elsewhere"},
        ],
        "/comments": [
            {"id": "c1", "body": "ok", "task_id": "home-call", "author_id": "me"},
            {"id": "c2", "body": "ok", "task_id": "work-call", "author_id": "else"},
        ],
    }
    team_projects = [{"id": pid, "name": pid.title()} for pid in ("home", "work", "other")]
    imported = get_imported_entities(None, "group", "me", team_projects, "sap")

    assert exists("projects", "Work", imported) == "work"
    assert not exists("projects", "Other", imported)  # not in group
    # same-named tasks matched one by one, in creation order
    assert exists("tasks", "Call mom", imported, "home") == "home-call-1"
    assert exists("tasks", "Call mom", imported, "home") == "home-call"
    assert not exists("tasks", "Call mom", imported, "home")
    assert exists("tasks", "Call mom", imported, "work") == "work-call"
    assert exists("tasks", "Call mom", imported, "sap") == "sap-call"
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


def test_dig():
    """Dotted path through dicts and list indices; default on miss or None"""
    data = {"a": [{"b": 1}, {"b": None}]}
    assert dig(data, "a.0.b") == 1
    assert dig(data, "a.1.b", 0) == 0
    assert dig(data, "a.5.b") is None
    assert dig(data, "a.x") is None

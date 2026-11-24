import hashlib
from collections import deque
from datetime import date, datetime
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from ntimporters.nozbe import NozbeImport, due_fields, exists, get_imported_entities, run_safely
from ntimporters.utils import ImportException

AUTHOR, SAP, PROJECT = "a" * 16, "s" * 16, "p" * 16
OLD, OTHER, NEW, TAG, COMMENT = "o" * 16, "q" * 16, "n" * 16, "x" * 16, "c" * 16


@pytest.fixture
def nz(nt):
    """Team: author, Ann, Bob; Single Tasks; grouped project: tasks 'Old' (recurring), OLD
    (comment 'pic'), sections 'S', archived 'A'. fetch_all reset after construction"""
    nt.records |= {
        "/team_members": [
            {"user_id": "user", "id": AUTHOR},
            {"user_id": "u1", "id": "m1"},
            {"user_id": "u2", "id": "m2"},
        ],
        "/users": [
            {"id": "u1", "email": "Ann@x.com"},
            {"id": "u2", "email": hashlib.md5(b"u2bob@y.com").hexdigest()},
        ],
        "/projects": [{"id": SAP, "is_single_actions": True}, {"id": PROJECT, "name": "P"}],
        "/group_assignments": [{"object_id": PROJECT}],
        "/tasks": [
            {"id": "old", "name": "Old", "project_id": PROJECT, "recurrence_id": "r" * 16},
            {"id": OLD, "name": "Pic", "project_id": PROJECT},
        ],
        "/comments": [{"id": COMMENT, "body": "pic", "task_id": OLD}],
        "/project_sections": [
            {"id": "s", "name": "S", "project_id": PROJECT},
            {"id": "a", "name": "A", "project_id": PROJECT, "archived_at": 1},
        ],
        "/tags": [{"id": "t" * 16, "name": "missing responsibility"}],
    }
    nt.api.ProjectGroupsApi().get_project_groups.return_value = [NS(id="g" * 16)]
    nz = NozbeImport("user_key", "team", "Imported")
    nt.fetch_all.reset_mock()
    return nz


def test_run_safely():
    """Missing field named; exception returned; None on success"""
    assert run_safely(lambda: None, token="", key="x") == "Missing 'token'"
    assert isinstance(run_safely(lambda: 1 / 0, token="t"), ZeroDivisionError)
    assert run_safely(lambda: None, token="t") is None


@pytest.mark.parametrize(
    "project_id, due_at, responsible_id, assigned, expected, tagged",
    [
        (PROJECT, 1, None, True, AUTHOR, True),  # due, assignee not mapped: author + tag
        (PROJECT, 1, None, False, AUTHOR, False),  # due, unassigned: author
        (PROJECT, 1, "m" * 16, True, "m" * 16, False),
        (PROJECT, None, "m" * 16, True, None, False),  # no due: nobody
        (PROJECT, None, None, True, None, False),
        (SAP, None, "m" * 16, True, AUTHOR, False),  # Single Tasks: always author
    ],
)
def test_task_responsible(nt, nz, project_id, due_at, responsible_id, assigned, expected, tagged):
    nt.api.TasksApi().post_task.return_value = NS(id=NEW)
    due = date(2024, 1, 1) if due_at else None
    task = nz.task(project_id, "New", due=due, responsible_id=responsible_id, assigned=assigned)
    assert task == (NEW, True)
    assert nt.api.TasksApi().post_task.call_args.args[0].responsible_id == expected
    assert nt.api.TagAssignmentsApi().post_tag_assignment.called == tagged


def test_due_fields_naive_as_utc():
    assert due_fields(datetime(2026, 1, 1)) == (due_fields(date(2026, 1, 1))[0], False)


def test_task_recurrence_with_due_unless_recurring(nt, nz, monkeypatch):
    """If due: set on new task and on imported one without recurrence"""
    monkeypatch.setattr(NozbeImport, "recurrence", recurrence := MagicMock())
    nt.api.TasksApi().post_task.return_value = NS(id=NEW)
    day = date(2026, 1, 1)
    for name, due in (("Old", day), ("Pic", day), ("Undated", None), ("Dated", day)):
        nz.task(PROJECT, name, due=due, recurrence=("FREQ=DAILY", "daily"))
    posted = nt.api.TasksApi().post_task.call_args.args[0]
    assert (posted.due_at, posted.is_all_day) == (1767225600000, True)
    assert [elt.args[1] for elt in recurrence.call_args_list] == [OLD, NEW]
    recurrence.assert_called_with(PROJECT, NEW, "FREQ=DAILY", True, "daily")


def test_section_limit_counts_open_sections(nt, nz, monkeypatch):
    """Existing open sections count; reused, archived ones don't add"""
    nz._limits = {"project_sections": 2}
    monkeypatch.setattr("ntimporters.nozbe.subscribe_trial", lambda *_: False)
    nt.api.ProjectSectionsApi().post_project_section.return_value = NS(id=NEW)
    assert nz.section(PROJECT, "S", 0) == "s"
    nz.section(PROJECT, "Archived", 1, archived=True)
    nz.section(PROJECT, "New", 2)
    with pytest.raises(ImportException):
        nz.section(PROJECT, "Newer", 3)


def test_assign_tags_skips_assigned(nt, nz):
    """Existing task: assignments fetched once per tag; new task: none fetched"""
    nt.records["/tag_assignments"] = [{"task_id": OLD}]
    nz.assign_tags(OLD, [TAG, TAG, None], is_new=False)
    nz.assign_tags(OTHER, [TAG], is_new=False)
    nz.assign_tags(NEW, ["y" * 16], is_new=True)
    assert nt.fetch_all.call_count == 1
    posted = nt.api.TagAssignmentsApi().post_tag_assignment.call_args_list
    assert [elt.args[0].task_id for elt in posted] == [OTHER, NEW]


def test_task_imported_before(nt, nz):
    assert nz.task(PROJECT, "Old") == ("old", False)
    nt.api.TasksApi().post_task.assert_not_called()


def test_members(nz):
    """By email, case-insensitive; md5(user_id + email) form too"""
    assert nz.members({"a": "ann@X.com", "b": "Bob@y.com", "c": "nobody@z.com", "d": None}) == {
        "a": "m1",
        "b": "m2",
    }
    assert nz.members({"c": "nobody@z.com"}, owner="c") == {"c": AUTHOR}  # token owner


@pytest.mark.parametrize("attached, uploads", [([], 1), ([{"id": "f"}], 0)])
def test_comment_imported_before_reuploads_missing_file(nt, nz, monkeypatch, attached, uploads):
    """Existing comment: file uploaded iff it has none"""
    nt.records[f"/comments/{COMMENT}/attachments"] = attached
    monkeypatch.setattr(NozbeImport, "_upload", upload := MagicMock())
    assert nz.comment(OLD, "pic", ("https://f", "pic.png", None)) == COMMENT
    nt.api.CommentsApi().post_comment.assert_not_called()
    assert upload.call_count == uploads


def test_check_open_projects_counts_only_new(nz, monkeypatch):
    nz._limits, nz._team_projects = {"projects_open": 2}, []
    nz.imported["projects"] = {"Home": deque(["h" * 16])}
    monkeypatch.setattr("ntimporters.nozbe.subscribe_trial", lambda *_: False)
    nz.check_open_projects(["Home", "Work", "Gym"])  # 2 new
    with pytest.raises(ImportException):
        nz.check_open_projects(["Home", "Home", "Work", "Gym"])  # 3 new: second Home too


def test_check_limit_missing_is_unlimited(nz, monkeypatch):
    nz._limits = {"projects": 1}
    monkeypatch.setattr("ntimporters.nozbe.subscribe_trial", lambda *_: False)
    nz.check_limit("project_sections", 100)
    with pytest.raises(ImportException):
        nz.check_limit("projects", 2)


def test_imported_entities_chain(nt):
    """Same names, different parents (incl. Single Tasks): distinct; one parent: each record
    matches once; fetched: group's data, author's comments only"""
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
    # same names: one match each, by creation order
    assert exists("tasks", "Call mom", imported, "home") == "home-call-1"
    assert exists("tasks", "Call mom", imported, "home") == "home-call"
    assert not exists("tasks", "Call mom", imported, "home")
    assert exists("tasks", "Call mom", imported, "work") == "work-call"
    assert exists("tasks", "Call mom", imported, "sap") == "sap-call"
    assert not exists("tasks", "Call mom", imported)
    assert exists("comments", "ok", imported, "home-call")
    assert not exists("comments", "ok", imported, "work-call")


def test_task_reminder_unless_task_has_one(nt, nz):
    """New task: posted, reminders not fetched; imported: posted iff it has none"""
    nt.records["/reminders"] = [{"task_id": "old"}]
    nt.api.TasksApi().post_task.return_value = NS(id=NEW)
    nz.task(PROJECT, "New", remind_at=5)
    nt.fetch_all.assert_not_called()
    nz.task(PROJECT, "Old", remind_at=5)
    nz.task(PROJECT, "Pic", remind_at=6)
    assert nt.fetch_all.call_count == 1
    posted = nt.api.RemindersApi().post_reminder.call_args_list
    assert [(elt.args[0].task_id, elt.args[0].remind_at) for elt in posted] == [(NEW, 5), (OLD, 6)]


def test_task_imported_before_gets_missing_responsibility_tag(nt, nz):
    nt.records["/tag_assignments"] = [{"tag_id": "t" * 16, "task_id": "old"}]
    for name in ("Old", "Pic"):
        assert not nz.task(PROJECT, name, due=date(2026, 1, 1), assigned=True)[1]
    posted = nt.api.TagAssignmentsApi().post_tag_assignment.call_args_list
    assert [elt.args[0].task_id for elt in posted] == [OLD]


def test_tags_visible_in_team_only(nt, nz, monkeypatch):
    """Other teams' tags: not matched, not counted"""
    nt.records["/tags"] = [
        {"id": "t" * 16, "name": "home", "team_id": None},
        {"id": "u" * 16, "name": "work", "team_id": "team"},
        {"id": "v" * 16, "name": "gym", "team_id": "other"},
    ]
    nz._limits = {"tags": 3}
    monkeypatch.setattr("ntimporters.nozbe.subscribe_trial", lambda *_: False)
    nt.api.TagsApi().post_tag.return_value = NS(id=NEW)
    assert nz.tags([("home", None), ("work", None), ("gym", None)]) == {
        "home": "t" * 16,
        "work": "u" * 16,
        "gym": NEW,
    }


def test_project_group_refused_stops_before_project(nt, nz):
    nz.group_id = None
    nt.api.ProjectGroupsApi().post_project_group.side_effect = ValueError
    with pytest.raises(ImportException, match="group"):
        nz.project("New")
    nt.api.ProjectsApi().post_project.assert_not_called()


def test_project_outside_group_deleted(nt, nz):
    nz.team_id = "t" * 16
    nt.api.ProjectsApi().post_project.return_value = NS(id=NEW)
    nt.api.GroupAssignmentsApi().post_group_assignment.side_effect = ValueError
    with pytest.raises(ImportException, match="group"):
        nz.project("New")
    nt.api.ProjectsApi().delete_project_by_id.assert_called_once_with(NEW)

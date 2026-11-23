import hashlib
from collections import deque
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.utils import ImportException

AUTHOR, SAP, PROJECT = "a" * 16, "s" * 16, "p" * 16
OLD, OTHER, NEW, TAG, COMMENT = "o" * 16, "q" * 16, "n" * 16, "x" * 16, "c" * 16


@pytest.fixture
def nz(nt):
    """NozbeImport of team: author, Ann, Bob; Single Tasks; grouped project with tasks
    'Old' and OLD, the latter commented 'pic' by author. Construction calls forgotten."""
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
            {"id": "old", "name": "Old", "project_id": PROJECT},
            {"id": OLD, "name": "Pic", "project_id": PROJECT},
        ],
        "/comments": [{"id": COMMENT, "body": "pic", "task_id": OLD}],
        "/tags": [{"id": "t" * 16, "name": "missing responsibility"}],
    }
    nt.api.ProjectGroupsApi().get_project_groups.return_value = [NS(id="g" * 16)]
    nz = NozbeImport("user_key", "team", "Imported")
    nt.fetch_all.reset_mock()
    return nz


def test_run_safely():
    """Missing field named, exception returned (Nozbe4Backend reports it), None on success"""
    assert run_safely(lambda: None, token="", key="x") == "Missing 'token'"
    assert isinstance(run_safely(lambda: 1 / 0, token="t"), ZeroDivisionError)
    assert run_safely(lambda: None, token="t") is None


@pytest.mark.parametrize(
    "project_id, due_at, responsible_id, assigned, expected, tagged",
    [
        (PROJECT, 1, None, True, AUTHOR, True),  # due, assignee not mapped: author + tag
        (PROJECT, 1, None, False, AUTHOR, False),  # due, unassigned in source: author
        (PROJECT, 1, "m" * 16, True, "m" * 16, False),
        (PROJECT, None, "m" * 16, True, None, False),  # no due: nobody responsible
        (PROJECT, None, None, True, None, False),
        (SAP, None, "m" * 16, True, AUTHOR, False),  # Single Tasks: always author
    ],
)
def test_task_responsible(nt, nz, project_id, due_at, responsible_id, assigned, expected, tagged):
    nt.api.TasksApi().post_task.return_value = NS(id=NEW)
    task = nz.task(
        project_id, "New", due_at=due_at, responsible_id=responsible_id, assigned=assigned
    )
    assert task == (NEW, True)
    assert nt.api.TasksApi().post_task.call_args.args[0].responsible_id == expected
    assert nt.api.TagAssignmentsApi().post_tag_assignment.called == tagged


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
    """Source id -> member by email, case-insensitive; md5(user_id + email) form matched"""
    assert nz.members({"a": "ann@X.com", "b": "Bob@y.com", "c": "nobody@z.com", "d": None}) == {
        "a": "m1",
        "b": "m2",
    }


@pytest.mark.parametrize("attached, uploads", [([], 1), ([{"id": "f"}], 0)])
def test_comment_imported_before_reuploads_missing_file(nt, nz, monkeypatch, attached, uploads):
    """Existing comment: file uploaded only if it has none (run stopped before upload)"""
    nt.records[f"/comments/{COMMENT}/attachments"] = attached
    monkeypatch.setattr(NozbeImport, "_upload", upload := MagicMock())
    assert nz.comment(OLD, "pic", ("https://f", "pic.png", None)) == COMMENT
    nt.api.CommentsApi().post_comment.assert_not_called()
    assert upload.call_count == uploads


def test_check_open_projects_counts_only_new(nz, monkeypatch):
    """Projects imported before don't count against the open projects limit"""
    nz._limits, nz._team_projects = {"projects_open": 2}, []
    nz.imported["projects"] = {"Home": deque(["h" * 16])}
    monkeypatch.setattr("ntimporters.nozbe.subscribe_trial", lambda *_: False)
    nz.check_open_projects(["Home", "Work", "Gym"])  # 2 new
    with pytest.raises(ImportException):
        nz.check_open_projects(["Home", "Home", "Work", "Gym"])  # 3 new: second Home too

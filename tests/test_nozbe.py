import hashlib
import io
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from ntimporters.nozbe import (
    NozbeImport,
    due_fields,
    exists,
    get_imported_entities,
    run_safely,
    utc_until,
)
from ntimporters.utils import ImportException
from openapi_client.exceptions import ApiException, OpenApiException

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
        (PROJECT, None, "m" * 16, True, "m" * 16, False),  # no due, mapped: kept
        (PROJECT, None, None, True, None, False),  # no due, unmapped: nobody
        (SAP, None, "m" * 16, True, AUTHOR, False),  # Single Tasks: always author
    ],
)
def test_task_responsible(nt, nz, project_id, due_at, responsible_id, assigned, expected, tagged):
    nt.api.TasksApi().post_task.return_value = NS(id=NEW)
    nt.api.TagsApi().post_tag.return_value = NS(id="i" * 16)  # Single Tasks' import tag
    due = date(2024, 1, 1) if due_at else None
    task = nz.task(project_id, "New", due=due, responsible_id=responsible_id, assigned=assigned)
    assert task == (NEW, True)
    assert nt.api.TasksApi().post_task.call_args.args[0].responsible_id == expected
    assigned_tags = nt.api.TagAssignmentsApi().post_tag_assignment.call_args_list
    assert any(call.args[0].tag_id == "t" * 16 for call in assigned_tags) == tagged


def test_due_fields_naive_as_utc():
    assert due_fields(datetime(2026, 1, 1)) == (due_fields(date(2026, 1, 1))[0], False)


def test_task_recurrence_with_due_unless_recurring(nt, nz, monkeypatch):
    """If due and open: set on new task and on imported one without recurrence"""
    monkeypatch.setattr(NozbeImport, "recurrence", recurrence := MagicMock())
    nt.api.TasksApi().post_task.return_value = NS(id=NEW)
    day = date(2026, 1, 1)
    for name, due in (("Old", day), ("Pic", day), ("Undated", None), ("Dated", day)):
        nz.task(PROJECT, name, due=due, recurrence=("FREQ=DAILY", "daily"))
    nz.task(PROJECT, "Done", due=day, ended_at=1, recurrence=("FREQ=DAILY", "daily"))
    posted = nt.api.TasksApi().post_task.call_args.args[0]
    assert (posted.due_at, posted.is_all_day) == (1767225600000, True)
    assert [elt.args[1] for elt in recurrence.call_args_list] == [OLD, NEW]
    recurrence.assert_called_with(PROJECT, NEW, "FREQ=DAILY", True, "daily")


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


def test_comment_matches_former_body(nt, nz):
    """Imported in earlier format: matched, not posted"""
    assert nz.comment(OLD, "**pic**", former=["pic"]) == COMMENT
    nt.api.CommentsApi().post_comment.assert_not_called()


@pytest.mark.parametrize(
    "attached, uploads", [([], 1), ([NS(id="f")], 0), (ApiException(status=503), 0)]
)
def test_comment_imported_before_reuploads_missing_file(nt, nz, monkeypatch, attached, uploads):
    """Existing comment: file uploaded iff it has none; unreadable: skipped"""
    nt.api.AttachmentsApi().getattachments.side_effect = (
        attached if isinstance(attached, Exception) else lambda _: attached
    )
    monkeypatch.setattr(NozbeImport, "_upload", upload := MagicMock())
    assert nz.comment(OLD, "pic", ("https://f", "pic.png", None)) == COMMENT
    nt.api.CommentsApi().post_comment.assert_not_called()
    assert upload.call_count == uploads


@pytest.mark.parametrize("name, saved", [("a/b.png", "b.png"), ("..", "attachment")])
def test_upload_saves_under_base_name(nt, nz, name, saved):
    nz._downloads = MagicMock()
    nz._downloads.get().__enter__().raw = io.BytesIO(b"data")
    nz._upload(COMMENT, "https://f", name, None)
    path = nt.api.AttachmentsApi().postattachment_by_id_content2.call_args.kwargs.get("file")
    assert Path(path).name == saved


def test_imported_entities_chain(nt):
    """Same names, different parents (incl. Single Tasks): distinct; one parent: each record
    matches once; fetched: group's data, imported Single Tasks, author's comments only"""
    nt.records = {
        "/tasks": [
            {"id": "home-call", "name": "Call mom", "created_at": 2, "project_id": "home"},
            {"id": "home-call-1", "name": "Call mom", "created_at": 1, "project_id": "home"},
            {"id": "work-call", "name": "Call mom", "project_id": "work"},
            {"id": "sap-call", "name": "Call mom", "project_id": "sap"},
            {"id": "sap-own", "name": "Call mom", "project_id": "sap", "created_at": 0},
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
    imported = get_imported_entities(None, "group", "me", team_projects, ("sap", {"sap-call"}))

    assert exists("projects", "Work", imported) == "work"
    assert not exists("projects", "Other", imported)  # not in group
    # same names: one match each, by creation order
    assert exists("tasks", "Call mom", imported, "home") == "home-call-1"
    assert exists("tasks", "Call mom", imported, "home") == "home-call"
    assert not exists("tasks", "Call mom", imported, "home")
    assert exists("tasks", "Call mom", imported, "work") == "work-call"
    assert exists("tasks", "Call mom", imported, "sap") == "sap-call"
    assert not exists("tasks", "Call mom", imported, "sap")  # not imported
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


def test_tags_visible_in_team_only(nt, nz):
    """Other teams' tags: not matched"""
    nt.records["/tags"] = [
        {"id": "t" * 16, "name": "home", "team_id": None},
        {"id": "u" * 16, "name": "work", "team_id": "team"},
        {"id": "v" * 16, "name": "gym", "team_id": "other"},
    ]
    nt.api.TagsApi().post_tag.return_value = NS(id=NEW)
    assert nz.tags([("home", None), ("work", None), ("gym", None)]) == {
        "home": "t" * 16,
        "work": "u" * 16,
        "gym": NEW,
    }


def test_project_group_refused_stops_before_project(nt, nz):
    nz.group_id = None
    nt.api.ProjectGroupsApi().post_project_group.side_effect = ApiException(status=400)
    with pytest.raises(ImportException, match="group"):
        nz.project("New")
    nt.api.ProjectsApi().post_project.assert_not_called()


@pytest.mark.parametrize("status, match", [(400, "group"), (503, "failed")])  # 503: import stopped
def test_project_outside_group_deleted(nt, nz, status, match):
    nz.team_id = "t" * 16
    nt.api.ProjectsApi().post_project.return_value = NS(id=NEW)
    nt.api.GroupAssignmentsApi().post_group_assignment.side_effect = ApiException(status=status)
    with pytest.raises(ImportException, match=match):
        nz.project("New")
    nt.api.ProjectsApi().delete_project_by_id.assert_called_once_with(NEW)


@pytest.mark.parametrize(
    "status, match", [(402, "Plan limit"), (401, "refused"), (403, "refused"), (503, "failed")]
)
def test_post_stops_on_errors_every_write_gets(nt, nz, status, match):
    nt.api.ProjectSectionsApi().post_project_section.side_effect = ApiException(status=status)
    with pytest.raises(ImportException, match=match):
        nz.section(PROJECT, "New", 1)


def test_post_record_refused_skipped(nt, nz):
    nt.api.ProjectSectionsApi().post_project_section.side_effect = ApiException(status=400)
    assert nz.section(PROJECT, "New", 1) is None


def test_post_reply_unreadable_is_created(nt, nz):
    """ValueError after send: record created, built id returned"""
    nt.api.ProjectSectionsApi().post_project_section.side_effect = ValueError
    section_id = nz.section(PROJECT, "New", 1)
    sent = nt.api.ProjectSectionsApi().post_project_section.call_args.args[0]
    assert section_id == sent.id


def test_single_tasks_imported_only_if_tagged(nt):
    """Imported Single Tasks: those tagged group_name; new one tagged"""
    nt.records = {
        "/team_members": [{"user_id": "user", "id": AUTHOR}],
        "/projects": [{"id": SAP, "is_single_actions": True}],
        "/tasks": [
            {"id": OLD, "name": "Call", "project_id": SAP},
            {"id": OTHER, "name": "Call", "project_id": SAP},
        ],
        "/tags": [{"id": TAG, "name": "Imported"}],
        "/tag_assignments": [{"tag_id": TAG, "task_id": OLD}],
    }
    nt.api.ProjectGroupsApi().get_project_groups.return_value = []
    nt.api.TasksApi().post_task.return_value = NS(id=NEW)
    nz = NozbeImport("user_key", "team", "Imported", with_single_tasks=True)
    assert nz.task(SAP, "Call") == (OLD, False)
    assert nz.task(SAP, "Call") == (NEW, True)
    posted = nt.api.TagAssignmentsApi().post_tag_assignment.call_args.args[0]
    assert (posted.tag_id, posted.task_id) == (TAG, NEW)
    nt.api.TagAssignmentsApi().post_tag_assignment.side_effect = ApiException(status=400)
    assert nz.task(SAP, "Text") == (None, False)  # untagged: re-run would duplicate
    nt.api.TasksApi().delete_task_by_id.assert_called_once_with(NEW)


def test_recurrence_put_keeps_task_flags(nt, nz):
    nt.api.TaskRecurrencesApi().post_task_recurrence.return_value = NS(id="r" * 16)
    nz.recurrence(PROJECT, OLD, "FREQ=DAILY", True, "daily")
    put = nt.api.TasksApi().put_task_by_id.call_args.args[1]
    assert put.to_dict() == {"id": OLD, "recurrence_id": "r" * 16, "is_all_day": True}


def test_recurrence_put_refused_deletes_recurrence(nt, nz):
    nt.api.TaskRecurrencesApi().post_task_recurrence.return_value = NS(id="r" * 16)
    nt.api.TasksApi().put_task_by_id.side_effect = ApiException(status=400)
    nz.recurrence(PROJECT, OLD, "FREQ=DAILY", True, "daily")
    nt.api.TaskRecurrencesApi().delete_task_recurrence_by_id.assert_called_once_with("r" * 16)
    assert nt.api.CommentsApi().post_comment.call_args.args[0].body == "daily"


def test_recurrence_put_reply_unreadable_no_fallback(nt, nz):
    nt.api.TaskRecurrencesApi().post_task_recurrence.return_value = NS(id="r" * 16)
    nt.api.TasksApi().put_task_by_id.side_effect = ValueError
    nz.recurrence(PROJECT, OLD, "FREQ=DAILY", True, "daily")
    nt.api.CommentsApi().post_comment.assert_not_called()


@pytest.mark.parametrize("pattern", [None, "FREQ=DAILY"])
def test_recurrence_fallback_comment(nt, nz, pattern):
    """Unparsed (None) or refused pattern: source text as comment"""
    nt.api.TaskRecurrencesApi().post_task_recurrence.side_effect = OpenApiException
    nz.recurrence(PROJECT, OLD, pattern, True, "Todoist: tous les lundis")
    assert nt.api.TaskRecurrencesApi().post_task_recurrence.called == bool(pattern)
    nt.api.TasksApi().put_task_by_id.assert_not_called()
    posted = nt.api.CommentsApi().post_comment.call_args.args[0]
    assert (posted.task_id, posted.body) == (OLD, "Todoist: tous les lundis")


@pytest.mark.parametrize("error", [OpenApiException, ValueError])
def test_time_zone_unreadable_user_is_utc(nt, nz, error):
    nt.api.UsersApi().get_user_by_id.side_effect = error
    assert nz.time_zone == "UTC"


@pytest.mark.parametrize(
    "group_id, has_projects, limit, groups, trial, outcome",
    [
        (None, True, 0, 0, True, "trial"),  # Free, first import
        (None, True, 0, 0, False, "refused"),  # Free, trial used
        (None, True, -1, 0, True, None),  # Premium
        (None, True, 2, 1, True, None),  # custom limit, room left
        (None, False, 0, 0, True, None),  # Single Tasks only: no group
        ("g" * 16, True, 0, 1, True, None),  # re-run: group exists
    ],
)
def test_check_group(nt, nz, monkeypatch, group_id, has_projects, limit, groups, trial, outcome):
    """Trial iff import group to create over project_groups limit; refused: ImportException"""
    nz.group_id = group_id
    nt.api.TeamsApi().get_team_by_id.return_value = NS(limits=f'{{"project_groups": {limit}}}')
    nt.records["/project_groups"] = [{"id": f"{n}" * 16} for n in range(groups)]
    monkeypatch.setattr(
        "ntimporters.nozbe.subscribe_trial", subscribe := MagicMock(return_value=trial)
    )
    if outcome == "refused":
        with pytest.raises(ImportException, match="LIMIT project_groups"):
            nz.check_group(has_projects)
    else:
        nz.check_group(has_projects)
    assert subscribe.called == (outcome is not None)


@pytest.mark.parametrize(
    "pattern, time_zone, expected",
    [
        ("FREQ=WEEKLY;UNTIL=20261231", "Europe/Warsaw", "FREQ=WEEKLY;UNTIL=20261231T225959Z"),
        ("FREQ=DAILY;UNTIL=20261231;COUNT=2", "UTC", "FREQ=DAILY;UNTIL=20261231T235959Z;COUNT=2"),
        ("FREQ=DAILY;UNTIL=20261231T120000Z", "UTC", "FREQ=DAILY;UNTIL=20261231T120000Z"),
        ("FREQ=DAILY", "UTC", "FREQ=DAILY"),
    ],
)
def test_utc_until(pattern, time_zone, expected):
    """Date UNTIL: end of that day in user's zone, UTC (backend DTSTART has TZID)"""
    assert utc_until(pattern, time_zone) == expected


def test_recurrence_import_stopped_deletes_recurrence(nt, nz):
    nt.api.TaskRecurrencesApi().post_task_recurrence.return_value = NS(id="r" * 16)
    nt.api.TasksApi().put_task_by_id.side_effect = ApiException(status=503)
    with pytest.raises(ImportException):
        nz.recurrence(PROJECT, OLD, "FREQ=DAILY", True, "daily")
    nt.api.TaskRecurrencesApi().delete_task_recurrence_by_id.assert_called_once_with("r" * 16)

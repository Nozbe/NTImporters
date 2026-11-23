"""Microsoft To Do -> Nozbe importer"""

import html
import itertools
import json
import re

from ntimporters.mstodo.mstodo_api import MSTodoClient
from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.utils import dig, parse_timestamp

SPEC = {
    "code": "mstodo",  # codename / ID of importer
    "name": "Microsoft To Do",  # name of application
    "url": "https://nozbe.help/advancedfeatures/importers/",
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}
IMPORT_NAME = "Imported from Microsoft To Do"
HIGH_IMPORTANCE = "high importance"
DAY_MS = 86_400_000
DAYS = {
    "monday": "MO",
    "tuesday": "TU",
    "wednesday": "WE",
    "thursday": "TH",
    "friday": "FR",
    "saturday": "SA",
    "sunday": "SU",
}
INDEX = {"first": 1, "second": 2, "third": 3, "fourth": 4, "last": -1}


# main method called by Nozbe app
def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Exception | str | None:
    """Perform import from Microsoft To Do to Nozbe"""
    return run_safely(
        lambda: _import_data(
            NozbeImport(nt_auth_token, team_id, IMPORT_NAME, with_single_tasks=True),
            MSTodoClient(auth_token),
        ),
        nt_auth_token=nt_auth_token,
        auth_token=auth_token,
    )


def _is_default(task_list: dict) -> bool:
    return task_list.get("wellknownListName") == "defaultList"


def _import_data(nz: NozbeImport, todo: MSTodoClient):
    """Import lists (projects; default "Tasks" list into Single Tasks, Outlook's flagged emails skipped)"""
    lists = [elt for elt in todo.lists() if elt.get("wellknownListName") != "flaggedEmails"]
    nz.check_open_projects(elt.get("displayName") for elt in lists if not _is_default(elt))
    for task_list in lists:
        _import_list(nz, todo, task_list)


def _import_list(nz: NozbeImport, todo: MSTodoClient, task_list: dict):
    """Import list with its tasks; categories and high importance as tags"""
    if _is_default(task_list):
        nt_project_id = nz.single_tasks_id
    else:
        nt_project_id = nz.project(task_list.get("displayName"))
    if not nt_project_id:
        return
    tasks = todo.tasks(task_list.get("id"))
    names = dict.fromkeys(itertools.chain.from_iterable(map(_labels, tasks)))
    tags = nz.tags((name, None) for name in names) if names else {}
    for position, task in enumerate(tasks):
        _import_task(nz, todo, task_list.get("id"), task, nt_project_id, position, tags)


def _labels(task: dict) -> list[str]:
    """Tag names of task: categories, HIGH_IMPORTANCE if high"""
    high = [HIGH_IMPORTANCE] if task.get("importance") == "high" else []
    return [*(task.get("categories") or []), *high]


def parse_due(due: dict | None) -> tuple[int | None, bool]:
    """dueDateTime -> (UTC midnight ms of its date, True); (None, False) if none.
    Graph gives due date's local midnight in UTC: rounded to nearest midnight."""
    if (moment := parse_timestamp(dig(due, "dateTime"))) is None:
        return None, False
    return (moment + DAY_MS // 2) // DAY_MS * DAY_MS, True


def _ended_at(task: dict) -> int | None:
    """Completion ms of completed task"""
    if task.get("status") != "completed":
        return None
    return parse_timestamp(dig(task, "completedDateTime.dateTime")) or parse_timestamp(
        task.get("lastModifiedDateTime")
    )


def to_rrule(recurrence: dict | None) -> str | None:
    """patternedRecurrence -> RRULE without DTSTART; None if unmappable"""
    pattern, span = dig(recurrence, "pattern", {}), dig(recurrence, "range", {})
    days = [DAYS.get(day) for day in pattern.get("daysOfWeek") or []]
    position = INDEX.get(pattern.get("index") or "first")
    month, day = pattern.get("month"), pattern.get("dayOfMonth")
    if not all(days) or position is None:
        return None
    by_day = f"BYDAY={','.join(days)}"
    match pattern.get("type"):
        case "daily":
            freq, rest = "DAILY", []
        case "weekly" if days:
            freq, rest = "WEEKLY", [by_day]
        case "absoluteMonthly" if day:
            freq, rest = "MONTHLY", [f"BYMONTHDAY={day}"]
        case "relativeMonthly" if days:
            freq, rest = "MONTHLY", [by_day, f"BYSETPOS={position}"]
        case "absoluteYearly" if day and month:
            freq, rest = "YEARLY", [f"BYMONTH={month}", f"BYMONTHDAY={day}"]
        case "relativeYearly" if days and month:
            freq, rest = "YEARLY", [f"BYMONTH={month}", by_day, f"BYSETPOS={position}"]
        case _:
            return None
    parts = [f"FREQ={freq}"]
    if (interval := pattern.get("interval") or 1) > 1:
        parts.append(f"INTERVAL={interval}")
        if freq == "WEEKLY" and (week_start := DAYS.get(pattern.get("firstDayOfWeek"))):
            parts.append(f"WKST={week_start}")
    parts += rest
    match span.get("type"):
        case "endDate" if end := span.get("endDate"):
            parts.append(f"UNTIL={end.replace('-', '')}")
        case "numbered" if (count := span.get("numberOfOccurrences") or 0) > 0:
            parts.append(f"COUNT={count}")
        case "endDate" | "numbered":
            return None
    return ";".join(parts)


def _import_task(
    nz: NozbeImport,
    todo: MSTodoClient,
    list_id: str,
    task: dict,
    nt_project_id: str,
    position: int,
    tags: dict[str, str],
):
    """Import task with tags, recurrence and comments"""
    due_at, is_all_day = parse_due(task.get("dueDateTime"))
    nt_task_id, is_new = nz.task(
        nt_project_id,
        task.get("title"),
        position=position,
        due_at=due_at,
        is_all_day=is_all_day,
        ended_at=_ended_at(task),
    )
    if not nt_task_id:
        return
    nz.assign_tags(nt_task_id, map(tags.get, _labels(task)), is_new)
    if is_new and due_at is not None and (recurrence := task.get("recurrence")):
        _import_recurrence(nz, nt_project_id, nt_task_id, recurrence)
    _import_comments(nz, todo, list_id, nt_task_id, task)


def _import_recurrence(nz: NozbeImport, nt_project_id: str, nt_task_id: str, recurrence: dict):
    """Set task recurrence; unmapped one goes to a comment"""
    nz.recurrence(
        nt_project_id,
        nt_task_id,
        to_rrule(recurrence),
        True,
        f"Microsoft To Do recurrence: {json.dumps(recurrence.get('pattern'))}",
    )


def _text(body: dict | None) -> str:
    """itemBody content as plain text"""
    content = dig(body, "content", "").replace("\r\n", "\n").replace("\r", "\n")
    if dig(body, "contentType") == "html":
        content = re.sub(r"(?is)<(head|style|script)\b.*?</\1>", "", content)
        content = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", content)
        content = html.unescape(re.sub(r"<[^>]+>", "", content))
        content = re.sub(r"\n\s*\n+", "\n\n", content)
    return content.strip()


def _import_comments(
    nz: NozbeImport, todo: MSTodoClient, list_id: str, nt_task_id: str, task: dict
):
    """Body, checklist, linked resources and file attachments of task"""
    task_id = task.get("id")
    if body := _text(task.get("body")):
        nz.comment(nt_task_id, body)
    if items := todo.checklist_items(list_id, task_id):
        nz.comment(
            nt_task_id,
            "\n".join(
                f"- [{'x' if item.get('isChecked') else ' '}] {item.get('displayName')}"
                for item in items
            ),
        )
    for resource in todo.linked_resources(list_id, task_id):
        nz.attachment(
            nt_task_id,
            resource.get("displayName") or resource.get("applicationName") or "link",
            resource.get("webUrl"),
            is_file=False,
        )
    if task.get("hasAttachments"):
        for attachment in todo.attachments(list_id, task_id):
            nz.attachment(
                nt_task_id,
                attachment.get("name") or "attachment",
                todo.attachment_url(list_id, task_id, attachment.get("id")),
                is_file=True,
                headers=todo.headers,
            )

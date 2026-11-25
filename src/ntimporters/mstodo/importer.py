"""Microsoft To Do -> Nozbe importer"""

import calendar
import itertools
import json
import re
from datetime import date, datetime, timedelta

from markdownify import markdownify

from ntimporters.mstodo.mstodo_api import MSTodoClient
from ntimporters.nozbe import NozbeImport, run_safely
from ntimporters.utils import checklist, dig, parse_timestamp, zone

SPEC = {
    "code": "mstodo",
    "name": "Microsoft To Do",
    "url": "https://nozbe.help/advancedfeatures/importers/#todo",
    "input_fields": ("nt_auth_token", "auth_token", "team_id"),
}
IMPORT_NAME = "Imported from Microsoft To Do"
HIGH_IMPORTANCE = "high importance"
DAYS = {day.name.lower(): day.name[:2] for day in calendar.Day}  # Graph name -> RRULE: monday -> MO
INDEX = {"first": 1, "second": 2, "third": 3, "fourth": 4, "last": -1}


def run_import(nt_auth_token: str, auth_token: str, team_id: str) -> Exception | str | None:
    """Nozbe app entry point"""
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
    """lists -> projects; default list -> Single Tasks; flagged emails skipped"""
    lists = [elt for elt in todo.lists() if elt.get("wellknownListName") != "flaggedEmails"]
    nz.check_group(not all(map(_is_default, lists)))
    for task_list in lists:
        _import_list(nz, todo, task_list)


def _import_list(nz: NozbeImport, todo: MSTodoClient, task_list: dict):
    """list -> project + tasks; categories, high importance -> tags"""
    if _is_default(task_list):
        nt_project_id = nz.single_tasks_id
    else:
        nt_project_id = nz.project(task_list.get("displayName"))
    if not nt_project_id:
        return
    tasks = todo.tasks(task_list.get("id"))
    tags = nz.tags((name, None) for name in itertools.chain.from_iterable(map(_labels, tasks)))
    for position, task in enumerate(tasks):
        _import_task(nz, todo, task_list.get("id"), task, nt_project_id, position, tags)


def _labels(task: dict) -> list[str]:
    """categories + HIGH_IMPORTANCE if high"""
    high = [HIGH_IMPORTANCE] if task.get("importance") == "high" else []
    return [*(task.get("categories") or []), *high]


def parse_due(due: dict | None, time_zone: str = "UTC") -> date | None:
    """dueDateTime (UTC via Prefer) -> date: nearest midnight in time_zone. Graph: local
    midnight (app-set): exact; UTC midnight (API-set): exact for |offset| < 12 h"""
    if (moment := parse_timestamp(dig(due, "dateTime"))) is None:
        return None
    return (datetime.fromtimestamp(moment / 1000, zone(time_zone)) + timedelta(hours=12)).date()


def _remind_at(task: dict) -> int | None:
    """reminder ms; None unless on and task open"""
    if task.get("isReminderOn") and task.get("status") != "completed":
        return parse_timestamp(dig(task, "reminderDateTime.dateTime"))
    return None


def _ended_at(task: dict) -> int | None:
    """completion ms (else lastModified); None unless completed"""
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
    """task -> Nozbe task + tags, recurrence, comments"""
    recurrence = task.get("recurrence")
    nt_task_id, is_new = nz.task(
        nt_project_id,
        task.get("title"),
        position=position,
        due=parse_due(task.get("dueDateTime"), nz.time_zone),
        ended_at=_ended_at(task),
        remind_at=_remind_at(task),
        recurrence=(
            to_rrule(recurrence),
            f"Microsoft To Do recurrence: {json.dumps(recurrence.get('pattern'))}",
        )
        if recurrence
        else None,
    )
    if not nt_task_id:
        return
    nz.assign_tags(nt_task_id, map(tags.get, _labels(task)), is_new)
    _import_comments(nz, todo, list_id, nt_task_id, task)


def _text(body: dict | None) -> str:
    """itemBody -> text; html -> markdown (links, lists kept)"""
    content = dig(body, "content", "").replace("\r\n", "\n").replace("\r", "\n")
    if dig(body, "contentType") == "html":
        content = re.sub(r"(?is)<(head|style|script)\b.*?</\1>", "", content)
        content = markdownify(content, heading_style="ATX", bullets="-")
        content = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+\n", "\n", content))
    return content.strip()


def _import_comments(
    nz: NozbeImport, todo: MSTodoClient, list_id: str, nt_task_id: str, task: dict
):
    """body, checklist, linked resources, file attachments -> task"""
    task_id = task.get("id")
    if body := _text(task.get("body")):
        nz.comment(nt_task_id, body)
    if items := task.get("checklistItems"):
        nz.comment(
            nt_task_id,
            checklist((item.get("displayName"), bool(item.get("isChecked"))) for item in items),
        )
    for resource in task.get("linkedResources") or []:
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
                attachment.get("name"),
                todo.attachment_url(list_id, task_id, attachment.get("id")),
                is_file=True,
                headers=todo.headers,
            )

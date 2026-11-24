"""Common helper functions"""

import logging
import random
import string
from collections.abc import Iterable
from datetime import UTC
from os import getenv

import requests
from dateutil.parser import isoparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import openapi_client as nt
from openapi_client import Color

log = logging.getLogger("ntimporters")

HOST = "api4"
if getenv("DEV_ACCESS_TOKEN"):
    HOST = f"dev{HOST}"
API_HOST = getenv("CUSTOM_API_HOST") or f"https://{HOST}.nozbe.com/v1/api"

MAX_RETRY_AFTER = 300  # s


class CappedRetry(Retry):
    """Retry honouring Retry-After up to MAX_RETRY_AFTER seconds"""

    def get_retry_after(self, response):
        after = super().get_retry_after(response)
        return None if after is None else min(after, MAX_RETRY_AFTER)


def session(headers: dict, statuses=(429, 500, 502, 503, 504)) -> requests.Session:
    """Session sending headers; statuses and connection errors retried up to 10 times,
    waiting Retry-After (<= MAX_RETRY_AFTER) if sent, else backoff (0, 2, 4, ... 60 s).
    Any method retried: for read-only clients only."""
    sess = requests.Session()
    sess.headers.update(headers)
    retry = CappedRetry(
        total=10,
        status_forcelist=statuses,
        allowed_methods=None,
        backoff_factor=1,
        backoff_max=60,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    return sess


def nt_api_client(nt_auth_token: str) -> nt.ApiClient:
    """NT API client: current API version, dev token, 429 retried every 10 s up to 36 times;
    read errors not retried (request may have been processed: POST would duplicate)"""
    configuration = nt.Configuration(
        host=API_HOST,
        api_key={"ApiKeyAuth": nt_auth_token},
        username=nt_auth_token.split("_")[0],
    )
    configuration.retries = Retry(
        total=36,
        read=0,
        other=0,
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


def checklist(items: Iterable[tuple[str | None, bool]]) -> str:
    """(name, done) pairs -> markdown task list"""
    return "\n".join(f"- [{'x' if done else ' '}] {name}" for name, done in items)


def subscribe_trial(api_key: str, nt_team_id: str) -> bool:
    """Return True if trial has been subscribed"""
    resp = requests.patch(
        "/".join((API_HOST.removesuffix("/api"), "teams", nt_team_id, "plan")),
        json={"members_len": 1, "plan_type": "trial", "is_recurring": False, "creds": 0},
        headers={"Authorization": f"Apikey {api_key}", "API-Version": "current"},
        timeout=60,
    )
    return resp.status_code == 200


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

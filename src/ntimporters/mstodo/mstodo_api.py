"""Microsoft Graph To Do client (read-only, delegated token with Tasks.Read)"""

from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ntimporters.utils import ImportException


class MSTodoClient:
    """Microsoft To Do lists, tasks and their details via Graph v1.0"""

    api_path = "https://graph.microsoft.com/v1.0/me/todo"

    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.mount(
            "https://",
            HTTPAdapter(
                max_retries=Retry(
                    total=10,
                    status_forcelist=[429, 503, 504],
                    allowed_methods=None,
                    backoff_factor=2,
                    backoff_max=60,
                    respect_retry_after_header=True,
                    raise_on_status=False,
                )
            ),
        )

    def _get_all(self, path: str, **params) -> list[dict]:
        """All records of collection at path, @odata.nextLink pages followed"""
        records, url = [], f"{self.api_path}/{path}"
        while url:
            response = self.session.get(url, params=params, timeout=60)
            if response.status_code == 401:
                raise ImportException(
                    "Microsoft To Do token invalid or expired: generate a new one in Graph Explorer"
                )
            if not response.ok:
                raise ImportException(
                    f"Connection to Microsoft To Do failed ({response.status_code})"
                )
            page = response.json()
            records += page.get("value") or []
            url, params = page.get("@odata.nextLink"), None  # nextLink carries the query
        return records

    @staticmethod
    def _task_path(list_id: str, task_id: str) -> str:
        return f"lists/{quote(list_id, safe='')}/tasks/{quote(task_id, safe='')}"

    def lists(self) -> list[dict]:
        """Task lists"""
        return self._get_all("lists")

    def tasks(self, list_id: str) -> list[dict]:
        """Tasks of list"""
        return self._get_all(f"lists/{quote(list_id, safe='')}/tasks")

    def checklist_items(self, list_id: str, task_id: str) -> list[dict]:
        """Checklist items (steps) of task"""
        return self._get_all(f"{self._task_path(list_id, task_id)}/checklistItems")

    def linked_resources(self, list_id: str, task_id: str) -> list[dict]:
        """Linked resources of task"""
        return self._get_all(f"{self._task_path(list_id, task_id)}/linkedResources")

    def attachments(self, list_id: str, task_id: str) -> list[dict]:
        """File attachments of task, without content"""
        return self._get_all(
            f"{self._task_path(list_id, task_id)}/attachments", **{"$select": "id,name"}
        )

    def attachment_url(self, list_id: str, task_id: str, attachment_id: str) -> str:
        """Raw content URL of attachment; GET needs self.headers"""
        return (
            f"{self.api_path}/{self._task_path(list_id, task_id)}"
            f"/attachments/{quote(attachment_id, safe='')}/$value"
        )

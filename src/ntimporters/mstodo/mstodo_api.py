"""Graph To Do client; read-only, delegated token, Tasks.Read"""

from urllib.parse import quote

from ntimporters.utils import ImportException, session


class MSTodoClient:
    """To Do via Graph v1.0"""

    api_path = "https://graph.microsoft.com/v1.0/me/todo"

    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session = session(self.headers | {"Prefer": 'outlook.timezone="UTC"'})

    def _get_all(self, path: str, **params) -> list[dict]:
        """all records at path; follows @odata.nextLink"""
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
        return self._get_all("lists")

    def tasks(self, list_id: str) -> list[dict]:
        """tasks + checklistItems, linkedResources (key absent if none)"""
        return self._get_all(
            f"lists/{quote(list_id, safe='')}/tasks",
            **{"$expand": "checklistItems,linkedResources"},
        )

    def attachments(self, list_id: str, task_id: str) -> list[dict]:
        """file attachments, no content"""
        return self._get_all(
            f"{self._task_path(list_id, task_id)}/attachments", **{"$select": "id,name"}
        )

    def attachment_url(self, list_id: str, task_id: str, attachment_id: str) -> str:
        """raw content URL; GET needs self.headers"""
        return (
            f"{self.api_path}/{self._task_path(list_id, task_id)}"
            f"/attachments/{quote(attachment_id, safe='')}/$value"
        )

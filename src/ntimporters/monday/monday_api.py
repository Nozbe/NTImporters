""" Monday API client module """
import json

import requests
from ntimporters.utils import parse_timestamp


class MondayClient:
    """Client to connect to Monday API"""

    api_path = "https://api.monday.com/v2"
    limit = 300

    def __init__(self, app_key):
        self.headers = {"Authorization": app_key}

    def _req(self, query) -> dict:
        if resp := requests.get(
            self.api_path, json={"query": f"{{ {query} }}"}, headers=self.headers
        ):
            return resp.json()

        return {}

    def user(self) -> dict:
        """Get Monday's user email"""
        return self._req("me{email}").get("data", {}).get("me", {})

    def projects(self) -> list[dict]:
        """Get Monday boards (NT projects)"""
        return (
            self._req(
                f"boards(state:all limit:{self.limit}){{name,id,state,description,board_kind}}"
            )
            .get("data", {})
            .get("boards", [])
        )

    def sections(self, project_id: str) -> list:
        """Get Monday groups (NT project sections)"""

        query = (
            f"boards (state:all ids: {project_id}) {{ groups {{ id title archived position }} }}"
        )

        return self._req(query).get("data", {}).get("boards", [{}])[0].get("groups", [])

    @staticmethod
    def _convert_columns(task):
        due_at, counter = None, 0
        for column in task.get("column_values"):
            if column.get("type") == "date" and column.get("text"):
                if (counter := counter + 1) > 1:
                    break
                try:
                    task["is_all_day"] = len(column.get("text", "")) == 10
                    due_at = parse_timestamp(column.get("text"))
                except (json.decoder.JSONDecodeError, ValueError):
                    pass
        return task, counter, due_at

    def tasks(self, project_id: str) -> list:
        """Get Monday items (NT tasks)"""
        query = f"""boards(state:all limit:{self.limit} ids:{project_id})
        {{ items(newest_first:false) {{ id group {{id}} name column_values {{ type value text title }} }}
        }}"""
        # ASSUMPTION: if only one date-type column then it is due_at
        tasks = []
        delta = 0
        for i, task in enumerate(
            self._req(query).get("data", {}).get("boards", [{}])[0].get("items", [])
        ):
            task["is_all_day"] = False
            task, counter, due_at = self._convert_columns(task)
            task.pop("column_values", None)
            tasks.append(
                task
                | {
                    "due_at": due_at if counter == 1 else None,
                    "group": task.get("group", {}).get("id"),
                    "position": i + delta + 1,
                }
            )
            subitems = self.subitems(task.get("id"), i + delta + 1)
            delta += len(subitems)
            tasks.extend(subitems)
        return reversed(tasks)

    def subitems(self, item_id: str, delta) -> list:
        """Get Monday subitems (NT tasks)"""
        query = f"""items(ids:{item_id} limit:1)
            {{ group {{id position}}
                subitems{{ name column_values {{ value type text title }} }} }}
        """
        # ASSUMPTION: if only one date-type column then it is due_at
        tasks = []
        resp = self._req(query).get("data", {}).get("items", [])
        for item in resp:
            group_id = item.get("group", {}).get("id")
            for i, task in enumerate(item.get("subitems", []) or []):
                task["is_all_day"] = False
                task, counter, due_at = self._convert_columns(task)
                task.pop("column_values", None)
                tasks.append(
                    task
                    | {
                        "due_at": due_at if counter == 1 else None,
                        "group": group_id,
                        "position": 1 + i + delta,
                    }
                )
        return tasks

    def comments(self, task_id: str) -> dict:
        """Get Monday updates (task's comments)"""
        query = f"""items (ids: {task_id}) {{
        updates(limit:{self.limit}) {{created_at, body, text_body, id,
        replies{{created_at, text_body}}, creator_id}}}}
        """
        resp = self._req(query).get("data", {}).get("items", [{}])[0].get("updates", [])
        comments = []
        for comment in reversed(resp):
            replies = comment.pop("replies", None) or []
            comments.append(comment)
            for reply in replies:
                comments.append(reply)
        return comments

    def users(self) -> dict:
        """Get Monday users"""
        return {
            str(elt.get("id")): str(elt.get("email"))
            for elt in self._req("users {id email}").get("data", {}).get("users", [])
        }

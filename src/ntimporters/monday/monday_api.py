""" Monday API client module """
import json
from datetime import datetime

import requests


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
        query = f"boards (state:all ids: {project_id}) {{ groups {{ id title archived }} }}"
        return self._req(query).get("data", {}).get("boards", [{}])[0].get("groups", [])

    def tasks(self, project_id: str) -> list:
        """Get Monday items (NT tasks)"""
        query = f"""boards(state:all limit:{self.limit} ids:{project_id})
        {{
        items {{ state id group {{id}} name column_values {{ type value text title }} }}
        }}"""
        # ASSUMPTION: if only one date-type column then it is due_at
        tasks = []
        for task in self._req(query).get("data", {}).get("boards", [{}])[0].get("items", []):
            counter, due_at = 0, None
            for column in task.get("column_values"):
                if column.get("type") == "date" and column.get("value"):
                    if (counter := counter + 1) > 1:
                        break
                    try:
                        dtime = json.loads(column.get("value", "{}"))
                        due_at = int(
                            datetime.strptime(
                                f"{dtime.get('date')} {dtime.get('time')}", "%Y-%m-%d %H:%M:%S"
                            ).timestamp()
                            * 1000
                        )
                    except (ValueError, json.decoder.JSONDecodeError):
                        pass
            task.pop("column_values", None)
            tasks.append(
                task
                | {
                    "due_at": due_at if counter == 1 else None,
                    "group": task.get("group", {}).get("id"),
                }
            )
        return tasks

    def comments(self, task_id: str) -> dict:
        """Get Monday updates (task's comments)"""
        query = f"""items (ids: {task_id}) {{
        updates(limit:{self.limit}) {{created_at, text_body, id, creator_id}}}}
        """
        return self._req(query).get("data", {}).get("items", [{}])[0].get("updates", [])

    def users(self) -> dict:
        """Get Monday users"""
        return {
            str(elt.get("id")): str(elt.get("email"))
            for elt in self._req("users {id email}").get("data", {}).get("users", [])
        }

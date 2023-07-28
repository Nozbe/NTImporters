""" Simple trello REST API client """
import datetime
import functools

import requests
from ntimporters.utils import ImportException

# board -> project
# list ->  section
# card -> task
# comment -> comment
# checklist -> comment


class TrelloClient:
    """Simple trello REST API client"""

    api_path = "https://api.trello.com/1"

    def __init__(self, app_key, token):
        self.headers = {
            "Authorization": f'OAuth oauth_consumer_key="{app_key}", oauth_token="{token}"'
        }
        print(self.headers)
        user_data = self.user()
        self.author_email = str(user_data.get("email"))
        self.boards_ids = user_data.get("idBoards", [])

    def _req(self, suffix, data=None) -> dict:
        if resp := requests.get(
            f"{self.api_path}/{suffix}", data=data or {"limit": 1000}, headers=self.headers
        ):
            return resp.json()
        else:
            print(resp.body, str(resp.content), data)
            raise ImportException(
                f"Connection to trello failed ({resp.status_code}). Wrong credentials?"
            )
        return {}

    def user(self) -> dict:
        """Get user details"""
        return self._req("members/me")

    def project_stars(self, project_id: str) -> bool:
        """Get project stars"""
        return bool(self._req(f"boards/{project_id}/boardStars"))

    def projects(self) -> dict:
        """Get projects"""
        return [
            self._req(f"boards/{board_id}") | {"is_fav": self.project_stars(board_id)}
            for board_id in self.boards_ids
        ]

    def sections(self, project_id: str) -> dict:
        """Get project sections"""
        return self._req(f"boards/{project_id}/lists")

    def tags(self, project_id: str) -> dict:
        """Get tags related with board"""
        return [elt for elt in self._req(f"boards/{project_id}/labels")]

    def tasks(self, section_id: str) -> dict:
        """Get section tasks"""
        return self._req(f"lists/{section_id}/cards")

    def attachments(self, task_id: str) -> dict:
        """Get task attachments"""
        return self._req(f"cards/{task_id}/attachments")

    @functools.cache
    def member(self, member_id: str) -> dict:
        """Get member by id"""
        return self._req(f"members/{member_id}")

    def members_emails(self) -> dict:
        """Return all emails related with boards"""
        members_emails = {}
        for board_id in self.boards_ids:
            for member in self._req(f"boards/{board_id}/members"):
                if (email := self.member(member.get("id")).get("email")) != self.user().get(
                    "email"
                ):
                    members_emails[member.get("id")] = email

        return members_emails

    def attachment(self, attachment_url: str):
        """Get attachment body"""
        if resp := requests.get(attachment_url, stream=True, headers=self.headers):
            if resp and hasattr(resp, "raw"):
                return resp.raw
        return b""

    def checklists(self, task_id: str) -> dict:
        """Get checklists as comments"""
        return self._parse_checklists(self._req(f"cards/{task_id}/checklists"))

    def comments(self, task_id: str) -> dict:
        """Get comments"""
        comments = []
        if resp := self._req(f"cards/{task_id}/actions"):
            for element in resp:
                edata = element.get("data")
                if edata.get("card", {}).get("id") == task_id:
                    comments.append(
                        {
                            "text": edata.get("text"),
                            "date": element.get("date"),
                            "author_email": str(
                                self.member(element.get("idMemberCreator")).get("email")
                                or self.author_email
                            ),
                        }
                    )
        return comments + self.checklists(task_id)

    def _parse_checklists(self, checklists: list) -> list[dict]:
        """Convert checklists into list of NT comments"""
        parsed = []
        for checklist in checklists:
            comment_body = []
            for item in checklist.get("checkItems"):
                checked = "- [ ]" if item.get("state") == "incomplete" else "- [x]"
                comment_body.append(f"{checked} {item.get('name')}")
            parsed.append(
                {
                    "author_email": str(self.author_email),
                    "text": "\n".join(comment_body),
                    "date": datetime.datetime.now().isoformat(),
                }
            )
        return parsed

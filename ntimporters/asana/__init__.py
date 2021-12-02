"""Asana -> Nozbe Teams importer"""

from itertools import chain
from typing import Optional

import asana
from asana.error import AsanaError

import openapi_client as nt
from openapi_client.exceptions import OpenApiException

SPEC = {
    "code": "asana",
    "name": "Asana",
    "url": "",
}


def run_import(nt_auth_token: str, auth_token: str) -> Optional[str]:
    """Perform import from Asana to Nozbe Teams"""
    if not nt_auth_token:
        return "Missing 'nt_auth_token'"
    if not auth_token:
        return "Missing 'auth_token'"

    nt_client = nt.ApiClient(configuration=nt.Configuration(
        host="https://api4.nozbe.com/v1/api",
        api_key={"ApiKeyAuth": nt_auth_token},
        access_token=nt_auth_token,
    ))
    asana_client = asana.Client.access_token(auth_token)
    try:
        _import_data(nt_client, asana_client)
    except (AsanaError, OpenApiException) as exc:
        return str(exc)


def _import_data(nt_client: nt.ApiClient, asana_client: asana.Client):
    """Import everything from Asana to Nozbe Teams"""
    me = asana_client.users.me()
    print(me)
    for workspace in asana_client.workspaces.find_all(full_payload=True):
        print(workspace)
        # users = asana_client.users.find_all({"workspace": workspace["gid"]})
        # print(users)
        for tag in asana_client.tags.find_by_workspace(workspace["gid"]):
            print(tag)
        for project in asana_client.projects.find_by_workspace(workspace["gid"]):
            print(project)
            for section in asana_client.sections.find_by_project(project["gid"]):
                print(section)
            for task in chain(
                asana_client.tasks.find_by_project(project["gid"]),
                asana_client.tasks.find_all({"workspace": workspace["gid"], "assignee": me["gid"]}),
            ):
                print(task)
                for story in asana_client.stories.find_by_task(task["gid"]):
                    print(story)
                for attachment in asana_client.attachments.find_by_task(task["gid"]):
                    print(attachment)

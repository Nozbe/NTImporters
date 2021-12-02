"""Asana -> Nozbe Teams importer"""

from typing import Optional
from openapi_client import ApiClient, Configuration, apis, models

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

    nt_client = ApiClient(configuration=Configuration(
        host="api4.nozbe.com",
        api_key=nt_auth_token,
    ))

    return None

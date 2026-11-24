from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
import requests
import urllib3


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach a real server (default API host is production)"""

    def refuse(*args, **kwargs):
        raise RuntimeError(f"network call in test: {args[1:3]}")

    monkeypatch.setattr(requests.Session, "request", refuse)
    monkeypatch.setattr(urllib3.PoolManager, "urlopen", refuse)


@pytest.fixture
def nt(monkeypatch):
    """Fake Nozbe API in ntimporters.nozbe.
    nt.api: MagicMock for openapi_client.api, e.g. nt.api.TasksApi().post_task.
    nt.records: path -> records; fetch_all serves those matching filters on fields they have
    ('fields' ignored). nt.fetch_all: its MagicMock."""
    fake = NS(api=MagicMock(), records={})

    def fetch_all(_client, path, **filters):
        filters.pop("fields", None)
        return [
            elt
            for elt in fake.records.get(path, [])
            if all(elt.get(key, value) == value for key, value in filters.items())
        ]

    fake.fetch_all = MagicMock(side_effect=fetch_all)
    monkeypatch.setattr("ntimporters.nozbe.api", fake.api)
    monkeypatch.setattr("ntimporters.nozbe.fetch_all", fake.fetch_all)
    return fake

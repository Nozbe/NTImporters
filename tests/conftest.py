from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def nt(monkeypatch):
    """Fake Nozbe API in ntimporters.nozbe and ntimporters.utils.
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
    for module in ("ntimporters.nozbe", "ntimporters.utils"):
        monkeypatch.setattr(f"{module}.api", fake.api)
        monkeypatch.setattr(f"{module}.fetch_all", fake.fetch_all)
    return fake

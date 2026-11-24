from ntimporters.utils import dig, nt_api_client, parse_timestamp


def test_parse_timestamp_utc():
    """Date-only and naive values are UTC, aware ones kept"""
    assert parse_timestamp("2026-11-26") == 1795651200000
    assert parse_timestamp("2026-11-24T14:30:00") == parse_timestamp("2026-11-24T15:30:00+01:00")
    assert parse_timestamp(None) is None


def test_nt_api_client(monkeypatch):
    """Api-Version, dev token headers and 429 retries set outside generated code"""
    monkeypatch.setenv("DEV_ACCESS_TOKEN", "dev")
    client = nt_api_client("user_key")
    assert client.default_headers.get("Api-Version") == "current"
    assert client.default_headers.get("X-DevToken") == "dev"
    assert client.configuration.username == "user"
    assert 429 in client.configuration.retries.status_forcelist


def test_dig():
    """Dotted path through dicts and list indices; default on miss or None"""
    data = {"a": [{"b": 1}, {"b": None}]}
    assert dig(data, "a.0.b") == 1
    assert dig(data, "a.1.b", 0) == 0
    assert dig(data, "a.5.b") is None
    assert dig(data, "a.x") is None

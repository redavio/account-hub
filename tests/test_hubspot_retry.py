"""HubSpot reads retry a timed-out or dropped connection instead of failing the whole run."""
import urllib.error

import pytest

from accounthub import hubspot


class Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": true}'


def test_a_timeout_is_retried(monkeypatch):
    calls = []

    def urlopen(req, context=None, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("The read operation timed out")
        return Resp()
    monkeypatch.setattr(hubspot.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(hubspot.time, "sleep", lambda s: None)
    assert hubspot.HubSpot("t").call("GET", "/x") == {"ok": True}
    assert len(calls) == 3


def test_it_gives_up_with_a_plain_reason(monkeypatch):
    def urlopen(req, context=None, timeout=None):
        raise urllib.error.URLError("connection reset")
    monkeypatch.setattr(hubspot.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(hubspot.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="HubSpot GET /x"):
        hubspot.HubSpot("t").call("GET", "/x")

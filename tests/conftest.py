"""Shared test setup.

Every test gets its own XDG_CACHE_HOME, so WebClient's persisted session file
(web/session.py) never touches the real ~/.cache and never leaks cookies from
one test into the next. The throttle's sleep is replaced by a recorder:
the suite stays fast, and tests that care can assert on the requested waits.
"""

from __future__ import annotations

import pytest

from fega_schmitt_client.web import session as session_module


@pytest.fixture(autouse=True)
def isolated_session_cache(tmp_path, monkeypatch):
    cache_home = tmp_path / "xdg-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    return cache_home / "fega-schmitt-client"


@pytest.fixture(autouse=True)
def recorded_sleeps(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(session_module, "_sleep", sleeps.append)
    return sleeps

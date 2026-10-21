"""Tests for the webshop throttle and the persisted session (web/session.py).

conftest.py already points XDG_CACHE_HOME at a per-test directory and replaces
the throttle's sleep with a recorder; tests here that need to reason about
time additionally install a fake clock that the recorded sleeps advance.
"""

from __future__ import annotations

import json
import stat

import httpx
import pytest
import respx
from web_fixtures import LOGIN_FAILURE_HEADERS, LOGIN_SUCCESS_HEADERS, SEARCH_RESULTS_HTML

from fega_schmitt_client.web import WebClient
from fega_schmitt_client.web import session as session_module
from fega_schmitt_client.web.client import DEFAULT_BASE_URL, DEFAULT_LOGIN_PATH, DEFAULT_SHOP_PATH
from fega_schmitt_client.web.session import SessionStore, default_session_dir

LOGIN_URL = f"{DEFAULT_BASE_URL}{DEFAULT_LOGIN_PATH}"
SHOP_URL = f"{DEFAULT_BASE_URL}{DEFAULT_SHOP_PATH}"

# Mirrors what the live shop sends: "sfs" several times with different paths
# (docs/extensions.md 2.2) - the case a cookie-file roundtrip once got wrong.
LOGIN_WITH_COOKIES = [
    ("Location", LOGIN_SUCCESS_HEADERS["Location"]),
    ("Set-Cookie", "sfs=abc; path=/scripts/"),
    ("Set-Cookie", "sfs=abc; path=/abtest/scripts/"),
    ("Set-Cookie", "sfs=abc; path=/product/"),
    ("Set-Cookie", "PHPSESSID=php1; path=/"),
    ("Set-Cookie", "cbold=b1; path=/"),
]


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch, recorded_sleeps):
    fake = FakeClock()
    monkeypatch.setattr(session_module, "_now", fake.time)

    def sleep(seconds: float) -> None:
        recorded_sleeps.append(seconds)
        fake.sleep(seconds)

    monkeypatch.setattr(session_module, "_sleep", sleep)
    return fake


def _mock_shop(login_headers=LOGIN_WITH_COOKIES):
    login = respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=login_headers))
    shop = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    return login, shop


# --- throttle ---


@respx.mock
def test_requests_are_spaced_by_the_default_interval(clock, recorded_sleeps):
    _mock_shop()
    client = WebClient(customer_number="9920", shop_password="geheim")

    client.search("121350")  # login + search
    client.search("121350")  # search only

    # First request goes out immediately, each following one waits the full 3 s.
    assert recorded_sleeps == [pytest.approx(3.0), pytest.approx(3.0)]


@respx.mock
def test_only_the_remaining_part_of_the_interval_is_waited(clock, recorded_sleeps):
    _mock_shop()
    client = WebClient(customer_number="9920", shop_password="geheim", min_request_interval=3.0)
    client.search("121350")
    recorded_sleeps.clear()

    clock.now += 2.0  # caller spent 2 s on something else
    client.search("121350")

    assert recorded_sleeps == [pytest.approx(1.0)]


@respx.mock
def test_no_wait_once_the_interval_has_passed(clock, recorded_sleeps):
    _mock_shop()
    client = WebClient(customer_number="9920", shop_password="geheim")
    client.search("121350")
    recorded_sleeps.clear()

    clock.now += 10.0
    client.search("121350")

    assert recorded_sleeps == []


@respx.mock
def test_zero_interval_disables_the_throttle(clock, recorded_sleeps):
    _mock_shop()
    client = WebClient(customer_number="9920", shop_password="geheim", min_request_interval=0)
    client.search("121350")
    client.search("121350")

    assert recorded_sleeps == []


def test_negative_interval_is_rejected():
    with pytest.raises(ValueError):
        WebClient(customer_number="9920", shop_password="geheim", min_request_interval=-1)


@respx.mock
def test_two_clients_sharing_the_cache_are_throttled_together(clock, recorded_sleeps):
    """Stands in for two consecutive CLI processes: the second one has to wait
    for the first one's last request, not just for its own."""
    _mock_shop()
    WebClient(customer_number="9920", shop_password="geheim").search("121350")
    recorded_sleeps.clear()

    WebClient(customer_number="9920", shop_password="geheim").search("121350")

    assert recorded_sleeps == [pytest.approx(3.0)]


def test_wait_is_capped_when_the_stored_time_lies_in_the_future(clock, recorded_sleeps, tmp_path):
    store = SessionStore(tmp_path / "s.json", min_interval=3.0)
    store.wait_turn()
    clock.now -= 3600  # wall clock jumped back an hour

    store.wait_turn()

    assert recorded_sleeps == [pytest.approx(3.0)]


# --- session reuse ---


@respx.mock
def test_second_client_reuses_the_saved_session_without_logging_in():
    login, shop = _mock_shop()
    WebClient(customer_number="9920", shop_password="geheim").search("121350")
    assert login.call_count == 1

    results = WebClient(customer_number="9920", shop_password="geheim").search("121350")

    assert login.call_count == 1
    assert len(results) == 1
    sent_cookies = shop.calls.last.request.headers["Cookie"]
    assert "sfs=abc" in sent_cookies
    assert "PHPSESSID=php1" in sent_cookies


@respx.mock
def test_all_same_named_cookies_with_different_paths_survive_the_roundtrip(isolated_session_cache):
    _mock_shop()
    WebClient(customer_number="9920", shop_password="geheim").search("121350")

    state = json.loads((isolated_session_cache / "web-session-9920.json").read_text())
    sfs_paths = sorted(c["path"] for c in state["cookies"] if c["name"] == "sfs")
    assert sfs_paths == ["/abtest/scripts/", "/product/", "/scripts/"]

    restored = httpx.Client()
    WebClient(customer_number="9920", shop_password="geheim", http_client=restored)
    assert sorted(c.path for c in restored.cookies.jar if c.name == "sfs") == sfs_paths


@respx.mock
def test_dead_saved_session_falls_back_to_a_fresh_login():
    login, _ = _mock_shop()
    WebClient(customer_number="9920", shop_password="geheim").search("121350")

    # Session died server-side in the meantime: first request bounces to the login page.
    respx.get(SHOP_URL).mock(
        side_effect=[
            httpx.Response(302, headers=LOGIN_FAILURE_HEADERS),
            httpx.Response(200, text=SEARCH_RESULTS_HTML),
        ]
    )
    results = WebClient(customer_number="9920", shop_password="geheim").search("121350")

    assert login.call_count == 2
    assert len(results) == 1


@respx.mock
def test_sessions_are_kept_apart_per_customer_number():
    login, _ = _mock_shop()
    WebClient(customer_number="9920", shop_password="geheim").search("121350")
    WebClient(customer_number="1234", shop_password="anders").search("121350")

    assert login.call_count == 2


@respx.mock
def test_expired_cookies_are_not_restored(isolated_session_cache):
    isolated_session_cache.mkdir(parents=True)
    (isolated_session_cache / "web-session-9920.json").write_text(
        json.dumps(
            {
                "version": 1,
                "cookies": [{"name": "sfs", "value": "old", "domain": "shop.fega.de", "path": "/", "expires": 1}],
            }
        )
    )
    login, _ = _mock_shop()

    WebClient(customer_number="9920", shop_password="geheim").search("121350")

    assert login.call_count == 1


@respx.mock
def test_damaged_state_file_is_ignored(isolated_session_cache):
    isolated_session_cache.mkdir(parents=True)
    (isolated_session_cache / "web-session-9920.json").write_text("{not json")
    login, _ = _mock_shop()

    results = WebClient(customer_number="9920", shop_password="geheim").search("121350")

    assert login.call_count == 1
    assert len(results) == 1


@respx.mock
def test_persist_session_false_writes_nothing_and_still_throttles(isolated_session_cache, clock, recorded_sleeps):
    login, _ = _mock_shop()
    WebClient(customer_number="9920", shop_password="geheim", persist_session=False).search("121350")
    WebClient(customer_number="9920", shop_password="geheim", persist_session=False).search("121350")

    assert not isolated_session_cache.exists()
    assert login.call_count == 2
    # Per object only: each client waits between its own login and search, not for the other one.
    assert recorded_sleeps == [pytest.approx(3.0), pytest.approx(3.0)]


@respx.mock
def test_explicit_session_dir_is_used(tmp_path, isolated_session_cache):
    _mock_shop()
    target = tmp_path / "elsewhere"
    WebClient(customer_number="9920", shop_password="geheim", session_dir=target).search("121350")

    assert (target / "web-session-9920.json").exists()
    assert not isolated_session_cache.exists()


# --- file safety ---


@respx.mock
def test_state_file_and_directory_are_private(isolated_session_cache):
    _mock_shop()
    WebClient(customer_number="9920", shop_password="geheim").search("121350")

    state_file = isolated_session_cache / "web-session-9920.json"
    assert stat.S_IMODE(isolated_session_cache.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600


@respx.mock
def test_password_is_never_written(isolated_session_cache):
    _mock_shop()
    WebClient(customer_number="9920", shop_password="sehr-geheim-42").search("121350")

    for path in isolated_session_cache.iterdir():
        assert "sehr-geheim-42" not in path.read_text()


def test_customer_number_cannot_escape_the_session_dir(tmp_path):
    store = SessionStore.for_customer("../../etc/x", tmp_path)
    assert store.path is not None
    assert store.path.parent == tmp_path


def test_default_session_dir_follows_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert default_session_dir() == tmp_path / "fega-schmitt-client"

    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert default_session_dir() == tmp_path / "home" / ".cache" / "fega-schmitt-client"


def test_clear_forgets_cookies_but_keeps_the_throttle(clock, recorded_sleeps, tmp_path):
    store = SessionStore(tmp_path / "s.json", min_interval=3.0)
    jar = httpx.Cookies()
    jar.set("sfs", "abc", domain="shop.fega.de", path="/")
    store.save_cookies(jar.jar)
    store.wait_turn()

    store.clear()

    assert store.load_cookies(httpx.Cookies().jar) is False
    store.wait_turn()
    assert recorded_sleeps == [pytest.approx(3.0)]

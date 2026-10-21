"""Persistent webshop session state: cookies and a cross-process request throttle.

One JSON file per customer number under ``$XDG_CACHE_HOME/fega-schmitt-client``
(``~/.cache/fega-schmitt-client`` by default) holds the shop's session cookies
and the wall-clock time of the last request. Every WebClient - in this process
or another one, e.g. consecutive ``fega web`` CLI calls - that points at the
same file waits its turn so that at most one request per ``min_interval``
seconds reaches the shop, and reuses the cookies instead of logging in again.

Cookies are stored as explicit (name, value, domain, path, expires) records,
not as a Netscape/Mozilla cookie file: the shop sets ``sfs`` five times with
different paths, and a cookie-file roundtrip through ``http.cookiejar`` was
seen to silently drop it (docs/extensions.md, section 4). The record format was
verified live on 2026-10-21: a session saved by one process and restored in a
fresh one was accepted by the shop without a new login, while the same request
without cookies was redirected to the login page.

The file is as good as a login for as long as the session lives, hence mode
0600 inside a 0700 directory. The shop password is never written.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from collections.abc import Iterator
from http.cookiejar import Cookie, CookieJar
from pathlib import Path

try:  # POSIX only - on Windows the throttle still works per process, just without a cross-process lock.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on Windows
    fcntl = None  # type: ignore[assignment]

DEFAULT_MIN_REQUEST_INTERVAL = 3.0

# Module-level indirection so tests can swap the clock and the sleep for this
# module alone instead of patching the global time module.
_now = time.time
_sleep = time.sleep

_STATE_VERSION = 1


def default_session_dir() -> Path:
    """``$XDG_CACHE_HOME/fega-schmitt-client``, falling back to ``~/.cache``."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "fega-schmitt-client"


class SessionStore:
    """Cookies + last-request timestamp, shared through a file if ``path`` is
    set, otherwise kept in memory for this one object only."""

    def __init__(self, path: Path | None, *, min_interval: float = DEFAULT_MIN_REQUEST_INTERVAL) -> None:
        if min_interval < 0:
            raise ValueError("min_interval darf nicht negativ sein")
        self._path = path
        self._lock_path = path.with_suffix(".lock") if path else None
        self._min_interval = min_interval
        self._memory_last_request_at: float | None = None

    @classmethod
    def for_customer(
        cls,
        customer_number: str,
        session_dir: Path | None,
        *,
        min_interval: float = DEFAULT_MIN_REQUEST_INTERVAL,
    ) -> SessionStore:
        if session_dir is None:
            return cls(None, min_interval=min_interval)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", customer_number)
        return cls(Path(session_dir) / f"web-session-{safe_name}.json", min_interval=min_interval)

    @property
    def path(self) -> Path | None:
        return self._path

    # --- throttle ---

    def wait_turn(self) -> None:
        """Block until ``min_interval`` has passed since the last request of
        anyone sharing this store, then claim the current moment as the new
        last request. The lock is held while sleeping on purpose: that is what
        queues concurrent processes behind each other."""
        with self._locked():
            state = self._read_state()
            last = state.get("last_request_at") if self._path else self._memory_last_request_at
            if isinstance(last, (int, float)):
                # min() caps the wait if the stored time lies in the future (clock jumped back).
                wait = min(self._min_interval, self._min_interval - (_now() - last))
                if wait > 0:
                    _sleep(wait)
            now = _now()
            if self._path:
                state["last_request_at"] = now
                self._write_state(state)
            else:
                self._memory_last_request_at = now

    # --- cookies ---

    def load_cookies(self, jar: CookieJar) -> bool:
        """Copy saved, unexpired cookies into ``jar``. Returns whether any were
        restored - the caller then treats itself as logged in and relies on
        the shop's "please log in again" redirect if the session has died."""
        if not self._path:
            return False
        with self._locked():
            records = self._read_state().get("cookies")
        if not isinstance(records, list):
            return False
        now = _now()
        restored = 0
        for record in records:
            try:
                expires = record.get("expires")
                if expires is not None and expires <= now:
                    continue
                jar.set_cookie(_make_cookie(record))
                restored += 1
            except (AttributeError, KeyError, TypeError):
                continue  # a damaged record is skipped, never fatal
        return restored > 0

    def save_cookies(self, jar: CookieJar) -> None:
        if not self._path:
            return
        records = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "secure": c.secure,
                "expires": c.expires,
            }
            for c in jar
        ]
        with self._locked():
            state = self._read_state()
            state["cookies"] = records
            self._write_state(state)

    def clear(self) -> None:
        """Forget the saved cookies (keeps the throttle timestamp)."""
        if not self._path:
            return
        with self._locked():
            state = self._read_state()
            state.pop("cookies", None)
            self._write_state(state)

    # --- file handling ---

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        if not self._lock_path:
            yield
            return
        self._ensure_dir()
        fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)  # closing the descriptor releases the flock

    def _ensure_dir(self) -> None:
        assert self._path is not None
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _read_state(self) -> dict:
        if not self._path:
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}  # missing or damaged file = no saved session
        if not isinstance(data, dict) or data.get("version") != _STATE_VERSION:
            return {}
        return data

    def _write_state(self, state: dict) -> None:
        assert self._path is not None
        self._ensure_dir()
        state["version"] = _STATE_VERSION
        # Write to a 0600 temp file and rename, so a reader never sees half a file
        # and the cookies are never briefly world-readable.
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            os.replace(tmp_name, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise


def _make_cookie(record: dict) -> Cookie:
    domain = record["domain"]
    path = record["path"]
    return Cookie(
        version=0,
        name=record["name"],
        value=record["value"],
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=domain.startswith("."),
        domain_initial_dot=domain.startswith("."),
        path=path,
        path_specified=True,
        secure=bool(record.get("secure", False)),
        expires=record.get("expires"),
        discard=record.get("expires") is None,
        comment=None,
        comment_url=None,
        rest={},
    )

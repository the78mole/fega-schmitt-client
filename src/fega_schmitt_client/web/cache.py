"""SQLite cache for article data fetched from the webshop.

Lives next to the DATANORM database as ``web.db`` in
``$XDG_CACHE_HOME/fega-schmitt-client``. Each article is stored as the JSON
of :meth:`Article.to_dict` with its fetch time; entries older than the
caller's ``max_age`` count as missing. The cache saves shop requests, it is
never the only copy of anything, so an unreadable file is simply rebuilt.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from .models import Article
from .session import default_session_dir

if TYPE_CHECKING:
    from typing import Self

DEFAULT_MAX_AGE = timedelta(days=30)

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    material_number TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,   -- ISO timestamp, UTC
    data TEXT NOT NULL          -- JSON of Article.to_dict()
);
"""


def default_cache_path() -> Path:
    return default_session_dir() / "web.db"


class WebArticleCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = self._connect()
        except sqlite3.DatabaseError:
            self.path.unlink(missing_ok=True)
            self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, _SCHEMA_VERSION):
                conn.execute("DROP TABLE IF EXISTS articles")
            conn.executescript(_SCHEMA)
            conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        except sqlite3.DatabaseError:
            conn.close()
            raise
        return conn

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def get(self, material_number: str, max_age: timedelta = DEFAULT_MAX_AGE) -> Article | None:
        row = self._conn.execute(
            "SELECT data FROM articles WHERE material_number = ? AND fetched_at >= ?",
            (material_number, (datetime.now(timezone.utc) - max_age).isoformat(timespec="seconds")),
        ).fetchone()
        return Article.from_dict(json.loads(row[0])) if row else None

    def put(self, article: Article) -> None:
        # Same fixed format as in get(), so the timestamps compare as strings.
        fetched_at = article.fetched_at.astimezone(timezone.utc).isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO articles VALUES (?, ?, ?)",
                (article.material_number, fetched_at, json.dumps(article.to_dict(), ensure_ascii=False)),
            )

    def delete(self, material_number: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM articles WHERE material_number = ?", (material_number,))

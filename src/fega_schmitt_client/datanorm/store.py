"""Read access to the database built by :func:`import_delivery`."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from .db import SCHEMA_VERSION, default_db_path

if TYPE_CHECKING:
    from typing import Self

DEFAULT_SEARCH_LIMIT = 50


@dataclass
class DatanormArticle:
    """One article as of the imported delivery. Prices are per ``price_unit``."""

    material_number: str
    short_text_1: str | None
    short_text_2: str | None
    unit: str | None
    price_unit: int | None
    list_price: Decimal | None
    net_price: Decimal | None
    ean: str | None
    manufacturer_type: str | None
    manufacturer_item_number: str | None
    main_group: str | None
    main_group_name: str | None
    sub_group: str | None
    sub_group_name: str | None
    delivery_date: str

    @property
    def description(self) -> str | None:
        return " ".join(t for t in (self.short_text_1, self.short_text_2) if t) or None


@dataclass
class DatanormSearchHit:
    material_number: str
    description: str | None
    matched: str  # material_number, ean, manufacturer_number or text


_ARTICLE_SQL = """
SELECT a.material_number, a.short_text_1, a.short_text_2, a.unit, a.price_unit,
       lp.price_cents, np.price_cents, a.ean, a.manufacturer_type, a.manufacturer_item_number,
       a.main_group, mg.name, a.sub_group, sg.name
FROM articles a
LEFT JOIN prices lp ON lp.material_number = a.material_number AND lp.price_type = 1
LEFT JOIN prices np ON np.material_number = a.material_number AND np.price_type = 2
LEFT JOIN groups mg ON mg.main_group = a.main_group AND mg.sub_group = ''
LEFT JOIN groups sg ON sg.main_group = a.main_group AND sg.sub_group = a.sub_group
WHERE a.material_number = ?
"""


class DatanormStore:
    """Read-only view on ``datanorm.db``.

    ``open()`` returns None when there is no usable database, so callers can
    fall back to other sources without special-casing a fresh installation.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.delivery_date: str = conn.execute("SELECT max(delivery_date) FROM deliveries WHERE kind = 'A'").fetchone()[
            0
        ]

    @classmethod
    def open(cls, path: Path | None = None) -> DatanormStore | None:
        path = path or default_db_path()
        if not path.exists():
            return None
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                conn.close()
                return None
            return cls(conn)
        except sqlite3.DatabaseError:
            conn.close()
            return None

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

    def get_article(self, material_number: str) -> DatanormArticle | None:
        row = self._conn.execute(_ARTICLE_SQL, (material_number,)).fetchone()
        if row is None:
            return None
        (number, text1, text2, unit, price_unit, list_cents, net_cents, ean, mtype, mnumber, main, main_name, sub,
         sub_name) = row  # fmt: skip
        return DatanormArticle(
            material_number=number,
            short_text_1=text1,
            short_text_2=text2,
            unit=unit,
            price_unit=price_unit,
            list_price=_euros(list_cents),
            net_price=_euros(net_cents),
            ean=ean,
            manufacturer_type=mtype,
            manufacturer_item_number=mnumber,
            main_group=main,
            main_group_name=main_name,
            sub_group=sub,
            sub_group_name=sub_name,
            delivery_date=self.delivery_date,
        )

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[DatanormSearchHit]:
        """Exact matches on article number, EAN and manufacturer numbers first,
        then articles whose short texts contain every word of ``query``."""
        query = query.strip()
        if not query:
            return []
        hits: dict[str, DatanormSearchHit] = {}

        def add(matched: str, sql: str, params: tuple) -> None:
            for number, text1, text2 in self._conn.execute(sql, params):
                if len(hits) < limit and number not in hits:
                    description = " ".join(t for t in (text1, text2) if t) or None
                    hits[number] = DatanormSearchHit(number, description, matched)

        select = "SELECT material_number, short_text_1, short_text_2 FROM articles"
        add("material_number", f"{select} WHERE material_number = ?", (query,))
        add("ean", f"{select} WHERE ean = ?", (query,))
        add(
            "manufacturer_number",
            f"{select} WHERE manufacturer_item_number = ?1 COLLATE NOCASE OR manufacturer_type = ?1 COLLATE NOCASE "
            "ORDER BY material_number",
            (query,),
        )
        words = query.split()
        if len(hits) < limit:
            # LIKE is case-insensitive for ASCII only; good enough for the
            # manufacturer prefixes and type designations people search for.
            text = "coalesce(short_text_1, '') || ' ' || coalesce(short_text_2, '')"
            where = " AND ".join(f"{text} LIKE ? ESCAPE '\\'" for _ in words)
            add("text", f"{select} WHERE {where} ORDER BY material_number LIMIT ?", (*map(_like, words), limit))
        return list(hits.values())


def _like(word: str) -> str:
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _euros(cents: int | None) -> Decimal | None:
    return Decimal(cents) / 100 if cents is not None else None

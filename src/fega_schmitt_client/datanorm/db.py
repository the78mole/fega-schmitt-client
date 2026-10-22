"""Load a DATANORM delivery into SQLite and report what changed.

FEGA sends full deliveries (every record flagged ``N``), so each import
builds a fresh database. An existing one is copied to
``datanorm-<its delivery date>.db`` next to it before it is replaced, and the
new database is compared against it.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from ._parser import DatanormFormatError, FileReader, Header, Source, int_field
from ._parser import field as get

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE deliveries (
    file TEXT PRIMARY KEY,
    kind TEXT NOT NULL,             -- A articles, S groups, P prices
    version TEXT NOT NULL,
    delivery_date TEXT NOT NULL,    -- ISO date from the V header
    currency TEXT NOT NULL,
    line_count INTEGER NOT NULL,
    header TEXT NOT NULL
);

CREATE TABLE groups (
    main_group TEXT NOT NULL,
    sub_group TEXT NOT NULL,        -- '' for the main group itself
    name TEXT NOT NULL,
    PRIMARY KEY (main_group, sub_group)
);

CREATE TABLE articles (
    material_number TEXT PRIMARY KEY,   -- FEGA article number, same as for the SOAP service
    short_text_1 TEXT,
    short_text_2 TEXT,
    unit TEXT,                          -- STCK, MTR, PACK, ...
    field_7 TEXT,                       -- meaning unknown, always 1 so far
    price_unit INTEGER,                 -- prices are per 1, 100 or 1000 units
    list_price_cents INTEGER,
    discount_group TEXT,
    main_group TEXT,
    sub_group TEXT,
    manufacturer_type TEXT,
    manufacturer_item_number TEXT,
    ean TEXT,
    field_23 TEXT,                      -- meaning unknown, 4 or 0
    field_28 TEXT,                      -- meaning unknown
    field_29 TEXT,                      -- meaning unknown, almost always 1
    extra TEXT                          -- JSON {field number: value} of the remaining non-empty fields
);

CREATE TABLE prices (
    material_number TEXT NOT NULL,
    price_type INTEGER NOT NULL,        -- 1 list price, 2 customer net price
    price_unit INTEGER,
    price_cents INTEGER NOT NULL,
    PRIMARY KEY (material_number, price_type)
);

CREATE TABLE surcharges (
    material_number TEXT NOT NULL,
    seq TEXT NOT NULL,                  -- 01..04
    fields TEXT NOT NULL,               -- JSON list of fields 5.., meaning only partly known
    PRIMARY KEY (material_number, seq)
);

CREATE VIEW article_prices AS
SELECT
    a.material_number,
    a.short_text_1,
    a.short_text_2,
    a.unit,
    a.price_unit,
    lp.price_cents / 100.0 AS list_price,
    np.price_cents / 100.0 AS net_price,
    np.price_cents / 100.0 / a.price_unit AS net_price_per_unit,
    a.main_group,
    mg.name AS main_group_name,
    a.sub_group,
    sg.name AS sub_group_name,
    a.ean,
    a.manufacturer_item_number
FROM articles a
LEFT JOIN prices lp ON lp.material_number = a.material_number AND lp.price_type = 1
LEFT JOIN prices np ON np.material_number = a.material_number AND np.price_type = 2
LEFT JOIN groups mg ON mg.main_group = a.main_group AND mg.sub_group = ''
LEFT JOIN groups sg ON sg.main_group = a.main_group AND sg.sub_group = a.sub_group;
"""

# Field numbers of the A record that get their own column.
_ARTICLE_FIELDS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 17, 19, 23, 28, 29}

# Columns compared for "changed article", with the label used in the summary.
# The list price is reported with the prices, not here.
ARTICLE_COLUMNS = {
    "short_text_1": "Kurztext 1",
    "short_text_2": "Kurztext 2",
    "unit": "Mengeneinheit",
    "field_7": "Feld 7",
    "price_unit": "Preiseinheit",
    "discount_group": "Rabattgruppe",
    "main_group": "Hauptgruppe",
    "sub_group": "Warengruppe",
    "manufacturer_type": "Herstellertyp",
    "manufacturer_item_number": "Hersteller-Bestellnr.",
    "ean": "EAN",
    "field_23": "Feld 23",
    "field_28": "Feld 28",
    "field_29": "Feld 29",
    "extra": "übrige Felder",
}

PRICE_TYPES = {1: "Listenpreis", 2: "Einkaufspreis"}

MAX_EXAMPLES = 5


def default_db_path() -> Path:
    """``$XDG_CACHE_HOME/fega-schmitt-client/datanorm.db``, falling back to ``~/.cache``."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "fega-schmitt-client" / "datanorm.db"


@dataclass
class PriceChange:
    material_number: str
    short_text: str | None
    old_cents: int
    old_price_unit: int
    new_cents: int
    new_price_unit: int

    @property
    def percent(self) -> float:
        """Change of the price per single unit, so a switch from "per 1" to "per 100" is not a jump."""
        old = self.old_cents / self.old_price_unit
        new = self.new_cents / self.new_price_unit
        return (new - old) / old * 100 if old else 0.0


@dataclass
class PriceTypeChanges:
    label: str
    changed: int = 0
    increased: int = 0
    decreased: int = 0
    largest: list[PriceChange] = field(default_factory=list)


@dataclass
class Changes:
    """Differences between the previous and the new database."""

    old_delivery_date: str | None
    new_delivery_date: str
    articles_total: int
    articles_added: list[tuple[str, str | None]]  # (material number, short text 1), at most MAX_EXAMPLES
    articles_added_count: int
    articles_removed: list[tuple[str, str | None]]
    articles_removed_count: int
    articles_changed_count: int
    article_column_changes: dict[str, int]  # label -> number of articles
    prices: list[PriceTypeChanges]
    groups_added: list[tuple[str, str, str]]
    groups_removed: list[tuple[str, str, str]]
    groups_renamed: list[tuple[str, str, str, str]]  # main, sub, old name, new name
    surcharges_added: int
    surcharges_removed: int
    surcharges_changed: int

    @property
    def is_first_import(self) -> bool:
        return self.old_delivery_date is None


@dataclass
class ImportResult:
    db_path: Path
    delivery_date: str
    articles: int
    prices: int
    groups: int
    surcharges: int
    backup_path: Path | None
    changes: Changes | None  # None when the previous database could not be compared


def import_delivery(source_path: Path, db_path: Path | None = None) -> ImportResult:
    """Import a delivery (``datanorm.zip`` or a directory) into ``db_path``.

    The new database is built next to the target and only moved into place
    once every file has been read and checked, so a broken delivery leaves
    the previous database untouched.
    """
    db_path = db_path or default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    scratch = db_path.with_name(db_path.name + ".new")
    scratch.unlink(missing_ok=True)

    source = Source(source_path)
    try:
        # URI mode, so ATTACH can open the previous database read-only.
        conn = sqlite3.connect(scratch.resolve().as_uri(), uri=True)
        try:
            counts = _load(conn, source)
            delivery_date = _delivery_date(conn)
            changes = None
            backup = None
            if db_path.exists():
                old_date = _readable_delivery_date(db_path)
                if old_date is not None:
                    changes = _compare(conn, db_path, old_date, delivery_date)
                backup = db_path.with_name(f"{db_path.stem}-{old_date or 'alt'}{db_path.suffix}")
            else:
                changes = _first_import(conn, delivery_date)
            conn.close()
        except BaseException:
            conn.close()
            scratch.unlink(missing_ok=True)
            raise
    finally:
        source.close()

    if backup is not None:
        shutil.copy2(db_path, backup)
    os.replace(scratch, db_path)
    return ImportResult(
        db_path=db_path,
        delivery_date=delivery_date,
        backup_path=backup,
        changes=changes,
        **counts,
    )


def _load(conn: sqlite3.Connection, source: Source) -> dict[str, int]:
    conn.executescript(_SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    files = source.files()
    counts = {"articles": 0, "prices": 0, "groups": 0, "surcharges": 0}
    with conn:
        for name in files.groups:
            reader = FileReader(source, name, "S")
            counts["groups"] += _insert(conn, "groups", 3, (_group_row(r) for r in reader), name)
            _insert_header(conn, reader.header)
        for name in files.articles:
            reader = FileReader(source, name, "A")
            surcharges: list[tuple] = []
            counts["articles"] += _insert(conn, "articles", 17, _split_article_file(reader, surcharges), name)
            counts["surcharges"] += _insert(conn, "surcharges", 3, surcharges, name)
            _insert_header(conn, reader.header)
        for name in files.prices:
            reader = FileReader(source, name, "P")
            counts["prices"] += _insert(conn, "prices", 4, (_price_row(r, name) for r in reader), name)
            _insert_header(conn, reader.header)
    return counts


def _insert(conn: sqlite3.Connection, table: str, width: int, rows: Iterable[tuple], name: str) -> int:
    before = conn.total_changes
    try:
        conn.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * width)})", rows)
    except sqlite3.IntegrityError as exc:
        raise DatanormFormatError(f"{name}: doppelter Satz ({exc}).") from exc
    return conn.total_changes - before


def _insert_header(conn: sqlite3.Connection, header: Header | None) -> None:
    assert header is not None  # set once the reader has been iterated
    conn.execute(
        "INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            header.file,
            header.kind,
            header.version,
            header.delivery_date,
            header.currency,
            header.line_count,
            header.raw,
        ),
    )


def _group_row(record: list[str]) -> tuple:
    if record[0] != "S":
        raise DatanormFormatError(f"Unerwarteter Satz {record[0]!r} in der Warengruppendatei.")
    return (get(record, 2) or "", get(record, 3) or "", get(record, 4) or "")


def _split_article_file(reader: FileReader, surcharges: list[tuple]) -> Iterator[tuple]:
    """Yield the A rows and collect the Z rows into ``surcharges``.

    One pass over the file: the A rows stream into executemany, the Z rows
    (about 27k small tuples) are inserted afterwards.
    """
    for record in reader:
        _check_processing_flag(record, reader.name)
        if record[0] == "A":
            yield _article_row(record)
        elif record[0] == "Z":
            fields = record[4:]
            while fields and not fields[-1].strip():
                fields.pop()
            surcharges.append((get(record, 3), get(record, 4), json.dumps(fields, ensure_ascii=False)))
        else:
            raise DatanormFormatError(f"{reader.name}: unbekannte Satzart {record[0]!r}.")


def _check_processing_flag(record: list[str], name: str) -> None:
    flag = get(record, 2)
    if flag != "N":
        raise DatanormFormatError(
            f"{name}: Satz mit Verarbeitungskennzeichen {flag!r}. Nur Volllieferungen (N) werden unterstützt, "
            "eine Änderungslieferung würde die Datenbank sonst unvollständig machen."
        )


def _article_row(record: list[str]) -> tuple:
    extra = {str(i + 1): v for i, v in enumerate(record) if i + 1 not in _ARTICLE_FIELDS and v.strip()}
    return (
        get(record, 3),
        get(record, 4),
        get(record, 5),
        get(record, 6),
        get(record, 7),
        int_field(record, 8),
        int_field(record, 9),
        get(record, 10),
        get(record, 11),
        get(record, 12),
        get(record, 13),
        get(record, 17),
        get(record, 19),
        get(record, 23),
        get(record, 28),
        get(record, 29),
        json.dumps(extra, ensure_ascii=False) if extra else None,
    )


def _price_row(record: list[str], name: str) -> tuple:
    if record[0] != "P":
        raise DatanormFormatError(f"{name}: unerwarteter Satz {record[0]!r} in der Preisdatei.")
    return (get(record, 2), int_field(record, 3), int_field(record, 4), int_field(record, 5))


def _delivery_date(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT max(delivery_date) FROM deliveries WHERE kind = 'A'").fetchone()
    return row[0]


def _readable_delivery_date(db_path: Path) -> str | None:
    """Delivery date of an existing database, ``None`` if it has another schema."""
    try:
        with closing(sqlite3.connect(_read_only_uri(db_path), uri=True)) as old:
            if old.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                return None
            return _delivery_date(old)
    except sqlite3.DatabaseError:
        return None


def _read_only_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro"


def _first_import(conn: sqlite3.Connection, delivery_date: str) -> Changes:
    total = conn.execute("SELECT count(*) FROM articles").fetchone()[0]
    return Changes(
        old_delivery_date=None,
        new_delivery_date=delivery_date,
        articles_total=total,
        articles_added=[],
        articles_added_count=total,
        articles_removed=[],
        articles_removed_count=0,
        articles_changed_count=0,
        article_column_changes={},
        prices=[],
        groups_added=[],
        groups_removed=[],
        groups_renamed=[],
        surcharges_added=conn.execute("SELECT count(*) FROM surcharges").fetchone()[0],
        surcharges_removed=0,
        surcharges_changed=0,
    )


def _compare(conn: sqlite3.Connection, old_path: Path, old_date: str, new_date: str) -> Changes:
    conn.execute("ATTACH DATABASE ? AS old", (_read_only_uri(old_path),))
    try:
        return _collect_changes(conn, old_date, new_date)
    finally:
        conn.execute("DETACH DATABASE old")


def _collect_changes(conn: sqlite3.Connection, old_date: str, new_date: str) -> Changes:
    def scalar(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    added_sql = "FROM main.articles n WHERE n.material_number NOT IN (SELECT material_number FROM old.articles)"
    removed_sql = "FROM old.articles o WHERE o.material_number NOT IN (SELECT material_number FROM main.articles)"
    joined = "FROM main.articles n JOIN old.articles o USING (material_number)"
    differs = " OR ".join(f"n.{c} IS NOT o.{c}" for c in ARTICLE_COLUMNS)

    column_changes = {}
    for column, label in ARTICLE_COLUMNS.items():
        count = scalar(f"SELECT count(*) {joined} WHERE n.{column} IS NOT o.{column}")
        if count:
            column_changes[label] = count

    prices = []
    for price_type, label in PRICE_TYPES.items():
        # Prices are per price unit (1, 100 or 1000), so compare per single
        # unit: cross-multiplied to stay in integers.
        new_per_unit = "n.price_cents * max(o.price_unit, 1)"
        old_per_unit = "o.price_cents * max(n.price_unit, 1)"
        pair = (
            "FROM main.prices n JOIN old.prices o USING (material_number, price_type) "
            "LEFT JOIN main.articles a USING (material_number) "
            f"WHERE n.price_type = {price_type} AND {new_per_unit} != {old_per_unit}"
        )
        largest = [
            PriceChange(*row)
            for row in conn.execute(
                "SELECT n.material_number, a.short_text_1, o.price_cents, max(o.price_unit, 1), "
                f"n.price_cents, max(n.price_unit, 1) {pair} "
                f"ORDER BY abs({new_per_unit} - {old_per_unit}) * 1.0 / max({old_per_unit}, 1) DESC, "
                f"n.material_number LIMIT {MAX_EXAMPLES}"
            )
        ]
        prices.append(
            PriceTypeChanges(
                label=label,
                changed=scalar(f"SELECT count(*) {pair}"),
                increased=scalar(f"SELECT count(*) {pair} AND {new_per_unit} > {old_per_unit}"),
                decreased=scalar(f"SELECT count(*) {pair} AND {new_per_unit} < {old_per_unit}"),
                largest=largest,
            )
        )

    def surcharge_count(sql: str) -> int:
        return scalar(f"SELECT count(*) {sql}")

    return Changes(
        old_delivery_date=old_date,
        new_delivery_date=new_date,
        articles_total=scalar("SELECT count(*) FROM main.articles"),
        articles_added=conn.execute(
            f"SELECT n.material_number, n.short_text_1 {added_sql} ORDER BY 1 LIMIT {MAX_EXAMPLES}"
        ).fetchall(),
        articles_added_count=scalar(f"SELECT count(*) {added_sql}"),
        articles_removed=conn.execute(
            f"SELECT o.material_number, o.short_text_1 {removed_sql} ORDER BY 1 LIMIT {MAX_EXAMPLES}"
        ).fetchall(),
        articles_removed_count=scalar(f"SELECT count(*) {removed_sql}"),
        articles_changed_count=scalar(f"SELECT count(*) {joined} WHERE {differs}"),
        article_column_changes=column_changes,
        prices=prices,
        groups_added=conn.execute(
            "SELECT main_group, sub_group, name FROM main.groups n "
            "WHERE NOT EXISTS (SELECT 1 FROM old.groups o WHERE o.main_group = n.main_group "
            "AND o.sub_group = n.sub_group) ORDER BY 1, 2"
        ).fetchall(),
        groups_removed=conn.execute(
            "SELECT main_group, sub_group, name FROM old.groups o "
            "WHERE NOT EXISTS (SELECT 1 FROM main.groups n WHERE n.main_group = o.main_group "
            "AND n.sub_group = o.sub_group) ORDER BY 1, 2"
        ).fetchall(),
        groups_renamed=conn.execute(
            "SELECT n.main_group, n.sub_group, o.name, n.name FROM main.groups n "
            "JOIN old.groups o USING (main_group, sub_group) WHERE n.name IS NOT o.name ORDER BY 1, 2"
        ).fetchall(),
        surcharges_added=surcharge_count(
            "FROM main.surcharges n WHERE NOT EXISTS (SELECT 1 FROM old.surcharges o "
            "WHERE o.material_number = n.material_number AND o.seq = n.seq)"
        ),
        surcharges_removed=surcharge_count(
            "FROM old.surcharges o WHERE NOT EXISTS (SELECT 1 FROM main.surcharges n "
            "WHERE n.material_number = o.material_number AND n.seq = o.seq)"
        ),
        surcharges_changed=surcharge_count(
            "FROM main.surcharges n JOIN old.surcharges o USING (material_number, seq) WHERE n.fields IS NOT o.fields"
        ),
    )

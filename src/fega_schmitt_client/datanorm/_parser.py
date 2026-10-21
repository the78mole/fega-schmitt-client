"""Low-level reader for FEGA's DATANORM 5.0 files.

All three files (``datanorm.001``, ``datanorm.wrg``, ``datpreis.001``) are
CP850 encoded, semicolon separated and CRLF terminated. Each starts with a
``V`` header and ends with ``E;<line count>``, where the count includes the
``V`` and ``E`` lines themselves. Field meanings are derived from real
deliveries, see DATANORM.md.
"""

from __future__ import annotations

import dataclasses
import io
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

ENCODING = "cp850"

_ARTICLE_FILE = re.compile(r"^datanorm\.\d{3}$", re.IGNORECASE)
_GROUP_FILE = re.compile(r"^datanorm\.wrg$", re.IGNORECASE)
_PRICE_FILE = re.compile(r"^datpreis\.\d{3}$", re.IGNORECASE)


class DatanormFormatError(ValueError):
    """A file does not look like the DATANORM layout this parser knows."""


@dataclass(frozen=True)
class Header:
    file: str
    version: str
    kind: str
    delivery_date: str  # ISO date
    currency: str
    line_count: int
    raw: str


@dataclass(frozen=True)
class DeliveryFiles:
    """The member names of one delivery, grouped by type, in import order."""

    groups: list[str]
    articles: list[str]
    prices: list[str]


class Source:
    """A delivery given as ``datanorm.zip`` or as a directory of extracted files."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if path.is_dir():
            self._names = sorted(p.name for p in path.iterdir() if p.is_file())
            self._zip: zipfile.ZipFile | None = None
        elif zipfile.is_zipfile(path):
            self._zip = zipfile.ZipFile(path)
            self._names = sorted(n for n in self._zip.namelist() if "/" not in n.rstrip("/"))
        else:
            raise DatanormFormatError(f"{path} ist weder ein Verzeichnis noch ein ZIP-Archiv.")

    def files(self) -> DeliveryFiles:
        found = DeliveryFiles(
            groups=[n for n in self._names if _GROUP_FILE.match(n)],
            articles=[n for n in self._names if _ARTICLE_FILE.match(n)],
            prices=[n for n in self._names if _PRICE_FILE.match(n)],
        )
        if not found.articles:
            raise DatanormFormatError(f"Keine Artikeldatei (datanorm.001, ...) in {self.path} gefunden.")
        return found

    @contextmanager
    def open(self, name: str) -> Iterator[BinaryIO]:
        if self._zip is not None:
            with self._zip.open(name) as f:
                yield f
        else:
            with open(self.path / name, "rb") as f:
                yield f

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()


class FileReader:
    """Iterates the data records of one file, without V and E.

    ``header`` is set as soon as iteration starts. The ``E`` line count is
    checked when iteration ends, so a truncated file raises after its last
    record instead of passing as a smaller delivery; callers write into a
    scratch database and only keep it once every file has been read.
    """

    def __init__(self, source: Source, name: str, expected_kind: str) -> None:
        self.source = source
        self.name = name
        self.expected_kind = expected_kind
        self.header: Header | None = None

    def __iter__(self) -> Iterator[list[str]]:
        name = self.name
        count = 0
        end: list[str] | None = None
        with self.source.open(name) as raw, io.TextIOWrapper(raw, encoding=ENCODING, newline="") as text:
            for line_number, line in enumerate(text, start=1):
                fields = line.rstrip("\r\n").split(";")
                if fields and fields[-1] == "":
                    fields.pop()  # every line ends with a trailing ";"
                if end is not None:
                    raise DatanormFormatError(f"{name}: Daten nach dem E-Satz (Zeile {line_number}).")
                if line_number == 1:
                    self.header = self._parse_header(fields)
                elif fields[0] == "E":
                    end = fields
                else:
                    count += 1
                    yield fields

        if self.header is None or end is None:
            raise DatanormFormatError(f"{name}: V- oder E-Satz fehlt, Datei unvollständig?")
        line_count = count + 2
        if len(end) < 2 or end[1] != str(line_count):
            raise DatanormFormatError(f"{name}: E-Satz meldet {end[1:2]} Zeilen, gelesen wurden {line_count}.")
        self.header = dataclasses.replace(self.header, line_count=line_count)

    def _parse_header(self, fields: list[str]) -> Header:
        name = self.name
        if fields[0] != "V" or len(fields) < 5:
            raise DatanormFormatError(f"{name}: erste Zeile ist kein V-Satz.")
        if fields[2] != self.expected_kind:
            raise DatanormFormatError(f"{name}: V-Satz hat Dateiart {fields[2]!r}, erwartet {self.expected_kind!r}.")
        if not fields[1].startswith("05"):
            raise DatanormFormatError(f"{name}: DATANORM-Version {fields[1]!r}, unterstützt wird nur 5.0.")
        stamp = fields[3]
        return Header(
            file=name,
            version=fields[1],
            kind=fields[2],
            delivery_date=f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}",
            currency=fields[4],
            line_count=0,
            raw=";".join(fields),
        )


def field(record: list[str], number: int) -> str | None:
    """1-based field access, ``None`` for missing or blank fields."""
    if number > len(record):
        return None
    value = record[number - 1].strip()
    return value or None


def int_field(record: list[str], number: int) -> int | None:
    value = field(record, number)
    return int(value) if value is not None else None

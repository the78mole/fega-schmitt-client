"""Tests for the DATANORM SQLite import and `fega datanorm import`.

The deliveries are synthetic, in the layout of FEGA's real files (CP850,
CRLF, trailing ";", E line counting V and E), not excerpts of them.
"""

from __future__ import annotations

import sqlite3
import zipfile

import pytest
from click.testing import CliRunner

from fega_schmitt_client.cli import main
from fega_schmitt_client.datanorm import DatanormFormatError, default_db_path, import_delivery

HEADER = "V;050;{kind};{date};EUR;{title};;;FEGA & Schmitt;Elektrogroßhandel GmbH;;Rettistr. 5;;;91522 Ansbach"


def _article(number, text1, text2="", unit="STCK", price_unit=1, price=1000, main="30", sub="05", ean="", flag="N"):
    fields = [""] * 30
    fields[:13] = [
        "A",
        flag,
        number,
        text1,
        text2,
        unit,
        "1",
        str(price_unit),
        str(price),
        "",
        main,
        sub,
        "TYP " + number,
    ]
    fields[16] = "BN" + number
    fields[18] = ean
    fields[22] = "4"
    fields[28] = "1"
    return ";".join(fields)


def _write(path, lines):
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("cp850"))


def _file(kind, title, date, records):
    return [HEADER.format(kind=kind, date=date, title=title), *records, f"E;{len(records) + 2}"]


def make_delivery(directory, date="20260810", articles=None, prices=None, groups=None, surcharges=None):
    directory.mkdir(parents=True, exist_ok=True)
    if articles is None:
        articles = [
            _article(
                "100", "LAPP Leitung", "ÖLFLEX 3G1,5", unit="MTR", price_unit=100, price=6505, ean="4044776760863"
            ),
            _article("200", "JUNG Rahmen", price=1250),
            _article("300", "SIEM Schalter", price=4200),
        ]
    if prices is None:
        prices = ["P;100;1;100;6505", "P;100;2;100;4033", "P;200;1;1;1250", "P;200;2;1;800", "P;300;1;1;4200"]
        prices.append("P;300;2;1;3000")
    if groups is None:
        groups = ["S;30;;Sonstige Installationsgeräte", "S;30;05;Schalter und Dosen", "S;20;;Kabel und Leitungen"]
    if surcharges is None:
        surcharges = [
            "Z;N;100;01;3;CU;2;100;15000;10;290;1000",
            "Z;N;200;01;1;Verpackung (#);Verpackung (#);2;+;2;1;454",
        ]
    _write(directory / "datanorm.001", _file("A", "Artikelstammdaten", date, articles + surcharges))
    _write(directory / "datanorm.wrg", _file("S", "Warengruppenstammdaten", date, groups))
    _write(directory / "datpreis.001", _file("P", "Preisstammdaten", date, prices))
    return directory


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "db" / "datanorm.db"


def _query(db_path, sql):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_default_db_path_uses_xdg_cache(isolated_session_cache):
    assert default_db_path() == isolated_session_cache / "datanorm.db"


def test_import_directory(tmp_path, db_path):
    result = import_delivery(make_delivery(tmp_path / "d"), db_path)

    assert (result.articles, result.prices, result.groups, result.surcharges) == (3, 6, 3, 2)
    assert result.delivery_date == "2026-08-10"
    assert result.backup_path is None
    assert result.changes.is_first_import
    assert _query(db_path, "SELECT * FROM articles WHERE material_number = '100'") == [
        (
            "100",
            "LAPP Leitung",
            "ÖLFLEX 3G1,5",
            "MTR",
            "1",
            100,
            6505,
            None,
            "30",
            "05",
            "TYP 100",
            "BN100",
            "4044776760863",
            "4",
            None,
            "1",
            None,
        )
    ]
    assert _query(db_path, "SELECT * FROM surcharges ORDER BY material_number") == [
        ("100", "01", '["3", "CU", "2", "100", "15000", "10", "290", "1000"]'),
        ("200", "01", '["1", "Verpackung (#)", "Verpackung (#)", "2", "+", "2", "1", "454"]'),
    ]
    assert _query(db_path, "SELECT name FROM groups WHERE main_group = '30' AND sub_group = ''") == [
        ("Sonstige Installationsgeräte",)
    ]
    assert _query(db_path, "SELECT kind, delivery_date, line_count FROM deliveries ORDER BY file") == [
        ("A", "2026-08-10", 7),
        ("S", "2026-08-10", 5),
        ("P", "2026-08-10", 8),
    ]


def test_article_prices_view(tmp_path, db_path):
    import_delivery(make_delivery(tmp_path / "d"), db_path)

    rows = _query(
        db_path,
        "SELECT list_price, net_price, net_price_per_unit, main_group_name, sub_group_name "
        "FROM article_prices WHERE material_number = '100'",
    )
    assert rows == [(65.05, 40.33, 0.4033, "Sonstige Installationsgeräte", "Schalter und Dosen")]


def test_import_zip(tmp_path, db_path):
    delivery = make_delivery(tmp_path / "d")
    archive = tmp_path / "datanorm.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in delivery.iterdir():
            zf.write(path, path.name)

    assert import_delivery(archive, db_path).articles == 3


def test_reimport_backs_up_and_reports_changes(tmp_path, db_path):
    import_delivery(make_delivery(tmp_path / "aug"), db_path)
    october = make_delivery(
        tmp_path / "oct",
        date="20261021",
        articles=[
            _article("100", "LAPP Leitung", "ÖLFLEX 3G1,5", unit="MTR", price_unit=1, price=70, ean="4044776760863"),
            _article("200", "JUNG Rahmen weiß", price=1250),
            _article("400", "OBO Dose", price=99),
        ],
        prices=[
            "P;100;1;1;70",
            "P;100;2;1;45",
            "P;200;1;1;1250",
            "P;200;2;1;700",
            "P;400;1;1;99",
            "P;400;2;1;60",
        ],
        groups=["S;30;;Sonstige Installationsgeräte und Systeme", "S;30;05;Schalter und Dosen", "S;37;;Leuchten"],
        surcharges=["Z;N;100;01;3;CU;2;100;15000;10;300;1000"],
    )

    result = import_delivery(october, db_path)

    assert result.backup_path == db_path.with_name("datanorm-2026-08-10.db")
    assert _query(result.backup_path, "SELECT count(*) FROM articles WHERE material_number = '300'") == [(1,)]
    assert _query(db_path, "SELECT count(*) FROM articles WHERE material_number = '300'") == [(0,)]
    assert not db_path.with_name("datanorm.db.new").exists()

    changes = result.changes
    assert (changes.old_delivery_date, changes.new_delivery_date) == ("2026-08-10", "2026-10-21")
    assert changes.articles_added == [("400", "OBO Dose")]
    assert changes.articles_removed == [("300", "SIEM Schalter")]
    assert changes.articles_changed_count == 2
    assert changes.article_column_changes == {"Kurztext 1": 1, "Preiseinheit": 1}

    list_prices, net_prices = changes.prices
    # 100: 65,05 €/100 m -> 0,70 €/m is +7.6 % per metre, not a jump from 65,05 € to 0,70 €.
    assert (list_prices.changed, list_prices.increased, list_prices.decreased) == (1, 1, 0)
    assert list_prices.largest[0].material_number == "100"
    assert list_prices.largest[0].percent == pytest.approx(7.61, abs=0.01)
    assert (net_prices.changed, net_prices.increased, net_prices.decreased) == (2, 1, 1)

    assert changes.groups_added == [("37", "", "Leuchten")]
    assert changes.groups_removed == [("20", "", "Kabel und Leitungen")]
    assert changes.groups_renamed == [
        ("30", "", "Sonstige Installationsgeräte", "Sonstige Installationsgeräte und Systeme")
    ]
    assert (changes.surcharges_added, changes.surcharges_removed, changes.surcharges_changed) == (0, 1, 1)


def test_truncated_file_keeps_previous_database(tmp_path, db_path):
    import_delivery(make_delivery(tmp_path / "aug"), db_path)
    broken = make_delivery(tmp_path / "oct", date="20261021")
    lines = (broken / "datpreis.001").read_bytes().split(b"\r\n")
    (broken / "datpreis.001").write_bytes(b"\r\n".join(lines[:4]) + b"\r\n")

    with pytest.raises(DatanormFormatError, match="datpreis.001"):
        import_delivery(broken, db_path)

    assert _query(db_path, "SELECT delivery_date FROM deliveries WHERE kind = 'A'") == [("2026-08-10",)]
    assert not db_path.with_name("datanorm.db.new").exists()
    assert not db_path.with_name("datanorm-2026-08-10.db").exists()


def test_wrong_end_count_is_rejected(tmp_path, db_path):
    delivery = make_delivery(tmp_path / "d")
    path = delivery / "datanorm.wrg"
    path.write_bytes(path.read_bytes().replace(b"E;5", b"E;6"))

    with pytest.raises(DatanormFormatError, match="E-Satz meldet"):
        import_delivery(delivery, db_path)


def test_change_delivery_is_rejected(tmp_path, db_path):
    delivery = make_delivery(tmp_path / "d", articles=[_article("100", "LAPP Leitung", flag="L")])

    with pytest.raises(DatanormFormatError, match="Volllieferungen"):
        import_delivery(delivery, db_path)


def test_duplicate_article_is_rejected(tmp_path, db_path):
    delivery = make_delivery(tmp_path / "d", articles=[_article("100", "A"), _article("100", "B")])

    with pytest.raises(DatanormFormatError, match="doppelter Satz"):
        import_delivery(delivery, db_path)


def test_missing_article_file_is_rejected(tmp_path, db_path):
    delivery = make_delivery(tmp_path / "d")
    (delivery / "datanorm.001").unlink()

    with pytest.raises(DatanormFormatError, match="Keine Artikeldatei"):
        import_delivery(delivery, db_path)


def test_foreign_database_is_backed_up_without_comparison(tmp_path, db_path):
    db_path.parent.mkdir(parents=True)
    sqlite3.connect(db_path).close()  # empty database, schema version 0

    result = import_delivery(make_delivery(tmp_path / "d"), db_path)

    assert result.changes is None
    assert result.backup_path == db_path.with_name("datanorm-alt.db")


def test_cli_import_with_summary(tmp_path, db_path):
    runner = CliRunner()
    first = runner.invoke(main, ["datanorm", "import", str(make_delivery(tmp_path / "aug")), "--db", str(db_path)])
    assert first.exit_code == 0, first.output
    assert "3 Artikel" in first.output
    assert "Änderungen" not in first.output

    october = make_delivery(
        tmp_path / "oct",
        date="20261021",
        prices=["P;100;1;100;6505", "P;100;2;100;4033", "P;200;1;1;1250", "P;200;2;1;900", "P;300;1;1;4200"]
        + ["P;300;2;1;3000"],
    )
    result = runner.invoke(main, ["datanorm", "import", str(october), "--db", str(db_path), "-s"])

    assert result.exit_code == 0, result.output
    assert "datanorm-2026-08-10.db" in result.output
    assert "Änderungen 2026-08-10 -> 2026-10-21" in result.output
    assert "Einkaufspreis (je Einheit): 1 geändert (1 teurer, 0 günstiger)" in result.output
    assert "200  JUNG Rahmen: 8,00 € -> 9,00 € (+12.5 %)" in result.output


def test_cli_first_import_summary(tmp_path, db_path):
    result = CliRunner().invoke(
        main, ["datanorm", "import", str(make_delivery(tmp_path / "d")), "--db", str(db_path), "--summary"]
    )

    assert result.exit_code == 0, result.output
    assert "Erstimport" in result.output


def test_cli_import_reports_errors(tmp_path, db_path):
    delivery = make_delivery(tmp_path / "d")
    (delivery / "datanorm.001").unlink()

    result = CliRunner().invoke(main, ["datanorm", "import", str(delivery), "--db", str(db_path)])

    assert result.exit_code == 1
    assert "Keine Artikeldatei" in result.output

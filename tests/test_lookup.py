"""Tests for the combined lookup (DATANORM -> SOAP -> web cache -> webshop),
the DATANORM read access and the web cache. No request leaves the process:
SOAP and webshop are fakes."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from click.testing import CliRunner
from test_datanorm_db import _article, make_delivery

from fega_schmitt_client import cli
from fega_schmitt_client.datanorm import import_delivery
from fega_schmitt_client.datanorm.store import DatanormStore
from fega_schmitt_client.lookup import ArticleLookup, ArticleNotFoundError
from fega_schmitt_client.models import PriceAvailResultItem
from fega_schmitt_client.web import Article, ArticleSearchResult
from fega_schmitt_client.web.cache import WebArticleCache, default_cache_path
from fega_schmitt_client.web.models import ArticleImage


def web_article(material_number="200", fetched_at=None):
    return Article(
        material_number=material_number,
        fetched_at=fetched_at or datetime.now(timezone.utc),
        ean="4000000000002",
        manufacturer_item_number="SHOP-" + material_number,
        manufacturer_item_number_alt=None,
        supplier_name="Albrecht Jung",
        supplier_number="J1",
        category_id="UWG_1",
        category_name="Rahmen",
        own_article_number="EG-7",
        description="Shop-Titel " + material_number,
        cutting_fee=Decimal("2.50"),
        attributes={"Farbe": "weiß"},
        images=[ArticleImage(material_number, "https://example.test/a.jpg", True)],
        accessories=["300"],
    )


class FakeWeb:
    def __init__(self, articles=None, search_results=None, fail=False):
        self.articles = articles or {}
        self.search_results = search_results or []
        self.fail = fail
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def get_article(self, material_number):
        self.calls.append(("article", material_number))
        if self.fail:
            raise RuntimeError("Shop down")
        return self.articles[material_number]

    def search(self, query):
        self.calls.append(("search", query))
        return self.search_results

    def close(self):
        self.closed = True


class FakeSoap:
    def __init__(self, status="ok", fail=False, known=None):
        self.status = status
        self.fail = fail
        self.known = known
        self.requests = []

    def get_price_availability(self, items):
        self.requests.append(items)
        if self.fail:
            raise RuntimeError("SOAP timeout")
        status = self.status if self.known is None or items[0].material_number in self.known else "error"
        return [
            PriceAvailResultItem(
                line_item_number=1,
                material_number=items[0].material_number,
                status=status,
                return_code="0" if status == "ok" else "E01",
                return_code_text="OK" if status == "ok" else "Artikel unbekannt",
                availability_status="V",
                warehouse_name="Ansbach",
                net_amount=Decimal("8.10"),
                list_amount=Decimal("12.50"),
            )
        ]


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "datanorm.db"
    delivery = make_delivery(
        tmp_path / "d",
        articles=[
            _article(
                "100", "LAPP Leitung", "ÖLFLEX 3G1,5", unit="MTR", price_unit=100, price=6505, ean="4044776760863"
            ),
            _article("200", "JUNG Rahmen", "1-fach weiß", price=1250),
            _article("300", "JUNG Rahmen", "2-fach", price=4200),
            _article("400", "SIEM Schalter 50%", price=99),
        ],
        prices=["P;100;1;100;6505", "P;100;2;100;4033", "P;200;1;1;1250", "P;200;2;1;800"],
    )
    import_delivery(delivery, db_path)
    store = DatanormStore.open(db_path)
    yield store
    store.close()


@pytest.fixture
def cache(tmp_path):
    with WebArticleCache(tmp_path / "web.db") as cache:
        yield cache


def _lookup(store=None, soap=None, web=None, cache=None):
    return ArticleLookup(datanorm=store, soap=soap, web_factory=(lambda: web) if web else None, web_cache=cache)


# --- DatanormStore ---


def test_store_get_article(store):
    article = store.get_article("100")

    assert article.description == "LAPP Leitung ÖLFLEX 3G1,5"
    assert (article.unit, article.price_unit) == ("MTR", 100)
    assert (article.list_price, article.net_price) == (Decimal("65.05"), Decimal("40.33"))
    assert (article.main_group_name, article.sub_group_name) == ("Sonstige Installationsgeräte", "Schalter und Dosen")
    assert article.delivery_date == "2026-08-10"
    assert store.get_article("999") is None


@pytest.mark.parametrize(
    ("query", "expected", "matched"),
    [
        ("200", ["200"], "material_number"),
        ("4044776760863", ["100"], "ean"),
        ("bn300", ["300"], "manufacturer_number"),
        ("typ 300", ["300"], "manufacturer_number"),
        ("jung rahmen", ["200", "300"], "text"),
        ("rahmen weiß", ["200"], "text"),
        ("50%", ["400"], "text"),
        ("5%", [], None),
    ],
)
def test_store_search(store, query, expected, matched):
    hits = store.search(query)

    assert [h.material_number for h in hits] == expected
    if hits:
        assert hits[0].matched == matched


def test_store_search_limit(store):
    assert len(store.search("JUNG", limit=1)) == 1


def test_store_open_without_database(tmp_path):
    assert DatanormStore.open(tmp_path / "missing.db") is None
    sqlite3.connect(tmp_path / "other.db").close()
    assert DatanormStore.open(tmp_path / "other.db") is None


# --- ArticleLookup ---


def test_search_prefers_datanorm(store):
    web = FakeWeb()
    hits = _lookup(store, web=web).search("JUNG")

    assert [(h.material_number, h.source) for h in hits] == [("200", "datanorm"), ("300", "datanorm")]
    assert web.calls == []


def test_search_falls_back_to_web(store):
    web = FakeWeb(search_results=[ArticleSearchResult("777", "OBO Dose", None, "/p/777")])

    hits = _lookup(store, web=web).search("OBO")

    assert [(h.material_number, h.source) for h in hits] == [("777", "web")]


def test_search_without_any_source():
    assert _lookup().search("x") == []


def test_get_article_combines_sources_and_caches_web(store, cache):
    web = FakeWeb({"200": web_article("200")})
    soap = FakeSoap()

    info = _lookup(store, soap, web, cache).get_article("200")

    assert info.sources == ["datanorm", "soap", "web"]
    assert info.description == "JUNG Rahmen 1-fach weiß"  # DATANORM wins over the shop title
    assert info.manufacturer_item_number == "BN200"
    assert info.price_availability.net_amount == Decimal("8.10")
    assert info.web.attributes == {"Farbe": "weiß"}
    assert not info.web_from_cache
    assert soap.requests[0][0].material_number == "200"
    assert cache.get("200").images[0].url == "https://example.test/a.jpg"


def test_get_article_uses_fresh_cache_without_shop_request(store, cache):
    cache.put(web_article("200"))
    web = FakeWeb()

    info = _lookup(store, web=web, cache=cache).get_article("200")

    assert info.web_from_cache
    assert info.web.own_article_number == "EG-7"
    assert web.calls == []


def test_get_article_refetches_stale_or_refreshed_cache(store, cache):
    cache.put(web_article("200", fetched_at=datetime.now(timezone.utc) - timedelta(days=40)))
    web = FakeWeb({"200": web_article("200")})
    lookup = _lookup(store, web=web, cache=cache)

    assert not lookup.get_article("200").web_from_cache
    assert not lookup.get_article("200", refresh=True).web_from_cache
    assert lookup.get_article("200", max_age=timedelta(days=1)).web_from_cache
    assert web.calls == [("article", "200"), ("article", "200")]


def test_get_article_no_web(store, cache):
    web = FakeWeb()

    info = _lookup(store, web=web, cache=cache).get_article("200", use_web=False)

    assert info.sources == ["datanorm"]
    assert web.calls == []


def test_get_article_failures_become_warnings(store):
    info = _lookup(store, FakeSoap(fail=True), FakeWeb(fail=True)).get_article("200")

    assert info.sources == ["datanorm"]
    assert any("SOAP timeout" in w for w in info.warnings)
    assert any("Shop down" in w for w in info.warnings)


def test_get_article_soap_error_status_is_a_warning(store):
    info = _lookup(store, FakeSoap(status="error")).get_article("200", use_web=False)

    assert info.price_availability is None
    assert info.warnings == ["SOAP: E01 Artikel unbekannt"]


def test_get_article_without_datanorm_uses_web(cache):
    info = _lookup(web=FakeWeb({"777": web_article("777")}), cache=cache).get_article("777")

    assert info.sources == ["web"]
    assert info.description == "Shop-Titel 777"
    assert info.ean == "4000000000002"
    assert "fega datanorm import" in info.warnings[0]


def test_get_article_not_found(store):
    with pytest.raises(ArticleNotFoundError, match="999"):
        _lookup(store, web=FakeWeb(fail=True)).get_article("999")


def test_lookup_closes_web_and_cache(store, tmp_path):
    web = FakeWeb({"200": web_article("200")})
    cache = WebArticleCache(tmp_path / "web.db")
    with _lookup(store, web=web, cache=cache) as lookup:
        lookup.get_article("200")

    assert web.closed
    with pytest.raises(sqlite3.ProgrammingError):
        cache.get("200")


# --- WebArticleCache ---


def test_article_dict_roundtrip():
    article = web_article("200")

    assert Article.from_dict(json.loads(json.dumps(article.to_dict()))) == article


def test_cache_default_path_next_to_datanorm(isolated_session_cache):
    assert default_cache_path() == isolated_session_cache / "web.db"


def test_cache_delete(cache):
    cache.put(web_article("200"))
    cache.delete("200")

    assert cache.get("200") is None


def test_cache_rebuilds_unreadable_file(tmp_path):
    path = tmp_path / "web.db"
    path.write_bytes(b"not a database" * 100)

    with WebArticleCache(path) as cache:
        cache.put(web_article("200"))
        assert cache.get("200") is not None


# --- CLI ---


@pytest.fixture
def cli_env(store, tmp_path, monkeypatch):
    """Credentials set, SOAP and webshop replaced by fakes."""
    web = FakeWeb({"200": web_article("200")})
    monkeypatch.setattr(cli, "FegaSchmittClient", lambda **kwargs: FakeSoap(known={"100", "200"}))
    monkeypatch.setattr(cli, "WebClient", lambda **kwargs: web)
    env = {
        "FEGA_CUSTOMER_NUMBER": "9920",
        "FEGA_SHOP_PASSWORD": "kennwort",
        "FEGA_DATANORM_DB": str(tmp_path / "datanorm.db"),
    }
    return env, web


def test_cli_search(cli_env):
    env, web = cli_env

    result = CliRunner().invoke(cli.main, ["search", "JUNG"], env=env)

    assert result.exit_code == 0, result.output
    assert "200  JUNG Rahmen 1-fach weiß  [datanorm]" in result.output
    assert web.calls == []


def test_cli_article_text(cli_env):
    env, _ = cli_env

    result = CliRunner().invoke(cli.main, ["article", "200"], env=env)

    assert result.exit_code == 0, result.output
    assert "Quellen: datanorm, soap, web" in result.output
    assert "DATANORM (2026-08-10): Liste 12,50 €, Einkauf 8,00 € je 1 STCK" in result.output
    assert "Aktuell (SOAP): 8,10 €" in result.output
    assert "Shop (live):" in result.output

    again = CliRunner().invoke(cli.main, ["article", "200"], env=env)
    assert "Shop (Cache vom " in again.output


def test_cli_article_json(cli_env):
    env, _ = cli_env

    result = CliRunner().invoke(cli.main, ["article", "200", "-j", "--no-web"], env=env)

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["sources"] == ["datanorm", "soap"]
    assert data["datanorm"]["net_price"] == "8"
    assert data["web"] is None


def test_cli_article_without_credentials_uses_datanorm_only(tmp_path, store):
    env = {"FEGA_CUSTOMER_NUMBER": "", "FEGA_SHOP_PASSWORD": "", "FEGA_DATANORM_DB": str(tmp_path / "datanorm.db")}

    result = CliRunner().invoke(cli.main, ["article", "100"], env=env)

    assert result.exit_code == 0, result.output
    assert "Quellen: datanorm" in result.output
    assert "je 100 MTR" in result.output


def test_cli_article_not_found(cli_env):
    env, _ = cli_env

    result = CliRunner().invoke(cli.main, ["article", "999", "--no-web"], env=env)

    assert result.exit_code == 1
    assert "nicht gefunden" in result.output


def test_cli_set_article_number_invalidates_cache(monkeypatch):
    class FakeShop:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def set_article_number(self, material_number, value):
            pass

    with WebArticleCache() as cache:
        cache.put(web_article("200"))
    monkeypatch.setattr(cli, "WebClient", lambda **kwargs: FakeShop())

    result = CliRunner().invoke(
        cli.main,
        ["--customer-number", "9920", "--shop-password", "kennwort", "web", "set-article-number", "200", "NEU"],
    )

    assert result.exit_code == 0, result.output
    with WebArticleCache() as cache:
        assert cache.get("200") is None

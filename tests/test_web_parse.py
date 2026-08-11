"""Tests for fega_schmitt_client.web._parse against fixture HTML.

See tests/web_fixtures.py for where each fixture's markup comes from, and
docs/extensions.md for the underlying research each pattern is based on.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from web_fixtures import (
    ARTICLE_DETAIL_HTML,
    ARTICLE_DETAIL_NO_ALTERNATIVES_HTML,
    ARTICLE_DETAIL_NO_DATA_VARIABLES_HTML,
    ARTICLE_DETAIL_WITH_CUTTING_FEE_HTML,
    CABLE_LENGTHS_HTML,
    CART_HTML,
    DEAL_CAMPAIGNS_HTML,
    ORDER_DETAIL_HTML,
    ORDER_LIST_HTML,
    SEARCH_RESULTS_HTML,
)

from fega_schmitt_client.web import _parse


def test_parse_tile_list_finds_article_and_skips_ad_tile():
    results = _parse.parse_tile_list(SEARCH_RESULTS_HTML)

    assert len(results) == 1
    assert results[0].material_number == "121350"
    assert results[0].description == "NEUT Gummischlauchleitung H07RN-F 5G16 TR500m schwarz"
    assert results[0].detail_url.endswith("121350.html")


def test_parse_article_detail_extracts_all_fields():
    detail = _parse.parse_article_detail(ARTICLE_DETAIL_HTML, "051430")

    assert detail.material_number == "051430"
    assert detail.ean == "4016705110575"
    assert detail.manufacturer_item_number == "05101057"
    assert detail.manufacturer_item_number_alt == "PAEH 1000/12"
    assert detail.supplier_name == "PROTEC.class"
    assert detail.supplier_number == "79559"
    assert detail.category_id == "UWG_1_1"  # normalized from the "_0" suffix on the page
    assert detail.category_name == "Aderendhülsen"
    assert detail.own_article_number == "MY-OWN-NUMBER"


def test_parse_article_images_marks_first_as_primary():
    images = _parse.parse_article_images(ARTICLE_DETAIL_HTML, "051430")

    assert len(images) == 1
    assert images[0].is_primary is True
    assert images[0].url.endswith("pbm_051430.jpg.jpg")


def test_parse_cart_extracts_items_and_metadata():
    cart = _parse.parse_cart(CART_HTML)

    assert cart.cart_id == "13586483"
    assert cart.name == "Testkorb"
    assert len(cart.items) == 1
    item = cart.items[0]
    assert item.material_number == "518927"
    assert item.quantity == Decimal(20)
    assert item.position_id == "59298595"
    assert item.comment == "Testkommentar"


def test_parse_cart_list_excludes_current_cart():
    carts = _parse.parse_cart_list(CART_HTML)

    assert {c.cart_id for c in carts} == {"12335021", "12273523"}
    assert {c.name for c in carts} == {"Projekt A", "Projekt B"}


def test_parse_order_list_deduplicates_detail_row():
    orders = _parse.parse_order_list(ORDER_LIST_HTML)

    assert len(orders) == 1
    assert orders[0].order_number == "45238958"
    assert orders[0].position == "1"
    assert orders[0].order_date == "14.01.26"
    assert orders[0].status == "Rechnung erstellt"


def test_parse_order_detail_extracts_line_items():
    order = _parse.parse_order_detail("45238958", ORDER_DETAIL_HTML)

    assert len(order.items) == 1
    item = order.items[0]
    assert item.material_number == "405881"
    assert item.position == 4
    assert item.description == "WAGO 3 Leiter Schutzleiterklemme 2016-1307"
    assert item.quantity_ordered == Decimal(20)
    assert item.quantity_delivered == Decimal(20)


def test_parse_article_attributes_extracts_label_value_pairs():
    attributes = _parse.parse_article_attributes(ARTICLE_DETAIL_HTML)

    assert attributes == {"Farbe": "rot", "Werkstoff": "Kupfer"}


def test_parse_article_accessories_excludes_own_material_number():
    accessories = _parse.parse_article_accessories(ARTICLE_DETAIL_HTML)

    assert accessories == ["051988", "057288", "053943"]


def test_parse_article_variants_excludes_own_material_number():
    variants = _parse.parse_article_variants(ARTICLE_DETAIL_HTML)

    assert variants == ["054821", "875999", "051870"]


def test_parse_article_alternatives_excludes_own_material_number():
    alternatives = _parse.parse_article_alternatives(ARTICLE_DETAIL_HTML)

    assert alternatives == ["6169773", "9641674"]


def test_parse_article_cross_sell_excludes_own_material_number():
    cross_sell = _parse.parse_article_cross_sell(ARTICLE_DETAIL_HTML)

    assert cross_sell == ["051431", "051432"]


def test_parse_article_alternatives_returns_empty_list_when_section_missing():
    assert _parse.parse_article_alternatives(ARTICLE_DETAIL_NO_ALTERNATIVES_HTML) == []


def test_parse_article_variants_returns_empty_list_when_headline_present_but_no_data():
    assert _parse.parse_article_variants(ARTICLE_DETAIL_NO_ALTERNATIVES_HTML) == []


def test_parse_article_variants_falls_back_to_teaser_without_body_variables():
    variants = _parse.parse_article_variants(ARTICLE_DETAIL_NO_DATA_VARIABLES_HTML)

    assert variants == ["054821", "051870"]


def test_parse_article_builds_full_tree_from_one_page():
    fetched_at = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    article = _parse.parse_article(ARTICLE_DETAIL_HTML, "051430", fetched_at)

    assert article.material_number == "051430"
    assert article.fetched_at == fetched_at
    assert article.ean == "4016705110575"
    assert article.category_id == "UWG_1_1"
    assert article.own_article_number == "MY-OWN-NUMBER"
    assert article.attributes == {"Farbe": "rot", "Werkstoff": "Kupfer"}
    assert len(article.images) == 1
    assert article.accessories == ["051988", "057288", "053943"]
    assert article.variants == ["054821", "875999", "051870"]
    assert article.alternatives == ["6169773", "9641674"]
    assert article.cross_sell == ["051431", "051432"]
    assert article.documents == []


def test_article_to_dict_is_json_serializable_with_nested_category_and_images():
    fetched_at = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    article = _parse.parse_article(ARTICLE_DETAIL_HTML, "051430", fetched_at)

    as_dict = article.to_dict()
    serialized = json.dumps(as_dict)  # raises if anything isn't JSON-serializable

    reloaded = json.loads(serialized)
    assert reloaded["fetched_at"] == "2026-08-11T12:00:00+00:00"
    assert reloaded["category"] == {"id": "UWG_1_1", "name": "Aderendhülsen"}
    assert reloaded["images"] == [{"url": article.images[0].url, "is_primary": True}]
    assert reloaded["accessories"] == ["051988", "057288", "053943"]


def test_parse_deal_campaigns_handles_variable_length_tiles():
    campaigns = _parse.parse_deal_campaigns(DEAL_CAMPAIGNS_HTML)

    assert len(campaigns) == 2
    assert campaigns[0].campaign_id == "27923"
    assert campaigns[0].title == "Sonderabverkauf Licht"
    assert campaigns[1].campaign_id == "31483"
    assert campaigns[1].title == "Standardtypen von Makita"


def test_parse_cutting_fee_extracts_euro_amount():
    assert _parse.parse_cutting_fee(ARTICLE_DETAIL_WITH_CUTTING_FEE_HTML) == Decimal("9.95")


def test_parse_cutting_fee_returns_none_when_not_mentioned():
    assert _parse.parse_cutting_fee(ARTICLE_DETAIL_HTML) is None


def test_parse_cable_lengths_scopes_rows_to_their_location():
    lengths = _parse.parse_cable_lengths(CABLE_LENGTHS_HTML)

    assert len(lengths) == 3
    assert [entry.location for entry in lengths] == ["Zentrallager", "Zentrallager", "FEGA & Schmitt Erlangen"]

    remainder, full_drum, erlangen = lengths

    assert remainder.packaging == "KTG Trommel"
    assert remainder.is_cuttable is True
    assert remainder.fixed_length_m is None
    assert remainder.count == 1
    assert remainder.total_available_m == Decimal(34)

    assert full_drum.packaging == "Einwegtrommel"
    assert full_drum.is_cuttable is False
    assert full_drum.fixed_length_m == Decimal(500)
    assert full_drum.count == 35
    assert full_drum.total_available_m == Decimal(17500)

    assert erlangen.count == 2
    assert erlangen.total_available_m == Decimal(80)

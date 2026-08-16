"""Tests for WebClient against a mocked HTTP transport (respx).

Covers the session/login machinery (docs/extensions.md, sections 2.2, 2.8)
and the two-request nature of get_article_detail() - not every parser edge
case, which is already covered against real captured markup in
test_web_parse.py.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx
from web_fixtures import (
    ARTICLE_DETAIL_HTML,
    ARTICLE_DETAIL_WITH_CUTTING_FEE_HTML,
    CABLE_LENGTHS_HTML,
    LOGIN_FAILURE_HEADERS,
    LOGIN_SUCCESS_HEADERS,
    SEARCH_RESULTS_HTML,
)

from fega_schmitt_client.web import WebClient
from fega_schmitt_client.web.client import (
    DEFAULT_BASE_URL,
    DEFAULT_LOGIN_PATH,
    DEFAULT_SECOND_CHOICE_DEAL_ID,
    DEFAULT_SHOP_PATH,
)
from fega_schmitt_client.web.exceptions import FegaLoginError

LOGIN_URL = f"{DEFAULT_BASE_URL}{DEFAULT_LOGIN_PATH}"
SHOP_URL = f"{DEFAULT_BASE_URL}{DEFAULT_SHOP_PATH}"
DETAIL_URL = (
    "https://shop.fega.de/product/Kabel-Leitungen--Gummischlauchleitung-H07RN-F-5G16-TR500m-schwarz---121350.html"
)


@respx.mock
def test_search_logs_in_then_fetches_results():
    login_route = respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    results = client.search("121350")

    assert login_route.called
    sent_body = login_route.calls.last.request.content.decode()
    assert "memb_login=9920" in sent_body
    assert "memb_pass=geheim" in sent_body
    assert len(results) == 1
    assert results[0].material_number == "121350"


@respx.mock
def test_login_failure_raises_fega_login_error():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_FAILURE_HEADERS))

    client = WebClient(customer_number="9920", shop_password="falsch")
    with pytest.raises(FegaLoginError):
        client.search("121350")


@respx.mock
def test_expired_session_triggers_relogin_and_retry():
    login_route = respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    responses = iter(
        [
            httpx.Response(302, headers=LOGIN_FAILURE_HEADERS),  # first GET: session considered expired
            httpx.Response(200, text=SEARCH_RESULTS_HTML),  # retry after re-login succeeds
        ]
    )
    respx.get(SHOP_URL).mock(side_effect=lambda request: next(responses))

    client = WebClient(customer_number="9920", shop_password="geheim")
    results = client.search("121350")

    assert login_route.call_count == 2
    assert len(results) == 1


@respx.mock
def test_get_article_detail_searches_then_fetches_detail_page():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    detail = client.get_article_detail("121350")

    assert detail.ean == "4016705110575"
    assert detail.category_id == "UWG_1_1"


@respx.mock
def test_get_article_detail_raises_when_search_finds_nothing():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text="<html><body>keine Treffer</body></html>"))

    client = WebClient(customer_number="9920", shop_password="geheim")
    with pytest.raises(Exception, match="Konnte keine Artikelseite"):
        client.get_article_detail("000000")


@respx.mock
def test_set_article_number_posts_expected_payload():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    post_route = respx.post(SHOP_URL).mock(return_value=httpx.Response(200, text="OK"))

    client = WebClient(customer_number="9920", shop_password="geheim")
    client.set_article_number("051430", "MY-OWN-NUMBER")

    assert post_route.called
    request = post_route.calls.last.request
    assert request.headers["X-Requested-With"] == "XMLHttpRequest"
    body = request.content.decode()
    assert "ownArticleNumber=MY-OWN-NUMBER" in body
    assert "arnr=051430" in body


@respx.mock
def test_get_article_returns_full_tree_from_two_requests():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    search_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    detail_route = respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    article = client.get_article("121350")

    assert search_route.call_count == 1
    assert detail_route.call_count == 1
    assert article.ean == "4016705110575"
    assert article.attributes == {"Farbe": "rot", "Werkstoff": "Kupfer"}
    assert article.accessories == ["051988", "057288", "053943"]
    assert article.images and article.images[0].is_primary
    assert article.documents == []


@respx.mock
def test_get_article_carries_description_over_from_the_search_tile():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    article = client.get_article("121350")

    # The search step happens anyway to find the detail URL; its tile is the
    # only place the article title appears, so it must not be dropped.
    assert article.description == "NEUT Gummischlauchleitung H07RN-F 5G16 TR500m schwarz"


@respx.mock
def test_get_article_category_returns_id_and_name_from_detail_page():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    category_id, category_name = client.get_article_category("121350")

    assert category_id == "UWG_1_1"
    assert category_name == "Aderendhülsen"


@respx.mock
def test_get_article_number_returns_own_article_number():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    own_number = client.get_article_number("121350")

    assert own_number == "MY-OWN-NUMBER"


@respx.mock
def test_get_article_attributes_returns_label_value_pairs():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    attributes = client.get_article_attributes("121350")

    assert attributes == {"Farbe": "rot", "Werkstoff": "Kupfer"}


@respx.mock
def test_get_article_accessories_returns_material_numbers():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    accessories = client.get_article_accessories("121350")

    assert accessories == ["051988", "057288", "053943"]


@respx.mock
def test_get_article_variants_returns_material_numbers():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    variants = client.get_article_variants("121350")

    assert variants == ["054821", "875999", "051870"]


@respx.mock
def test_get_article_alternatives_returns_material_numbers():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    alternatives = client.get_article_alternatives("121350")

    assert alternatives == ["6169773", "9641674"]


@respx.mock
def test_get_article_cross_sell_returns_material_numbers():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    cross_sell = client.get_article_cross_sell("121350")

    assert cross_sell == ["051431", "051432"]


@respx.mock
def test_get_cutting_fee_returns_amount_from_detail_page():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_WITH_CUTTING_FEE_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    fee = client.get_cutting_fee("121350")

    assert fee == Decimal("9.95")


@respx.mock
def test_get_cable_lengths_is_a_single_request_with_material_number_in_cmd():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    shop_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=CABLE_LENGTHS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    lengths = client.get_cable_lengths("104260")

    assert shop_route.call_count == 1
    assert shop_route.calls.last.request.url.params["cmd"] == "AjaxKLaeng/104260"
    assert len(lengths) == 3


@respx.mock
def test_has_cable_lengths_true_when_rows_present():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=CABLE_LENGTHS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")

    assert client.has_cable_lengths("104260") is True


@respx.mock
def test_has_cable_lengths_false_when_no_rows():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text="<div>keine Kabellängen</div>"))

    client = WebClient(customer_number="9920", shop_password="geheim")

    assert client.has_cable_lengths("051430") is False


@respx.mock
def test_list_articles_by_category_sends_hierarchie_cmd_with_mode_list():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    shop_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    results = client.list_articles_by_category("UWG_1_1")

    sent_params = shop_route.calls.last.request.url.params
    assert sent_params["cmd"] == "Hierarchie/UWG_1_1"
    assert sent_params["mode"] == "list"
    assert len(results) == 1
    assert results[0].material_number == "121350"


@respx.mock
def test_get_favorite_list_sends_favorites_cmd():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    shop_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    results = client.get_favorite_list()

    assert shop_route.calls.last.request.url.params["cmd"] == "Favorites/-1"
    assert len(results) == 1


@respx.mock
def test_get_deal_articles_sends_campaign_cmd_with_mode_1():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    shop_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    results = client.get_deal_articles("27923")

    sent_params = shop_route.calls.last.request.url.params
    assert sent_params["cmd"] == "Deal/27923"
    assert sent_params["mode"] == "1"
    assert len(results) == 1


@respx.mock
def test_get_daily_deals_sends_taga_cmd():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    shop_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    results = client.get_daily_deals()

    assert shop_route.calls.last.request.url.params["cmd"] == "TagA"
    assert len(results) == 1


@respx.mock
def test_get_second_choice_articles_sends_default_campaign_and_svc_param():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    shop_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    results = client.get_second_choice_articles()

    sent_params = shop_route.calls.last.request.url.params
    assert sent_params["cmd"] == f"Deal/{DEFAULT_SECOND_CHOICE_DEAL_ID}"
    assert sent_params["mode"] == "1"
    assert sent_params["svc"] == "2Wahl"
    assert len(results) == 1


@respx.mock
def test_get_second_choice_articles_accepts_deal_id_override():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    shop_route = respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    client = WebClient(customer_number="9920", shop_password="geheim")
    client.get_second_choice_articles(deal_id="9999")

    assert shop_route.calls.last.request.url.params["cmd"] == "Deal/9999"

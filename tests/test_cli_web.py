"""Tests for the `fega web` CLI subcommands.

Not exhaustive over all subcommands - the underlying WebClient methods are
already covered in test_web_client.py/test_web_parse.py. This just checks
the CLI wiring itself: argument passing, --json vs. table output, and the
credential/error boundary shared by every subcommand.
"""

from __future__ import annotations

import json

import httpx
import respx
from click.testing import CliRunner
from web_fixtures import (
    ARTICLE_DETAIL_HTML,
    CABLE_LENGTHS_HTML,
    LOGIN_SUCCESS_HEADERS,
    SEARCH_RESULTS_HTML,
)

from fega_schmitt_client.cli import main
from fega_schmitt_client.web.client import DEFAULT_BASE_URL, DEFAULT_LOGIN_PATH, DEFAULT_SHOP_PATH

LOGIN_URL = f"{DEFAULT_BASE_URL}{DEFAULT_LOGIN_PATH}"
SHOP_URL = f"{DEFAULT_BASE_URL}{DEFAULT_SHOP_PATH}"
DETAIL_URL = (
    "https://shop.fega.de/product/Kabel-Leitungen--Gummischlauchleitung-H07RN-F-5G16-TR500m-schwarz---121350.html"
)
CREDENTIALS = ["--customer-number", "9920", "--shop-password", "geheim"]


@respx.mock
def test_web_search_table_output():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    runner = CliRunner()
    result = runner.invoke(main, [*CREDENTIALS, "web", "search", "121350"])

    assert result.exit_code == 0, result.output
    assert "121350" in result.output
    assert "Gummischlauchleitung" in result.output


@respx.mock
def test_web_search_json_output():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))

    runner = CliRunner()
    result = runner.invoke(main, [*CREDENTIALS, "web", "search", "-j", "121350"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["material_number"] == "121350"


@respx.mock
def test_web_article_json_output_matches_article_to_dict():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    runner = CliRunner()
    result = runner.invoke(main, [*CREDENTIALS, "web", "article", "-j", "121350"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ean"] == "4016705110575"
    assert payload["category"] == {"id": "UWG_1_1", "name": "Aderendhülsen"}


@respx.mock
def test_web_article_table_output_summarizes_key_fields():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=SEARCH_RESULTS_HTML))
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=ARTICLE_DETAIL_HTML))

    runner = CliRunner()
    result = runner.invoke(main, [*CREDENTIALS, "web", "article", "121350"])

    assert result.exit_code == 0, result.output
    assert "EAN=4016705110575" in result.output
    assert "Aderendhülsen" in result.output


@respx.mock
def test_web_cable_lengths_table_output():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    respx.get(SHOP_URL).mock(return_value=httpx.Response(200, text=CABLE_LENGTHS_HTML))

    runner = CliRunner()
    result = runner.invoke(main, [*CREDENTIALS, "web", "cable-lengths", "104260"])

    assert result.exit_code == 0, result.output
    assert "Zentrallager" in result.output
    assert "insgesamt 34 m" in result.output
    assert "FEGA & Schmitt Erlangen" in result.output


@respx.mock
def test_web_set_article_number_posts_expected_payload():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(302, headers=LOGIN_SUCCESS_HEADERS))
    post_route = respx.post(SHOP_URL).mock(return_value=httpx.Response(200, text="OK"))

    runner = CliRunner()
    result = runner.invoke(main, [*CREDENTIALS, "web", "set-article-number", "051430", "MY-OWN-NUMBER"])

    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    body = post_route.calls.last.request.content.decode()
    assert "ownArticleNumber=MY-OWN-NUMBER" in body
    assert "arnr=051430" in body


def test_web_requires_credentials():
    runner = CliRunner()
    result = runner.invoke(
        main, ["web", "search", "121350"], env={"FEGA_CUSTOMER_NUMBER": "", "FEGA_SHOP_PASSWORD": ""}
    )

    assert result.exit_code == 2
    assert "erforderlich" in result.output


@respx.mock
def test_web_reports_transport_error():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(500))

    runner = CliRunner()
    result = runner.invoke(main, [*CREDENTIALS, "web", "search", "121350"])

    assert result.exit_code == 1
    assert "Error" in result.output

"""Tests for the `fega` CLI."""

from __future__ import annotations

import json

import httpx
import respx
from click.testing import CliRunner
from fixtures import EXAMPLE_RESPONSE_XML

from fega_schmitt_client.cli import main
from fega_schmitt_client.price_avail import DEFAULT_ENDPOINT


@respx.mock
def test_price_avail_table_output():
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(200, content=EXAMPLE_RESPONSE_XML))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--customer-number", "9920", "--shop-password", "kennwort", "price-avail", "0815:200:MTR"],
    )

    assert result.exit_code == 0, result.output
    assert "0815" in result.output
    assert "status=ok" in result.output


@respx.mock
def test_price_avail_json_output():
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(200, content=EXAMPLE_RESPONSE_XML))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--customer-number", "9920", "--shop-password", "kennwort", "price-avail", "-j", "0815"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["material_number"] == "0815"
    assert payload[0]["net_amount"] == "67.54"


@respx.mock
def test_price_avail_reports_transport_error():
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(500))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--customer-number", "9920", "--shop-password", "kennwort", "price-avail", "0815"],
    )

    assert result.exit_code == 1
    assert "Error" in result.output


def test_price_avail_requires_credentials():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["price-avail", "0815"],
        env={"FEGA_CUSTOMER_NUMBER": "", "FEGA_SHOP_PASSWORD": ""},
    )

    assert result.exit_code == 2
    assert "erforderlich" in result.output


def test_price_avail_rejects_invalid_quantity():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--customer-number", "9920", "--shop-password", "kennwort", "price-avail", "0815:not-a-number"],
    )

    assert result.exit_code == 2
    assert "Ungültige Menge" in result.output

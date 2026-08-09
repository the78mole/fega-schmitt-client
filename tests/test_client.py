"""Tests for FegaSchmittClient against a mocked HTTP transport (respx)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx
from fixtures import EXAMPLE_RESPONSE_XML

from fega_schmitt_client import FegaSchmittClient, PriceAvailRequestItem
from fega_schmitt_client.exceptions import FegaAuthError, FegaTransportError
from fega_schmitt_client.price_avail import DEFAULT_ENDPOINT, MAX_ITEMS


@respx.mock
def test_get_price_availability_returns_parsed_items():
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(200, content=EXAMPLE_RESPONSE_XML))

    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="kennwort")
    results = client.get_price_availability(
        [PriceAvailRequestItem(material_number="0815", quantity=Decimal(200), unit="MTR")]
    )

    assert len(results) == 3
    assert results[0].material_number == "0815"
    assert results[0].net_amount == Decimal("67.54")
    assert results[2].status == "error"


@respx.mock
def test_get_price_availability_sends_credentials_in_request_body():
    route = respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(200, content=EXAMPLE_RESPONSE_XML))

    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="geheim")
    client.get_price_availability([PriceAvailRequestItem(material_number="0815", quantity=1)])

    sent_body = route.calls.last.request.content.decode("ISO-8859-1")
    assert "PARTNER_PURCHASER>9920<" in sent_body
    assert "LEGITIMATION_ID>geheim<" in sent_body


@respx.mock
def test_get_price_availability_raises_auth_error_on_401():
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(401))

    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="falsch")
    with pytest.raises(FegaAuthError):
        client.get_price_availability([PriceAvailRequestItem(material_number="0815", quantity=1)])


@respx.mock
def test_get_price_availability_raises_transport_error_on_5xx():
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(500))

    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="kennwort")
    with pytest.raises(FegaTransportError):
        client.get_price_availability([PriceAvailRequestItem(material_number="0815", quantity=1)])


@respx.mock
def test_get_price_availability_raises_transport_error_on_timeout():
    respx.post(DEFAULT_ENDPOINT).mock(side_effect=httpx.TimeoutException("timed out"))

    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="kennwort")
    with pytest.raises(FegaTransportError):
        client.get_price_availability([PriceAvailRequestItem(material_number="0815", quantity=1)])


@respx.mock
def test_get_price_availability_rejects_malformed_response_body():
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(200, content=b"not xml"))

    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="kennwort")
    with pytest.raises(FegaTransportError):
        client.get_price_availability([PriceAvailRequestItem(material_number="0815", quantity=1)])


def test_get_price_availability_rejects_empty_items():
    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="kennwort")
    with pytest.raises(ValueError):
        client.get_price_availability([])


def test_get_price_availability_rejects_too_many_items():
    client = FegaSchmittClient(partner_purchaser="9920", legitimation_id="kennwort")
    items = [PriceAvailRequestItem(material_number=str(i), quantity=1) for i in range(MAX_ITEMS + 1)]
    with pytest.raises(ValueError):
        client.get_price_availability(items)

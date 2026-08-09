"""Tests for the low-level SOAP envelope building/parsing in _soap.py."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fixtures import EXAMPLE_RESPONSE_XML

from fega_schmitt_client._soap import build_request, parse_response
from fega_schmitt_client.exceptions import FegaTransportError
from fega_schmitt_client.models import PriceAvailRequestItem


def _build(items: list[PriceAvailRequestItem]) -> str:
    return build_request(
        items,
        partner_purchaser="9920",
        legitimation_id="kennwort",
        partner_company="50",
        transaction_id="N001",
    ).decode("ISO-8859-1")


def test_build_request_contains_expected_fields():
    items = [PriceAvailRequestItem(material_number="TEST123", quantity=Decimal(1), unit="MTR")]
    xml_text = _build(items)

    assert "PARTNER_PURCHASER>9920<" in xml_text
    assert "LEGITIMATION_ID>kennwort<" in xml_text
    assert "TRANSACTION_ID>N001<" in xml_text
    assert "MATERIAL_NUMBER>TEST123<" in xml_text
    assert "REQUEST_QUANTITY>1<" in xml_text
    assert "REQUEST_UNIT>MTR<" in xml_text
    assert "PRICE_AVAIL_REQUEST" in xml_text


def test_build_request_assigns_sequential_line_item_numbers():
    items = [
        PriceAvailRequestItem(material_number="A", quantity=1),
        PriceAvailRequestItem(material_number="B", quantity=2),
    ]
    xml_text = _build(items)

    assert "LINE_ITEM_NUMBER>1<" in xml_text
    assert "LINE_ITEM_NUMBER>2<" in xml_text


def test_build_request_honors_explicit_line_item_number():
    items = [PriceAvailRequestItem(material_number="A", quantity=1, line_item_number=42)]
    xml_text = _build(items)

    assert "LINE_ITEM_NUMBER>42<" in xml_text


def test_build_request_formats_decimal_quantity_without_trailing_zeros():
    items = [PriceAvailRequestItem(material_number="A", quantity=Decimal("5.50"))]
    xml_text = _build(items)

    assert "REQUEST_QUANTITY>5.5<" in xml_text


def test_build_request_omits_partner_warehouse_by_default():
    items = [PriceAvailRequestItem(material_number="A", quantity=1)]
    xml_text = _build(items)

    assert "<PARTNER_WAREHOUSE />" in xml_text


def test_build_request_includes_partner_warehouse_when_set():
    items = [PriceAvailRequestItem(material_number="A", quantity=1)]
    xml_text = build_request(
        items,
        partner_purchaser="9920",
        legitimation_id="kennwort",
        partner_company="50",
        transaction_id="N001",
        partner_warehouse="22",
    ).decode("ISO-8859-1")

    assert "PARTNER_WAREHOUSE>22<" in xml_text


@pytest.mark.parametrize("invalid_value", ["", "12345", "22a", "Erlangen", "-1", "1.0"])
def test_build_request_rejects_invalid_partner_warehouse(invalid_value):
    items = [PriceAvailRequestItem(material_number="A", quantity=1)]
    with pytest.raises(ValueError):
        build_request(
            items,
            partner_purchaser="9920",
            legitimation_id="kennwort",
            partner_company="50",
            transaction_id="N001",
            partner_warehouse=invalid_value,
        )


def test_parse_response_example_from_spec_appendix():
    parsed = parse_response(EXAMPLE_RESPONSE_XML)

    assert parsed.transaction_id == "testtest"
    assert len(parsed.items) == 3

    ok_item = parsed.items[0]
    assert ok_item.line_item_number == 1
    assert ok_item.material_number == "0815"
    assert ok_item.status == "ok"
    assert ok_item.return_code == "I010"
    assert ok_item.availability_status == "V"
    assert ok_item.warehouse_number == "22"
    assert ok_item.warehouse_name == "Zentrallager"
    assert ok_item.price_amount == Decimal("36.90")
    assert ok_item.net_amount == Decimal("67.54")
    assert ok_item.list_amount == Decimal("135.80")
    assert len(ok_item.surcharges) == 1
    assert ok_item.surcharges[0].code == "1"
    assert ok_item.surcharges[0].text == "Kupferzuschlag"
    assert ok_item.surcharges[0].amount == Decimal("30.64")

    backorder_item = parsed.items[1]
    assert backorder_item.availability_status == "B"
    assert backorder_item.surcharges == []

    error_item = parsed.items[2]
    assert error_item.status == "error"
    assert error_item.return_code == "E106"
    assert error_item.return_code_text == "Artikel ist gelöscht"
    assert error_item.availability_status is None
    assert error_item.price_amount is None


def test_parse_response_hint_return_code_maps_to_hint_status():
    xml = EXAMPLE_RESPONSE_XML.decode("ISO-8859-1").replace("I010", "H014", 1).encode("ISO-8859-1")

    parsed = parse_response(xml)

    assert parsed.items[0].status == "hint"


def test_parse_response_rejects_malformed_xml():
    with pytest.raises(FegaTransportError):
        parse_response(b"not xml")


def test_parse_response_tolerates_bare_ampersand_in_warehouse_name():
    # Observed live from FEGA & Schmitt: PARTNER_WAREHOUSE_NAME can contain an
    # unescaped "&" (e.g. "FEGA & Schmitt Erlangen"), making the XML technically
    # invalid. parse_response() should repair and parse it anyway.
    xml = (
        EXAMPLE_RESPONSE_XML.decode("ISO-8859-1")
        .replace(
            "<PARTNER_WAREHOUSE_NAME>Zentrallager</PARTNER_WAREHOUSE_NAME>",
            "<PARTNER_WAREHOUSE_NAME>FEGA & Schmitt Erlangen</PARTNER_WAREHOUSE_NAME>",
            1,
        )
        .encode("ISO-8859-1")
    )

    parsed = parse_response(xml)

    assert parsed.items[0].warehouse_name == "FEGA & Schmitt Erlangen"


def test_parse_response_still_rejects_xml_broken_for_other_reasons():
    xml = EXAMPLE_RESPONSE_XML.decode("ISO-8859-1").replace("</ITEM_LIST>", "", 1).encode("ISO-8859-1")
    with pytest.raises(FegaTransportError):
        parse_response(xml)


def test_parse_response_rejects_missing_body():
    envelope_without_body = (
        b'<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"/>'
    )
    with pytest.raises(FegaTransportError):
        parse_response(envelope_without_body)

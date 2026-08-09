"""Tests for the low-level Warenkorb XML building/parsing in ids/_xml.py."""

from __future__ import annotations

from decimal import Decimal

from fega_schmitt_client.ids._xml import build_warenkorb_xml, parse_warenkorb_xml
from fega_schmitt_client.ids.models import (
    Address,
    Cart,
    CartItem,
    CustomerInfo,
    OrderInfo,
    RawMaterialShare,
    SupplierInfo,
)


def _sample_cart() -> Cart:
    return Cart(
        items=[
            CartItem(
                article_number="TEST123",
                quantity=Decimal(50),
                unit="MTR",
                ref_customer="1",
                short_text="50 Meter Ring Kabel",
                net_price=Decimal("522.00"),
                offer_price=Decimal("10000.00"),
                price_basis=Decimal(1000),
                raw_material_shares=[
                    RawMaterialShare(
                        raw_material="CU",
                        weight_share_value=Decimal(96),
                        weight_share_unit="KGM",
                        basis_value=Decimal(100),
                        basis_unit="MTR",
                        basis_quote=Decimal(150),
                        current_quote=Decimal(300),
                    )
                ],
            ),
        ],
        order_info=OrderInfo(mode_of_shipment="Lieferung", commission="Baustelle Musterweg"),
        supplier_info=SupplierInfo(id_no="50", address=Address(name1="FEGA & Schmitt", city="Nürnberg")),
        customer_info=CustomerInfo(id_no="9920", address=Address(name1="Mustermann GmbH", city="Erlangen")),
    )


def test_build_warenkorb_xml_contains_expected_tags():
    xml_text = build_warenkorb_xml(_sample_cart()).decode("utf-8")

    assert "<Warenkorb>" in xml_text
    assert "<Version>2.5</Version>" in xml_text
    assert "<ModeOfShipment>Lieferung</ModeOfShipment>" in xml_text
    assert "<ArtNo>TEST123</ArtNo>" in xml_text
    assert "<Qty>50</Qty>" in xml_text
    assert "<QU>MTR</QU>" in xml_text
    assert "<Rohstoff>CU</Rohstoff>" in xml_text
    assert "<Gewichtsanteilswert>96</Gewichtsanteilswert>" in xml_text


def test_build_warenkorb_xml_never_emits_rueckgabekz():
    cart = _sample_cart()
    cart.return_flag = "Warenkorbrückgabe"

    xml_text = build_warenkorb_xml(cart).decode("utf-8")

    assert "RueckgabeKZ" not in xml_text


def test_round_trip_preserves_item_and_address_fields():
    original = _sample_cart()

    parsed = parse_warenkorb_xml(build_warenkorb_xml(original))

    assert len(parsed.items) == 1
    item = parsed.items[0]
    assert item.article_number == "TEST123"
    assert item.quantity == Decimal(50)
    assert item.unit == "MTR"
    assert item.ref_customer == "1"
    assert item.short_text == "50 Meter Ring Kabel"
    assert item.net_price == Decimal("522.00")
    assert len(item.raw_material_shares) == 1
    assert item.raw_material_shares[0].raw_material == "CU"
    assert item.raw_material_shares[0].current_quote == Decimal(300)

    assert parsed.order_info.mode_of_shipment == "Lieferung"
    assert parsed.order_info.commission == "Baustelle Musterweg"
    assert parsed.supplier_info.id_no == "50"
    assert parsed.supplier_info.address.name1 == "FEGA & Schmitt"
    assert parsed.customer_info.address.city == "Erlangen"


def test_parse_warenkorb_xml_reads_rueckgabekz_from_response():
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<Warenkorb><WarenkorbInfo><RueckgabeKZ>Warenkorbr\xc3\xbcckgabe</RueckgabeKZ>"
        b"<Version>2.5</Version></WarenkorbInfo>"
        b"<Order><OrderInfo><ModeOfShipment>Lieferung</ModeOfShipment></OrderInfo></Order></Warenkorb>"
    )

    parsed = parse_warenkorb_xml(xml)

    assert parsed.return_flag == "Warenkorbrückgabe"
    assert parsed.items == []


def test_build_warenkorb_xml_omits_optional_blocks_when_absent():
    cart = Cart(items=[CartItem(article_number="A", quantity=1, unit="PCE")])

    xml_text = build_warenkorb_xml(cart).decode("utf-8")

    assert "SupplierInfo" not in xml_text
    assert "CustomerInfo" not in xml_text
    assert "DeliveryPlaceInfo" not in xml_text
    assert "Rohstoffanteil" not in xml_text

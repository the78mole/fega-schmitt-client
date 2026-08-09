"""Tests for the high-level IDS cart request/callback helpers in ids/cart.py."""

from __future__ import annotations

from decimal import Decimal

from fega_schmitt_client.ids import build_cart_request, parse_cart_callback
from fega_schmitt_client.ids.models import Cart, CartItem

SHOP_URL = "https://shop.fega.de/ids"


def _cart() -> Cart:
    return Cart(items=[CartItem(article_number="0815", quantity=Decimal(2), unit="PCE")])


def test_build_cart_request_includes_warenkorb_xml_and_action():
    request = build_cart_request(_cart(), shop_url=SHOP_URL)

    assert request.shop_url == SHOP_URL
    assert request.method == "POST"
    assert request.fields["action"] == "WKS"
    assert request.fields["version"] == "2.5"
    assert "<ArtNo>0815</ArtNo>" in request.fields["warenkorb"]


def test_build_cart_request_hook_url_is_optional():
    without_hook = build_cart_request(_cart(), shop_url=SHOP_URL)
    assert "hookurl" not in without_hook.fields

    with_hook = build_cart_request(_cart(), shop_url=SHOP_URL, hook_url="https://my-server.example/fega-hook")
    assert with_hook.fields["hookurl"] == "https://my-server.example/fega-hook"


def test_build_cart_request_includes_credentials_when_given():
    request = build_cart_request(
        _cart(),
        shop_url=SHOP_URL,
        customer_number="9920",
        username="user",
        password="secret",
    )

    assert request.fields["kndnr"] == "9920"
    assert request.fields["name_kunde"] == "user"
    assert request.fields["pw_kunde"] == "secret"


def test_build_cart_request_omits_credentials_when_not_given():
    request = build_cart_request(_cart(), shop_url=SHOP_URL)

    assert "kndnr" not in request.fields
    assert "name_kunde" not in request.fields
    assert "pw_kunde" not in request.fields


def test_parse_cart_callback_accepts_str_and_bytes():
    xml_str = (
        '<?xml version="1.0" encoding="UTF-8"?><Warenkorb><WarenkorbInfo><Version>2.5</Version>'
        "</WarenkorbInfo><Order><OrderInfo><ModeOfShipment>Lieferung</ModeOfShipment></OrderInfo>"
        "<OrderItem><ArtNo>0815</ArtNo><Qty>2</Qty><QU>PCE</QU></OrderItem></Order></Warenkorb>"
    )

    from_str = parse_cart_callback(xml_str)
    from_bytes = parse_cart_callback(xml_str.encode("utf-8"))

    assert from_str.items[0].article_number == "0815"
    assert from_bytes.items[0].article_number == "0815"

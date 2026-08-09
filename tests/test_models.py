"""Tests for the data model in models.py."""

from __future__ import annotations

from decimal import Decimal

from fega_schmitt_client.models import PriceAvailRequestItem


def test_quantity_int_is_coerced_to_decimal():
    item = PriceAvailRequestItem(material_number="0815", quantity=200)
    assert item.quantity == Decimal(200)
    assert isinstance(item.quantity, Decimal)


def test_quantity_float_is_coerced_to_decimal():
    item = PriceAvailRequestItem(material_number="0815", quantity=5.5)
    assert item.quantity == Decimal("5.5")


def test_quantity_decimal_is_kept_as_is():
    quantity = Decimal("12.34")
    item = PriceAvailRequestItem(material_number="0815", quantity=quantity)
    assert item.quantity is quantity

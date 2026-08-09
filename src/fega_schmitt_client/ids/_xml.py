"""Low-level Warenkorb XML building/parsing for the IDS interface.

Internal module - not part of the public API. Field names and structure
follow docs/specs/IDS_Schnittstelle_2_5_final_NEU.pdf, section 7.1. Unlike
the SOAP price/availability service, this is plain XML (no SOAP envelope)
and defaults to UTF-8 per the spec ("Wird nichts angegeben, so wird utf-8
genutzt").
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date as _date_cls
from decimal import Decimal, InvalidOperation

from .models import (
    Address,
    Cart,
    CartItem,
    CustomerInfo,
    DeliveryPlaceInfo,
    OrderInfo,
    RawMaterialShare,
    SupplierInfo,
)


def build_warenkorb_xml(cart: Cart) -> bytes:
    """Build a ``Warenkorb`` XML document as UTF-8-encoded bytes.

    Never emits ``WarenkorbInfo/RueckgabeKZ`` - the spec forbids sending it
    ("kann nicht übertragen werden"), it is only meaningful on a received cart.
    """
    root = ET.Element("Warenkorb")

    info_el = ET.SubElement(root, "WarenkorbInfo")
    if cart.date is not None:
        _add_text(info_el, "Date", cart.date.isoformat())
    if cart.time is not None:
        _add_text(info_el, "Time", cart.time.isoformat(timespec="seconds"))
    _add_text(info_el, "Version", "2.5")

    order_el = ET.SubElement(root, "Order")
    _build_order_info(ET.SubElement(order_el, "OrderInfo"), cart.order_info)

    if cart.supplier_info is not None:
        _build_supplier_info(ET.SubElement(order_el, "SupplierInfo"), cart.supplier_info)
    if cart.customer_info is not None:
        _build_customer_info(ET.SubElement(order_el, "CustomerInfo"), cart.customer_info)
    if cart.delivery_place_info is not None:
        _build_delivery_place_info(ET.SubElement(order_el, "DeliveryPlaceInfo"), cart.delivery_place_info)

    for item in cart.items:
        _build_order_item(ET.SubElement(order_el, "OrderItem"), item)

    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def parse_warenkorb_xml(xml_bytes: bytes) -> Cart:
    """Parse a ``Warenkorb`` XML document (as received via the Hook-URL callback)."""
    root = ET.fromstring(xml_bytes)

    info_el = root.find("WarenkorbInfo")
    order_el = root.find("Order")

    order_info_el = order_el.find("OrderInfo") if order_el is not None else None
    supplier_el = order_el.find("SupplierInfo") if order_el is not None else None
    customer_el = order_el.find("CustomerInfo") if order_el is not None else None
    delivery_el = order_el.find("DeliveryPlaceInfo") if order_el is not None else None
    item_els = order_el.findall("OrderItem") if order_el is not None else []

    return Cart(
        items=[_parse_order_item(el) for el in item_els],
        order_info=_parse_order_info(order_info_el),
        supplier_info=_parse_supplier_info(supplier_el),
        customer_info=_parse_customer_info(customer_el),
        delivery_place_info=_parse_delivery_place_info(delivery_el),
        date=None,
        time=None,
        return_flag=_text(info_el, "RueckgabeKZ"),
    )


# --- OrderInfo -----------------------------------------------------------


def _build_order_info(el: ET.Element, order_info: OrderInfo) -> None:
    _add_text(el, "InquiryNo", order_info.inquiry_no)
    _add_text(el, "OfferNo", order_info.offer_no)
    _add_text(el, "PartNo", order_info.part_no)
    _add_text(el, "OrderConfNo", order_info.order_conf_no)
    if order_info.delivery_week is not None:
        _add_text(el, "DeliveryWeek", str(order_info.delivery_week))
    if order_info.delivery_year is not None:
        _add_text(el, "DeliveryYear", str(order_info.delivery_year))
    if order_info.delivery_date is not None:
        _add_text(el, "DeliveryDate", order_info.delivery_date.isoformat())
    _add_text(el, "ModeOfShipment", order_info.mode_of_shipment)
    _add_text(el, "Cur", order_info.currency)
    _add_text(el, "ZusatzText", order_info.additional_text)
    _add_text(el, "Kommission", order_info.commission)


def _parse_order_info(el: ET.Element | None) -> OrderInfo:
    delivery_week = _text(el, "DeliveryWeek")
    delivery_year = _text(el, "DeliveryYear")
    delivery_date = _text(el, "DeliveryDate")
    return OrderInfo(
        mode_of_shipment=_text(el, "ModeOfShipment") or "Lieferung",
        inquiry_no=_text(el, "InquiryNo"),
        offer_no=_text(el, "OfferNo"),
        part_no=_text(el, "PartNo"),
        order_conf_no=_text(el, "OrderConfNo"),
        delivery_week=int(delivery_week) if delivery_week else None,
        delivery_year=int(delivery_year) if delivery_year else None,
        delivery_date=_date(delivery_date),
        currency=_text(el, "Cur"),
        additional_text=_text(el, "ZusatzText"),
        commission=_text(el, "Kommission"),
    )


# --- Address ---------------------------------------------------------------


def _build_address(el: ET.Element, address: Address) -> None:
    _add_text(el, "Name1", address.name1)
    _add_text(el, "Name2", address.name2)
    _add_text(el, "Name3", address.name3)
    _add_text(el, "Name4", address.name4)
    _add_text(el, "Street", address.street)
    _add_text(el, "PCode", address.postal_code)
    _add_text(el, "City", address.city)
    _add_text(el, "Country", address.country)
    _add_text(el, "ILN", address.iln)
    _add_text(el, "Contact", address.contact)
    _add_text(el, "Phone", address.phone)
    _add_text(el, "Fax", address.fax)
    _add_text(el, "Email", address.email)


def _parse_address(el: ET.Element | None) -> Address | None:
    if el is None:
        return None
    return Address(
        name1=_text(el, "Name1"),
        name2=_text(el, "Name2"),
        name3=_text(el, "Name3"),
        name4=_text(el, "Name4"),
        street=_text(el, "Street"),
        postal_code=_text(el, "PCode"),
        city=_text(el, "City"),
        country=_text(el, "Country"),
        iln=_text(el, "ILN"),
        contact=_text(el, "Contact"),
        phone=_text(el, "Phone"),
        fax=_text(el, "Fax"),
        email=_text(el, "Email"),
    )


def _build_supplier_info(el: ET.Element, supplier_info: SupplierInfo) -> None:
    _add_text(el, "IDNo", supplier_info.id_no)
    if supplier_info.address is not None:
        _build_address(ET.SubElement(el, "Address"), supplier_info.address)


def _parse_supplier_info(el: ET.Element | None) -> SupplierInfo | None:
    if el is None:
        return None
    return SupplierInfo(id_no=_text(el, "IDNo"), address=_parse_address(el.find("Address")))


def _build_customer_info(el: ET.Element, customer_info: CustomerInfo) -> None:
    _add_text(el, "IDNo", customer_info.id_no)
    if customer_info.address is not None:
        _build_address(ET.SubElement(el, "Address"), customer_info.address)


def _parse_customer_info(el: ET.Element | None) -> CustomerInfo | None:
    if el is None:
        return None
    return CustomerInfo(id_no=_text(el, "IDNo"), address=_parse_address(el.find("Address")))


def _build_delivery_place_info(el: ET.Element, delivery_place_info: DeliveryPlaceInfo) -> None:
    if delivery_place_info.address is not None:
        _build_address(ET.SubElement(el, "Address"), delivery_place_info.address)


def _parse_delivery_place_info(el: ET.Element | None) -> DeliveryPlaceInfo | None:
    if el is None:
        return None
    return DeliveryPlaceInfo(address=_parse_address(el.find("Address")))


# --- OrderItem / Rohstoffanteil --------------------------------------------


def _build_order_item(el: ET.Element, item: CartItem) -> None:
    _add_text(el, "ItemChara", item.item_type)
    if item.ref_customer or item.ref_customer_sub_no or item.ref_supplier or item.ref_supplier_sub_no:
        ref_el = ET.SubElement(el, "RefItems")
        _add_text(ref_el, "Customer", item.ref_customer)
        _add_text(ref_el, "CustomerSubNo", item.ref_customer_sub_no)
        _add_text(ref_el, "Supplier", item.ref_supplier)
        _add_text(ref_el, "SupplierSubNo", item.ref_supplier_sub_no)
    _add_text(el, "EAN", item.ean)
    _add_text(el, "ManufacturerID", item.manufacturer_id)
    _add_text(el, "ManufacturerIDType", item.manufacturer_id_type)
    _add_text(el, "ArtNo", item.article_number)
    _add_text(el, "Qty", _format_decimal(item.quantity))
    _add_text(el, "QU", item.unit)
    _add_text(el, "Kurztext", item.short_text)
    _add_text(el, "Langtext", item.long_text)
    if item.offer_price is not None:
        _add_text(el, "OfferPrice", _format_decimal(item.offer_price))
    if item.net_price is not None:
        _add_text(el, "NetPrice", _format_decimal(item.net_price))
    if item.price_basis is not None:
        _add_text(el, "PriceBasis", _format_decimal(item.price_basis))
    if item.vat is not None:
        _add_text(el, "VAT", _format_decimal(item.vat))
    if item.techn_clarification is not None:
        _add_text(el, "TechnClarification", "Yes" if item.techn_clarification else "No")
    _add_text(el, "Hinweis", item.hint)
    if item.error_code is not None:
        _add_text(el, "Fehlercode", str(item.error_code))
    _add_text(el, "Fehlertext", item.error_text)
    if item.surcharge_percent is not None:
        _add_text(el, "Zuschlag", _format_decimal(item.surcharge_percent))
    for share in item.raw_material_shares:
        _build_raw_material_share(ET.SubElement(el, "Rohstoffanteil"), share)
    if item.diverse is not None:
        _add_text(el, "Divers", "true" if item.diverse else "false")


def _parse_order_item(el: ET.Element) -> CartItem:
    ref_el = el.find("RefItems")
    error_code = _text(el, "Fehlercode")
    techn_clarification = _text(el, "TechnClarification")
    diverse = _text(el, "Divers")

    return CartItem(
        article_number=_text(el, "ArtNo") or "",
        quantity=_decimal(_text(el, "Qty")) or Decimal(0),
        unit=_text(el, "QU") or "",
        item_type=_text(el, "ItemChara"),
        ref_customer=_text(ref_el, "Customer"),
        ref_customer_sub_no=_text(ref_el, "CustomerSubNo"),
        ref_supplier=_text(ref_el, "Supplier"),
        ref_supplier_sub_no=_text(ref_el, "SupplierSubNo"),
        ean=_text(el, "EAN"),
        manufacturer_id=_text(el, "ManufacturerID"),
        manufacturer_id_type=_text(el, "ManufacturerIDType"),
        short_text=_text(el, "Kurztext"),
        long_text=_text(el, "Langtext"),
        offer_price=_decimal(_text(el, "OfferPrice")),
        net_price=_decimal(_text(el, "NetPrice")),
        price_basis=_decimal(_text(el, "PriceBasis")),
        vat=_decimal(_text(el, "VAT")),
        techn_clarification=(techn_clarification == "Yes") if techn_clarification is not None else None,
        hint=_text(el, "Hinweis"),
        error_code=int(error_code) if error_code else None,
        error_text=_text(el, "Fehlertext"),
        surcharge_percent=_decimal(_text(el, "Zuschlag")),
        raw_material_shares=[_parse_raw_material_share(e) for e in el.findall("Rohstoffanteil")],
        diverse=(diverse == "true") if diverse is not None else None,
    )


def _build_raw_material_share(el: ET.Element, share: RawMaterialShare) -> None:
    _add_text(el, "Rohstoff", share.raw_material)
    _add_text(el, "Gewichtsanteilswert", _format_decimal(share.weight_share_value))
    _add_text(el, "Gewichtsanteilseinheit", share.weight_share_unit)
    _add_text(el, "Basiswert", _format_decimal(share.basis_value))
    _add_text(el, "Basiseinheit", share.basis_unit)
    if share.basis_quote is not None:
        _add_text(el, "Basisnotierung", _format_decimal(share.basis_quote))
    if share.current_quote is not None:
        _add_text(el, "NotierungAktuell", _format_decimal(share.current_quote))


def _parse_raw_material_share(el: ET.Element) -> RawMaterialShare:
    return RawMaterialShare(
        raw_material=_text(el, "Rohstoff") or "",
        weight_share_value=_decimal(_text(el, "Gewichtsanteilswert")) or Decimal(0),
        weight_share_unit=_text(el, "Gewichtsanteilseinheit") or "",
        basis_value=_decimal(_text(el, "Basiswert")) or Decimal(0),
        basis_unit=_text(el, "Basiseinheit") or "",
        basis_quote=_decimal(_text(el, "Basisnotierung")),
        current_quote=_decimal(_text(el, "NotierungAktuell")),
    )


# --- shared helpers ----------------------------------------------------------


def _add_text(parent: ET.Element, tag: str, value: str | None) -> None:
    if value is None:
        return
    el = ET.SubElement(parent, tag)
    el.text = value


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _text(parent: ET.Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    el = parent.find(tag)
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _date(value: str | None):
    if value is None:
        return None
    return _date_cls.fromisoformat(value)

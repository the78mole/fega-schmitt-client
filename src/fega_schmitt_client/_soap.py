"""Low-level SOAP envelope building/parsing for the price/availability service.

Internal module - not part of the public API (see docs/architecture.md,
section 2). Field names and structure follow
docs/specs/Schnittstellenbeschreibung_SOAP.pdf, sections 3.2/3.3.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .exceptions import FegaTransportError
from .models import PriceAvailRequestItem, PriceAvailResultItem, Surcharge

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
REQUEST_NS = "https://soap.fega.de/priceavail.php"

ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("a", REQUEST_NS)

# Spec section 3.2 lists PARTNER_WAREHOUSE as "anum 4", but it's a Lagernummer
# (warehouse number) - every example in the spec (incl. the response's
# AVAILABILITY_PARTNER_WAREHOUSE, e.g. "22") is purely numeric, so we validate
# it as such here to fail fast instead of letting the server reject it.
_PARTNER_WAREHOUSE_RE = re.compile(r"^\d{1,4}$")

# Observed live: FEGA's server sometimes writes bare "&" into PARTNER_WAREHOUSE_NAME
# (e.g. "FEGA & Schmitt Erlangen"), which is invalid XML. We only fall back to
# this repair when strict parsing fails, so well-formed responses are untouched.
_BARE_AMPERSAND_RE = re.compile(rb"&(?!amp;|lt;|gt;|quot;|apos;|#)")


@dataclass
class ParsedResponse:
    transaction_id: str | None
    items: list[PriceAvailResultItem]


def build_request(
    items: list[PriceAvailRequestItem],
    *,
    partner_purchaser: str,
    legitimation_id: str,
    partner_company: str,
    transaction_id: str,
    eshop_id: str | None = None,
    shipment_type: str = "01",
    partner_warehouse: str | None = None,
    request_currency: str = "EUR",
    postal_code: str | None = None,
    country_code: str | None = None,
) -> bytes:
    """Build a ``PRICE_AVAIL_REQUEST`` SOAP envelope as ISO-8859-1-encoded bytes.

    ``partner_warehouse`` is the FEGA & Schmitt Lagernummer per spec (a
    numeric warehouse *number*, max. 4 digits - not a location name such as
    "Erlangen"), sent as ``PARTNER_WAREHOUSE`` in the request ``HEADER``. It
    only matters when ``shipment_type="02"`` (Abholung/pickup) and is meant
    to let the caller ask for a pickup warehouse other than FEGA & Schmitt's
    default one; for delivery (``shipment_type="01"``, the default) or when
    left unset, the request uses the standard warehouse. Raises
    :class:`ValueError` if set to anything other than 1-4 digits.

    Caution: live testing against one account showed every value from "1" to
    "30" resolving to the same warehouse (the account's home/default one) -
    only omitting the field (delivery) gave a different one. It may be that
    this field is a per-customer index into that customer's assigned
    warehouses rather than a global Lagernummer, and this account only has
    one assigned warehouse - unconfirmed. Don't assume a specific numeric
    value reliably selects a specific warehouse without verifying against
    the target account first.
    """
    if partner_warehouse is not None and not _PARTNER_WAREHOUSE_RE.fullmatch(partner_warehouse):
        raise ValueError(
            "partner_warehouse muss eine numerische Lagernummer mit maximal 4 Ziffern sein, "
            f"erhalten: {partner_warehouse!r}"
        )

    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    request = ET.SubElement(body, f"{{{REQUEST_NS}}}PRICE_AVAIL_REQUEST")

    prefix = ET.SubElement(request, "PREFIX")
    _add_text(prefix, "ESHOP_ID", eshop_id)
    _add_text(prefix, "TRANSACTION_ID", transaction_id)
    _add_text(prefix, "PARTNER_COMPANY", partner_company)
    _add_text(prefix, "PARTNER_COMPANY_PART", None)
    _add_text(prefix, "PARTNER_PURCHASER", partner_purchaser)
    _add_text(prefix, "LEGITIMATION_ID", legitimation_id)

    header = ET.SubElement(request, "HEADER")
    _add_text(header, "SHIPMENT_TYPE", shipment_type)
    _add_text(header, "PARTNER_WAREHOUSE", partner_warehouse)
    _add_text(header, "REQUEST_CURRENCY", request_currency)
    _add_text(header, "POSTAL_CODE", postal_code)
    _add_text(header, "COUNTRY_CODE", country_code)

    item_list = ET.SubElement(request, "ITEM_LIST")
    for index, item in enumerate(items, start=1):
        item_el = ET.SubElement(item_list, "ITEM")
        _add_text(item_el, "LINE_ITEM_NUMBER", str(item.line_item_number or index))
        _add_text(item_el, "MATERIAL_NUMBER", item.material_number)
        _add_text(item_el, "REQUEST_QUANTITY", _format_quantity(item.quantity))
        _add_text(item_el, "REQUEST_UNIT", item.unit)

    return ET.tostring(envelope, encoding="ISO-8859-1", xml_declaration=True)


def parse_response(xml_bytes: bytes) -> ParsedResponse:
    """Parse a ``PRICE_AVAIL_RESPONSE`` SOAP envelope into result items.

    Tolerates one known FEGA & Schmitt server quirk: bare ``&`` characters in
    text content (seen in ``PARTNER_WAREHOUSE_NAME`` values like "FEGA &
    Schmitt Erlangen") that make the response technically invalid XML. If
    strict parsing fails, we retry once with bare ``&`` escaped to ``&amp;``.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        try:
            root = ET.fromstring(_BARE_AMPERSAND_RE.sub(b"&amp;", xml_bytes))
        except ET.ParseError as exc:
            raise FegaTransportError(f"Ungültiges SOAP-XML in der Antwort: {exc}") from exc

    body = root.find(f"{{{SOAP_NS}}}Body")
    if body is None:
        raise FegaTransportError("SOAP-Antwort enthält kein <soap:Body>-Element")

    response_el = next(iter(body), None)
    if response_el is None:
        raise FegaTransportError("SOAP-Body der Antwort ist leer")

    prefix_el = response_el.find("PREFIX")
    transaction_id = _text(prefix_el, "TRANSACTION_ID")

    items: list[PriceAvailResultItem] = []
    item_list_el = response_el.find("ITEM_LIST")
    if item_list_el is not None:
        items = [_parse_item(item_el) for item_el in item_list_el.findall("ITEM")]

    return ParsedResponse(transaction_id=transaction_id, items=items)


def _parse_item(item_el: ET.Element) -> PriceAvailResultItem:
    return_code = _text(item_el, "RETURNCODE") or ""
    return_code_text = _text(item_el, "RETURNCODE_TEXT") or ""

    ident_el = item_el.find("ITEM_IDENT")
    line_item_number = int(_text(ident_el, "LINE_ITEM_NUMBER") or "0")
    material_number = _text(ident_el, "MATERIAL_NUMBER") or ""

    availability_el = item_el.find("AVAILABILITY_DATA")
    availability_status = _text(availability_el, "AVAILABILITY_STATUS")
    warehouse_number = _text(availability_el, "AVAILABILITY_PARTNER_WAREHOUSE")
    warehouse_name = _text(availability_el, "PARTNER_WAREHOUSE_NAME")

    price_el = item_el.find("PRICE_DATA")
    price_amount = _decimal(_text(price_el, "PRICE_AMOUNT"))
    net_amount = _decimal(_text(price_el, "NET_AMOUNT"))
    list_amount = _decimal(_text(price_el, "LIST_AMOUNT"))

    surcharges: list[Surcharge] = []
    surcharge_list_el = price_el.find("SURCHARGE_REBATE_LIST") if price_el is not None else None
    if surcharge_list_el is not None:
        for surcharge_el in surcharge_list_el.findall("SURCHARGE_REBATE"):
            surcharges.append(
                Surcharge(
                    code=_text(surcharge_el, "SURCHARGE_REBATE_CODE") or "",
                    text=_text(surcharge_el, "SURCHARGE_REBATE_TEXT") or "",
                    amount=_decimal(_text(surcharge_el, "SURCHARGE_REBATE_AMOUNT")) or Decimal(0),
                )
            )

    return PriceAvailResultItem(
        line_item_number=line_item_number,
        material_number=material_number,
        status=_status_for_return_code(return_code),
        return_code=return_code,
        return_code_text=return_code_text,
        availability_status=availability_status,
        warehouse_number=warehouse_number,
        warehouse_name=warehouse_name,
        price_amount=price_amount,
        net_amount=net_amount,
        list_amount=list_amount,
        surcharges=surcharges,
    )


def _status_for_return_code(return_code: str) -> str:
    if return_code.startswith("I"):
        return "ok"
    if return_code.startswith("H"):
        return "hint"
    return "error"


def _add_text(parent: ET.Element, tag: str, value: str | None) -> None:
    el = ET.SubElement(parent, tag)
    if value is not None:
        el.text = value


def _format_quantity(quantity: Decimal) -> str:
    """Format per spec's ``num 7.2``: dot separator, no leading zeros/thousands separators."""
    return format(quantity.normalize(), "f")


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

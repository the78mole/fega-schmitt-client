"""Data model for the IDS Warenkorb (cart) exchange.

Field names/structure follow docs/specs/IDS_Schnittstelle_2_5_final_NEU.pdf,
section 7.1 ("Dateninhalte Warenkorb"). Only the Warenkorb-relevant data is
modeled here - Heatinglabel (section 7.2) is out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from typing import Literal

ModeOfShipment = Literal["Lieferung", "Abholung"]
ItemChara = Literal["normal", "alternate", "provis"]
ReturnFlag = Literal["Warenkorbrückgabe", "Warenkorbrückgabe mit Bestellung"]


@dataclass
class Address:
    """A postal address block - reused identically for Supplier/Customer/DeliveryPlace."""

    name1: str | None = None
    name2: str | None = None
    name3: str | None = None
    name4: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    iln: str | None = None
    contact: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None


@dataclass
class SupplierInfo:
    id_no: str | None = None
    address: Address | None = None


@dataclass
class CustomerInfo:
    id_no: str | None = None
    address: Address | None = None


@dataclass
class DeliveryPlaceInfo:
    address: Address | None = None


@dataclass
class OrderInfo:
    mode_of_shipment: ModeOfShipment = "Lieferung"
    inquiry_no: str | None = None
    offer_no: str | None = None
    part_no: str | None = None
    order_conf_no: str | None = None
    delivery_week: int | None = None
    delivery_year: int | None = None
    delivery_date: date | None = None
    currency: str | None = None
    additional_text: str | None = None
    commission: str | None = None


@dataclass
class RawMaterialShare:
    """A single ``Rohstoffanteil`` entry (e.g. copper share for metal surcharges)."""

    raw_material: str
    weight_share_value: Decimal
    weight_share_unit: str
    basis_value: Decimal
    basis_unit: str
    basis_quote: Decimal | None = None
    current_quote: Decimal | None = None


@dataclass
class CartItem:
    """A single article line of a Warenkorb (``Order/OrderItem``).

    Reused for both directions: :func:`fega_schmitt_client.ids.build_cart_request`
    only populates the request-side fields, :func:`fega_schmitt_client.ids.parse_cart_callback`
    fills in the additional response-side fields (price/error/etc.).
    """

    article_number: str
    quantity: Decimal | int | float | str
    unit: str
    item_type: ItemChara | None = None
    ref_customer: str | None = None
    ref_customer_sub_no: str | None = None
    ref_supplier: str | None = None
    ref_supplier_sub_no: str | None = None
    ean: str | None = None
    manufacturer_id: str | None = None
    manufacturer_id_type: str | None = None
    short_text: str | None = None
    long_text: str | None = None
    offer_price: Decimal | None = None
    net_price: Decimal | None = None
    price_basis: Decimal | None = None
    vat: Decimal | None = None
    techn_clarification: bool | None = None
    hint: str | None = None
    error_code: int | None = None
    error_text: str | None = None
    surcharge_percent: Decimal | None = None
    raw_material_shares: list[RawMaterialShare] = field(default_factory=list)
    diverse: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))


@dataclass
class Cart:
    """A full Warenkorb (``Warenkorb`` root element)."""

    items: list[CartItem]
    order_info: OrderInfo = field(default_factory=OrderInfo)
    supplier_info: SupplierInfo | None = None
    customer_info: CustomerInfo | None = None
    delivery_place_info: DeliveryPlaceInfo | None = None
    date: date | None = None
    time: time | None = None
    # Only ever set on a *received* cart (WarenkorbInfo/RueckgabeKZ) - the
    # spec explicitly forbids sending it: "kann nicht übertragen werden".
    return_flag: ReturnFlag | None = None


@dataclass
class CartRequest:
    """A prepared 'Warenkorb senden' (WKS) browser form-POST.

    Not a simple GET-redirect URL: FEGA's IDS interface requires POSTing
    this as ``multipart/form-data`` from an actual browser context (the shop
    then renders its own UI - "Blackbox" per the spec, section 5.2). The
    caller (e.g. fega-schmitt-mcp) decides how to present this - rendering
    an auto-submitting HTML form for the user to open, or handing the
    fields to a browser-automation tool.
    """

    shop_url: str
    fields: dict[str, str]
    method: str = "POST"
    enctype: str = "multipart/form-data"

"""IDS interface (BVBS/ITEK Warenkorb exchange) - see docs/architecture.md, section 7.1.

Not part of v1's core scope (SOAP price/availability), built as an optional
extension. Only 'Warenkorb senden'/'Warenkorb empfangen' are implemented so
far - not Artikeldeeplink, Artikelsuche, Login-Informationen,
Schnittstellenversion, or Heatinglabel.
"""

from .cart import build_cart_request, parse_cart_callback
from .models import (
    Address,
    Cart,
    CartItem,
    CartRequest,
    CustomerInfo,
    DeliveryPlaceInfo,
    OrderInfo,
    RawMaterialShare,
    SupplierInfo,
)

__all__ = [
    "Address",
    "Cart",
    "CartItem",
    "CartRequest",
    "CustomerInfo",
    "DeliveryPlaceInfo",
    "OrderInfo",
    "RawMaterialShare",
    "SupplierInfo",
    "build_cart_request",
    "parse_cart_callback",
]

"""IDS Warenkorb (cart) exchange: sending a cart to FEGA's webshop and
parsing the cart that comes back via the Hook-URL callback.

Unlike the SOAP price/availability service, IDS is not a simple
request/response API - see docs/architecture.md, section 7.1. Sending a
cart means POSTing a form to a browser window that a human then interacts
with in FEGA's shop; this module only builds/parses the data, it does not
open a browser or run a webhook receiver (that's the caller's job, e.g.
fega-schmitt-mcp).
"""

from __future__ import annotations

from ._xml import build_warenkorb_xml, parse_warenkorb_xml
from .models import Cart, CartRequest

ACTION_SEND_CART = "WKS"


def build_cart_request(
    cart: Cart,
    *,
    shop_url: str,
    customer_number: str | None = None,
    username: str | None = None,
    password: str | None = None,
    hook_url: str | None = None,
    target: str | None = None,
) -> CartRequest:
    """Build the form fields for a 'Warenkorb senden' (WKS) browser POST.

    ``shop_url`` is FEGA's IDS shop entry point - not yet known/documented,
    see README "Offene Punkte"; it must be supplied by the caller once
    confirmed, there is no default.

    ``hook_url`` is optional: without it, FEGA's shop has no way to post a
    result back (IDS-Spec, section 5.8: "Der Parameter Hook-Url muss in
    jedem Fall mitgesendet werden, da nur dann eine Rückübertragung möglich
    ist") - the cart can still be opened for a human to complete manually in
    the browser, there just won't be an automatic callback.
    """
    fields: dict[str, str] = {"action": ACTION_SEND_CART, "version": "2.5"}
    if customer_number:
        fields["kndnr"] = customer_number
    if username:
        fields["name_kunde"] = username
    if password:
        fields["pw_kunde"] = password
    if hook_url:
        fields["hookurl"] = hook_url
    if target:
        fields["target"] = target
    fields["warenkorb"] = build_warenkorb_xml(cart).decode("utf-8")

    return CartRequest(shop_url=shop_url, fields=fields)


def parse_cart_callback(xml: bytes | str) -> Cart:
    """Parse the Warenkorb XML received via the Hook-URL callback.

    Takes the raw XML content directly - extracting it from the incoming
    webhook POST (``multipart/form-data``, field name presumably
    ``warenkorb`` by symmetry with the outgoing request, not explicitly
    re-documented for the callback direction) is the caller's responsibility.
    """
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    return parse_warenkorb_xml(xml)

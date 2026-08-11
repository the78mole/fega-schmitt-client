"""Webshop frontend access (search, article detail/images/category, cart,
orders, favorites, deals) - see docs/extensions.md, section 10.

Not part of v1's core scope (SOAP price/availability), and not an
officially documented FEGA & Schmitt interface like SOAP or IDS - built as
an optional, explicitly-imported extension. Read docs/extensions.md before
relying on this: it documents which parts are validated against a real
72-article production run vs. best-effort, and remaining open questions.
"""

from .client import WebClient
from .exceptions import FegaLoginError, FegaScrapingError
from .models import (
    Article,
    ArticleDetail,
    ArticleImage,
    ArticleSearchResult,
    CableLength,
    Cart,
    CartItem,
    CartSummary,
    DealCampaign,
    Order,
    OrderItem,
    OrderSummary,
)

__all__ = [
    "Article",
    "ArticleDetail",
    "ArticleImage",
    "ArticleSearchResult",
    "CableLength",
    "Cart",
    "CartItem",
    "CartSummary",
    "DealCampaign",
    "FegaLoginError",
    "FegaScrapingError",
    "Order",
    "OrderItem",
    "OrderSummary",
    "WebClient",
]

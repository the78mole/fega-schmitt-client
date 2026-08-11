"""WebClient: access to the FEGA & Schmitt webshop frontend.

Not an officially documented FEGA & Schmitt interface, unlike the SOAP
price/availability service or IDS - see docs/extensions.md, section 10,
for why this lives as its own explicitly-imported extension rather than
part of FegaSchmittClient, and section 5 for what's still open before
relying on this in production.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import TracebackType
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from typing import Self

from ..exceptions import FegaTransportError
from . import _parse
from .exceptions import FegaLoginError, FegaScrapingError
from .models import (
    Article,
    ArticleDetail,
    ArticleImage,
    ArticleSearchResult,
    CableLength,
    Cart,
    CartSummary,
    DealCampaign,
    Order,
    OrderSummary,
)

DEFAULT_BASE_URL = "https://shop.fega.de"

# The "/abtest/" segment is an A/B test FEGA & Schmitt appears to be running
# on the shop frontend - observed stable across multiple days and sessions
# (docs/extensions.md, section 2.2), but not documented or guaranteed to
# stay that way. Override shop_path if it changes.
DEFAULT_SHOP_PATH = "/abtest/scripts/shop.php"
DEFAULT_LOGIN_PATH = "/scripts/clsAIShop.php"

# Campaign ID for the "2. Wahl"/B-Ware section (docs/extensions.md, section
# 2.7) - an opaque ID found via one real link, not a documented constant.
# Its long-term stability is unconfirmed.
DEFAULT_SECOND_CHOICE_DEAL_ID = "3342"

# The shop redirects to a URL containing this marker (".../abtest?warnings=
# Bitte+melden+Sie+sich+neu+an...") both for an actually-expired session and
# for a mismatched "bold" session token (docs/extensions.md, section 2.2/2.8)
# - we can't tell those apart from the outside, so both trigger one retry.
_LOGIN_REQUIRED_MARKER = "warnings="

_REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)


class WebClient:
    """Client for the FEGA & Schmitt webshop frontend: search, article detail/
    images/category, favorites, deals, cart, orders - see docs/extensions.md
    for what each method is based on and how confident the parsing is.

    Uses the same customer number/shop password as FegaSchmittClient
    (confirmed in extensions.md 2.2). Unlike FegaSchmittClient, this keeps a
    single persistent httpx.Client for the object's lifetime instead of one
    per request: the shop's session cookie is scoped across several
    different paths at once (extensions.md 2.2), and a cookie-file/process
    roundtrip has been observed to silently drop it (extensions.md,
    section 4) - close() / the context manager exist because of that.
    """

    def __init__(
        self,
        *,
        customer_number: str,
        shop_password: str,
        base_url: str = DEFAULT_BASE_URL,
        shop_path: str = DEFAULT_SHOP_PATH,
        login_path: str = DEFAULT_LOGIN_PATH,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._customer_number = customer_number
        self._shop_password = shop_password
        self._base_url = base_url.rstrip("/")
        self._shop_path = shop_path
        self._login_path = login_path
        self._client = http_client or httpx.Client(timeout=timeout, follow_redirects=False)
        self._owns_client = http_client is None
        self._logged_in = False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # --- Articles (docs/extensions.md 2.3-2.5, 2.7) ---

    def search(self, query: str) -> list[ArticleSearchResult]:
        """Search by material number, EAN, manufacturer item number, or free
        text - confirmed to be one shared field (extensions.md 2.3)."""
        response = self._get("Suche", q=query)
        return _parse.parse_tile_list(response.text)

    def get_article(self, material_number: str) -> Article:
        """Fetch everything this library knows about an article - EAN,
        manufacturer numbers, category, own article number, technical
        attributes, images, accessories, variants, alternatives, cross-sell
        (docs/extensions.md 2.9) - from a single detail-page fetch.

        Internally does a search() first to find the article's detail-page
        URL (the shop's product URLs contain a description slug that can't
        be constructed from material_number alone), so this is two HTTP
        requests, not one - but the same two requests as any single one of
        the narrower get_article_*() methods below, which are now thin
        accessors on top of this method's result rather than doing their
        own fetch+parse.
        """
        response = self._get_product_page(material_number)
        return _parse.parse_article(response.text, material_number, fetched_at=datetime.now(timezone.utc))

    def get_article_detail(self, material_number: str) -> ArticleDetail:
        """Shortcut for the EAN/manufacturer-number/category/own-article-number
        subset of get_article()'s result, as the older, narrower ArticleDetail shape."""
        article = self.get_article(material_number)
        return ArticleDetail(
            material_number=article.material_number,
            ean=article.ean,
            manufacturer_item_number=article.manufacturer_item_number,
            manufacturer_item_number_alt=article.manufacturer_item_number_alt,
            supplier_name=article.supplier_name,
            supplier_number=article.supplier_number,
            category_id=article.category_id,
            category_name=article.category_name,
            own_article_number=article.own_article_number,
        )

    def get_article_category(self, material_number: str) -> tuple[str | None, str | None]:
        """Shortcut for ``(category_id, category_name)`` from get_article()'s result."""
        article = self.get_article(material_number)
        return article.category_id, article.category_name

    def get_article_number(self, material_number: str) -> str | None:
        """Shortcut for ``Article.own_article_number``."""
        return self.get_article(material_number).own_article_number

    def set_article_number(self, material_number: str, own_article_number: str) -> None:
        """Set the customer's own article number for an article (docs/extensions.md 2.8).

        Confirmed via one real browser network capture, not independently
        re-verified end-to-end by this library (the capture's session had
        cookies - notably PHPSESSID and a long-lived login token - that a
        plain login here does not set, see extensions.md 2.8). If this call
        succeeds (HTTP 200) but get_article_number() doesn't reflect the
        change afterwards, that cookie gap is the most likely cause.
        """
        self._post(
            "AjaxArticleNumber",
            data={"ownArticleNumber": own_article_number, "arnr": material_number},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

    def get_article_images(self, material_number: str) -> list[ArticleImage]:
        """Shortcut for get_article()'s images; see ArticleImage/parse_article_images
        for the "shared across a variant family" caveat."""
        return self.get_article(material_number).images

    def get_article_attributes(self, material_number: str) -> dict[str, str]:
        """Shortcut for get_article()'s technical attributes (the "Produktdetails"
        grid, docs/extensions.md 2.9), e.g. "Farbe" or "Nennspannung" - field
        names vary by Warengruppe, no fixed schema."""
        return self.get_article(material_number).attributes

    def get_article_accessories(self, material_number: str) -> list[str]:
        """Shortcut for get_article()'s "Zubehör" material numbers (docs/extensions.md 2.9)."""
        return self.get_article(material_number).accessories

    def get_article_variants(self, material_number: str) -> list[str]:
        """Shortcut for get_article()'s "Varianten" material numbers - other
        colours/sizes/... of this article's family (docs/extensions.md 2.9)."""
        return self.get_article(material_number).variants

    def get_article_alternatives(self, material_number: str) -> list[str]:
        """Shortcut for get_article()'s "Alternativen" material numbers.

        May be an empty list even where the shop's UI shows an "Verwandte
        Artikel anzeigen" button - that button drives a separate, JS-only
        attribute-filter feature this doesn't use (docs/extensions.md 2.9).
        """
        return self.get_article(material_number).alternatives

    def get_article_cross_sell(self, material_number: str) -> list[str]:
        """Shortcut for get_article()'s "Oft zusammengekauft mit" material
        numbers - not originally planned, found via the same mechanism while
        researching accessories/variants/alternatives (docs/extensions.md 2.9)."""
        return self.get_article(material_number).cross_sell

    def get_cutting_fee(self, material_number: str) -> Decimal | None:
        """Shortcut for get_article()'s cutting fee (docs/extensions.md 2.10) -
        only cable articles cut from a drum have one, None otherwise."""
        return self.get_article(material_number).cutting_fee

    def get_cable_lengths(self, material_number: str) -> list[CableLength]:
        """ "Verfügbare Kabellängen" - available drums/remainder pieces for a
        cable article, across all warehouse locations (docs/extensions.md 2.10).

        Unlike get_article() and friends, this is a single HTTP request:
        cmd=AjaxKLaeng/<material_number> takes the material number directly,
        no search()-derived detail-page URL needed. Empty for articles that
        aren't sold off a drum, or currently out of stock everywhere.
        """
        response = self._get(f"AjaxKLaeng/{material_number}")
        return _parse.parse_cable_lengths(response.text)

    def has_cable_lengths(self, material_number: str) -> bool:
        """Whether this article currently offers any drums/remainder pieces
        at all - a cheap existence check on top of get_cable_lengths()."""
        return bool(self.get_cable_lengths(material_number))

    def list_articles_by_category(self, category_id: str) -> list[ArticleSearchResult]:
        """List articles in a UWG category (docs/fega_categories.md for known IDs).

        Pagination/completeness for categories with more than a handful of
        articles is unconfirmed (extensions.md 2.6) - this returns whatever
        the first response contains, which may not be the full category.
        """
        response = self._get(f"Hierarchie/{category_id}", mode="list")
        return _parse.parse_tile_list(response.text)

    def get_favorite_list(self) -> list[ArticleSearchResult]:
        response = self._get("Favorites/-1")
        return _parse.parse_tile_list(response.text)

    def get_deal_campaigns(self) -> list[DealCampaign]:
        """ "Aktionsangebote" - promotional deal *campaigns* (extensions.md 2.7).

        cmd=Deal lists campaigns (e.g. "Sonderabverkauf Licht"), not
        individual articles - fetch a campaign's articles with
        get_deal_articles(campaign_id).
        """
        response = self._get("Deal")
        return _parse.parse_deal_campaigns(response.text)

    def get_deal_articles(self, campaign_id: str) -> list[ArticleSearchResult]:
        """Articles within one deal campaign (see get_deal_campaigns())."""
        response = self._get(f"Deal/{campaign_id}", mode="1")
        return _parse.parse_tile_list(response.text)

    def get_daily_deals(self) -> list[ArticleSearchResult]:
        """ "Tagesangebote" - may legitimately be empty depending on the day (extensions.md 2.7).
        Only ever observed empty during research, so the non-empty tile format is unverified."""
        response = self._get("TagA")
        return _parse.parse_tile_list(response.text)

    def get_second_choice_articles(self, deal_id: str = DEFAULT_SECOND_CHOICE_DEAL_ID) -> list[ArticleSearchResult]:
        """ "2. Wahl"/B-Ware articles (docs/extensions.md 2.7) - a special case of
        get_deal_articles() for a specific, hardcoded campaign ID, with an extra
        ``svc=2Wahl`` parameter as observed in the real link this was found through.
        ``deal_id`` is an opaque campaign ID whose long-term stability is
        unconfirmed - override it if FEGA & Schmitt changes it."""
        response = self._get(f"Deal/{deal_id}", mode="1", svc="2Wahl")
        return _parse.parse_tile_list(response.text)

    # --- Cart (docs/extensions.md 2.7) ---

    def get_cart(self, cart_id: str | None = None) -> Cart:
        """Fetch a cart by ID, or the currently active one if omitted."""
        cmd = f"BasketView/{cart_id}" if cart_id else "BasketView"
        response = self._get(cmd)
        return _parse.parse_cart(response.text)

    def get_cart_list(self) -> list[CartSummary]:
        """List all of the customer's named carts (current + others).

        No dedicated "list all carts" route was found - this combines the
        currently-open cart with the "switch cart" dropdown found on the
        same page (extensions.md 2.7).
        """
        response = self._get("BasketView")
        current = _parse.parse_cart(response.text)
        others = _parse.parse_cart_list(response.text)
        if current.cart_id and not any(c.cart_id == current.cart_id for c in others):
            return [CartSummary(cart_id=current.cart_id, name=current.name), *others]
        return others

    # --- Orders (docs/extensions.md 2.7) ---

    def get_order_list(self) -> list[OrderSummary]:
        response = self._get("Auftraege", mode="opbauDok")
        return _parse.parse_order_list(response.text)

    def get_order(self, order_number: str) -> Order:
        """Fetch an order's line items. See parse_order_detail() for field confidence."""
        response = self._get(f"Auftraege/{order_number}", mode="detail", show_complete="1")
        return _parse.parse_order_detail(order_number, response.text)

    # --- Internal HTTP/session handling ---

    def _get_product_page(self, material_number: str) -> httpx.Response:
        results = self.search(material_number)
        match = next((r for r in results if r.material_number == material_number and r.detail_url), None)
        if match is None:
            raise FegaScrapingError(f"Konnte keine Artikelseite für Artikelnummer {material_number!r} finden")
        return self._raw_get(match.detail_url)

    def _ensure_login(self) -> None:
        if self._logged_in:
            return
        url = f"{self._base_url}{self._login_path}"
        response = self._client.post(
            url,
            params={"cmd": "MemberLogin"},
            data={
                "memb_login": self._customer_number,
                "memb_pass": self._shop_password,
                "winwidth": "",
                "winheight": "",
                "setcookie": "1",
            },
        )
        location = response.headers.get("Location", "")
        if response.status_code not in _REDIRECT_STATUS_CODES or _LOGIN_REQUIRED_MARKER in location:
            # Never independently verified against actually-wrong credentials
            # (docs/extensions.md, README "Offene Punkte" for the analogous
            # SOAP case) - this is a best-effort interpretation of "login failed".
            raise FegaLoginError(
                f"FEGA & Schmitt hat den Webshop-Login abgelehnt (HTTP {response.status_code}, Location={location!r})"
            )
        self._logged_in = True

    def _get(self, cmd: str, **params: str) -> httpx.Response:
        url = f"{self._base_url}{self._shop_path}"
        return self._request("GET", url, params={"bold": "", "cmd": cmd, **params})

    def _post(self, cmd: str, *, data: dict[str, str], headers: dict[str, str] | None = None) -> httpx.Response:
        url = f"{self._base_url}{self._shop_path}"
        # Mirror the session's "cbold" cookie into "bold" - see extensions.md
        # 2.7/2.8 for why a hardcoded/empty value isn't guaranteed to work here
        # the way it does for the GET endpoints above.
        bold = self._client.cookies.get("cbold", "")
        return self._request("POST", url, params={"bold": bold, "cmd": cmd}, data=data, headers=headers)

    def _raw_get(self, url: str) -> httpx.Response:
        return self._request("GET", url)

    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self._ensure_login()
        response = self._send(method, url, **kwargs)

        location = response.headers.get("Location", "")
        if response.status_code in _REDIRECT_STATUS_CODES and _LOGIN_REQUIRED_MARKER in location:
            # Session expired or "bold" mismatch mid-use (extensions.md 2.2/2.8) - log in again, retry once.
            self._logged_in = False
            self._ensure_login()
            response = self._send(method, url, **kwargs)

        if response.status_code != 200:
            raise FegaTransportError(f"Unerwarteter HTTP-Status {response.status_code} von {url}")
        return response

    def _send(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise FegaTransportError(f"Zeitüberschreitung bei Anfrage an {url}") from exc
        except httpx.HTTPError as exc:
            raise FegaTransportError(f"HTTP-Anfrage an {url} fehlgeschlagen: {exc}") from exc

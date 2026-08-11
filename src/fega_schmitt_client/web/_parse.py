"""Low-level HTML parsing for the FEGA & Schmitt webshop.

Internal module - not part of the public API. Deliberately regex-based
instead of a full HTML parser: docs/extensions.md found this sufficient
(100% success rate across a 72-article production run) because the shop
exposes the data we need through a handful of narrow, stable markers
(a "data-compare" microformat, one JSON blob per article page, a couple of
label-anchored fields) rather than requiring a full DOM walk - see
docs/extensions.md, sections 2.3-2.8, for what each pattern is based on.

Confidence varies by function - see individual docstrings. Search/article
detail/images/category are validated against a real 72-article run;
cart/order parsing are validated against real examples but only a small
number of them, so treat their exact field layout as more likely to need
adjustment if FEGA changes the frontend.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from ._categories import normalize_category_id
from .exceptions import FegaScrapingError
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

# --- Article search/favorites/deals/category-list tiles (extensions.md 2.3) ---

_TILE_COMPARE_RE = re.compile(r'data-compare="(\d+);([^"]*);(https?://[^"]*)"')


def parse_tile_list(html: str) -> list[ArticleSearchResult]:
    """Parse the "data-compare" tile microformat shared by search results,
    favorites, deals, daily deals, second-choice articles, and
    category-listing pages (see docs/extensions.md, sections 2.3, 2.6, 2.7).

    Deliberately does not require a specific container class
    (``fsProductList__item`` vs. ``fsDealList__item``) - "data-compare" alone
    is enough and is shared across all of these page types. Ad tiles
    (``fsSucheWerbung``, see 2.3) don't carry this attribute and are
    naturally excluded.
    """
    results: list[ArticleSearchResult] = []
    seen: set[str] = set()
    for match in _TILE_COMPARE_RE.finditer(html):
        material_number, description, thumbnail_url = match.groups()
        if material_number in seen:
            continue
        seen.add(material_number)

        window = html[match.end() : match.end() + 2000]
        href_match = re.search(
            r'href="(https://shop\.fega\.de/product/[^"]*-' + re.escape(material_number) + r'\.html)"',
            window,
        )
        results.append(
            ArticleSearchResult(
                material_number=material_number,
                description=html_lib.unescape(description),
                thumbnail_url=thumbnail_url or None,
                detail_url=href_match.group(1) if href_match else "",
            )
        )
    return results


# --- Article detail page (extensions.md 2.4, 2.5, 2.7) ---

# Despite the name, this isn't a separate "fsOxomi div" as docs/extensions.md
# 2.4 originally assumed - the data-variables attribute (and the fsOxomi
# class) sit directly on the article page's own <body> tag. The regex
# doesn't care which tag it is, so this always worked, but that mental
# model was wrong and matters now: the same JSON also carries a "variants"
# array (docs/extensions.md 2.9) that parse_article_variants() below reads
# from this exact same dict, not a second blob.
_DATA_VARIABLES_RE = re.compile(r'data-variables="(.*?)"\s+class="fscomponent fsWebsite', re.DOTALL)
_WARENGRUPPE_RE = re.compile(
    r'Warengruppe\s*</span>\s*<span class="fsProductInfo__text">\s*'
    r'<a[^>]*href="[^"]*cmd=Hierarchie/([A-Za-z0-9_]+)[^"]*"[^>]*>\s*([^<]+)'
)
_OWN_ARTICLE_NUMBER_RE = re.compile(r'name="ownArticleNumber"[^>]*value="([^"]*)"')
_IMAGE_RE = re.compile(r'<img class="width-100" src="(https://shop\.fega\.de/media/[^"]+)"')


def _extract_data_variables(html: str) -> dict[str, object]:
    match = _DATA_VARIABLES_RE.search(html)
    if not match:
        raise FegaScrapingError(
            "data-variables attribute not found on article detail page - "
            "the shop's frontend markup may have changed, see docs/extensions.md section 2.4"
        )
    raw = html_lib.unescape(match.group(1))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FegaScrapingError(f"could not decode data-variables JSON: {exc}") from exc


def _extract_variant_matrix(html: str) -> list[str] | None:
    """Flat, deduplicated material numbers from the data-variables JSON's
    "variants" array (docs/extensions.md 2.9), or None if that JSON blob
    can't be found/parsed at all - defensive fallback to the older,
    less rich teaser-based extraction rather than raising, since
    parse_article_variants() has never raised before.
    """
    try:
        data = _extract_data_variables(html)
    except FegaScrapingError:
        return None
    variants = data.get("variants")
    if not isinstance(variants, list):
        return None

    numbers: list[str] = []
    seen: set[str] = set()
    for entry in variants:
        for number in str(entry.get("arnrlist", "")).split(","):
            number = number.strip()
            if number and number not in seen:
                seen.add(number)
                numbers.append(number)
    return numbers


def parse_article_detail(html: str, material_number: str) -> ArticleDetail:
    """Parse an article detail page's data-variables JSON blob, Warengruppe
    link, and own-article-number field (docs/extensions.md 2.4/2.5/2.7).

    ``supplier_name`` is unreliable as a manufacturer name - it was a
    category name for one tested article and a real brand for another
    (extensions.md 2.4). Don't treat it as authoritative without further
    per-supplier verification.
    """
    data = _extract_data_variables(html)

    category_id = None
    category_name = None
    wg_match = _WARENGRUPPE_RE.search(html)
    if wg_match:
        category_id = normalize_category_id(wg_match.group(1))
        category_name = html_lib.unescape(wg_match.group(2).strip())

    own_match = _OWN_ARTICLE_NUMBER_RE.search(html)
    own_article_number = html_lib.unescape(own_match.group(1)) if own_match and own_match.group(1) else None

    return ArticleDetail(
        material_number=str(data.get("oxom_arnr") or material_number),
        ean=(str(data.get("oxom_ean") or "").strip() or None),
        manufacturer_item_number=(str(data["supplierItemNumber"]) if data.get("supplierItemNumber") else None),
        manufacturer_item_number_alt=(str(data["supplierItemNumber3"]) if data.get("supplierItemNumber3") else None),
        supplier_name=(str(data["supplierName"]) if data.get("supplierName") else None),
        supplier_number=(str(data["supplierNumber"]) if data.get("supplierNumber") else None),
        category_id=category_id,
        category_name=category_name,
        own_article_number=own_article_number,
    )


def parse_article_images(html: str, material_number: str) -> list[ArticleImage]:
    """Parse gallery images from an article detail page (extensions.md 2.4).

    The first ``<img class="width-100">`` is the hero/preview image, further
    ones (if any) come from the ``fsDetailSwiper`` gallery - marked
    ``is_primary`` accordingly. Note: the image shown is sometimes shared
    across an entire article family/variant group rather than being unique
    to this exact material_number (extensions.md 2.4) - the URL itself may
    reference a different, "representative" article number.
    """
    urls: list[str] = []
    seen: set[str] = set()
    for match in _IMAGE_RE.finditer(html):
        url = match.group(1)
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return [ArticleImage(material_number=material_number, url=url, is_primary=(i == 0)) for i, url in enumerate(urls)]


# --- Attributes, accessories/variants/alternatives/cross-sell (extensions.md 2.9) ---

# Anchored on the visible "Verwandte Artikel anzeigen"/attribute-filter block
# on the detail page's "Produktdetails" grid, not the generic
# "fsProductOverview__value" alone - that class is reused for fixed fields
# like "Artikelnummer"/"Meine Artikelnummer" which are already covered by
# parse_article_detail() and shouldn't show up twice.
_ATTRIBUTE_RE = re.compile(
    r'<span class="fsProductOverview__label alternativesLabelContainer">([^<]+?):?\s*</span>\s*'
    r'<div class="fsProductOverview__value">\s*([^<]*?)\s*</div>',
    re.DOTALL,
)

# Zubehör/Varianten/Alternativen/"Oft zusammengekauft mit" are all rendered
# as a "fsProductTeaser" (or, for Alternativen, plain "fsProductTeaser")
# block with a "Jetzt vergleichen" fsWand button whose data-compare
# attribute is a flat comma-separated list of material numbers - the
# article's own number first, then the related ones. No individual-tile
# parsing needed for the material-number list itself (extensions.md 2.9).
# Anchored on the visible headline text rather than the section's numeric
# id (productTeaser1/2/3, productCompare) - those ids were stable across
# three tested articles but aren't guaranteed to be if a whole section is
# omitted for a given article (e.g. no Alternativen section at all).
_TEASER_HEADLINE_RE = re.compile(r'<h2 class="fsProductTeaser__headline">([^<]+)</h2>')
_WAND_COMPARE_RE = re.compile(r'class="[^"]*\bfsWand\b[^"]*"\s+data-compare="([^"]*)"')


def parse_article_attributes(html: str) -> dict[str, str]:
    """Parse category-/article-type-specific technical attributes from the
    "Produktdetails" grid on an article detail page (extensions.md 2.9).

    Field names vary by Warengruppe (e.g. "Farbe", "Nennspannung",
    "Leiternennquerschnitt") - there's no fixed schema, so this returns a
    plain dict rather than a dataclass with named fields.
    """
    return {label.strip(): html_lib.unescape(value.strip()) for label, value in _ATTRIBUTE_RE.findall(html)}


def _parse_related_material_numbers(html: str, headline: str) -> list[str]:
    for headline_match in _TEASER_HEADLINE_RE.finditer(html):
        if headline_match.group(1).strip() != headline:
            continue
        window = html[headline_match.end() : headline_match.end() + 4000]
        next_headline_match = _TEASER_HEADLINE_RE.search(window)
        if next_headline_match:
            window = window[: next_headline_match.start()]
        wand_match = _WAND_COMPARE_RE.search(window)
        if not wand_match or not wand_match.group(1):
            return []
        # The list's first entry is always the article's own number
        # (extensions.md 2.9) - dropped unconditionally rather than matched
        # against a caller-supplied material_number, since the two can
        # legitimately differ in spelling (e.g. leading zeros).
        numbers = wand_match.group(1).split(",")
        return numbers[1:]
    return []


def parse_article_accessories(html: str) -> list[str]:
    """Material numbers listed under "Zubehör" on the article detail page."""
    return _parse_related_material_numbers(html, "Zubehör")


def parse_article_variants(html: str) -> list[str]:
    """Material numbers of every variant (colour/size/current rating/.../
    any combination the shop's attribute-based variant selector offers) of
    this article's family.

    Sourced from the data-variables JSON's "variants" array (see
    _extract_variant_matrix) - the same data backing the shop's large
    clickable variant selector, confirmed to hold far more entries (500+
    for one tested article) than the small "Varianten" teaser section this
    used to read (extensions.md 2.9). Falls back to the teaser section if
    that JSON is missing/malformed, since it's less battle-tested markup.
    """
    matrix = _extract_variant_matrix(html)
    if matrix is not None:
        return matrix
    return _parse_related_material_numbers(html, "Varianten")


def parse_article_alternatives(html: str) -> list[str]:
    """Material numbers listed under "Alternativen" on the article detail page.

    Some articles have no static "Alternativen" section at all and instead
    only expose a JS-driven, attribute-filter-based "Verwandte Artikel
    anzeigen" finder (extensions.md 2.9) - this returns an empty list for
    those, it does not attempt to drive that JS feature.
    """
    return _parse_related_material_numbers(html, "Alternativen")


def parse_article_cross_sell(html: str) -> list[str]:
    """Material numbers listed under "Oft zusammengekauft mit" (frequently
    bought together) on the article detail page."""
    return _parse_related_material_numbers(html, "Oft zusammengekauft mit")


# Only present on cable articles sold off a drum (extensions.md 2.10) - the
# same page text the "verfügbare Kabellängen" overlay button sits next to,
# not part of the overlay's own AjaxKLaeng response.
_CUTTING_FEE_RE = re.compile(r'Schnittkosten in Höhe von\s*<span class="bold">([^<]+)</span>')


def parse_cutting_fee(html: str) -> Decimal | None:
    """ "Eventuell fallen Schnittkosten in Höhe von X an." - the flat fee for
    cutting a custom length off a "zum Ablängen" cable drum (extensions.md
    2.10). None for articles that don't mention one at all."""
    match = _CUTTING_FEE_RE.search(html)
    if not match:
        return None
    return _parse_decimal(html_lib.unescape(match.group(1)).replace("€", "").strip())


def parse_article(html: str, material_number: str, fetched_at: datetime) -> Article:
    """Parse everything this module knows how to extract from one article
    detail page into a single tree (extensions.md 2.9).

    Composes the narrower parse_article_*() functions above rather than
    duplicating their regexes - each stays individually usable/testable,
    this just assembles their results plus a caller-supplied fetch
    timestamp (the page itself carries no "as of" marker).
    """
    detail = parse_article_detail(html, material_number)
    return Article(
        material_number=detail.material_number,
        fetched_at=fetched_at,
        ean=detail.ean,
        manufacturer_item_number=detail.manufacturer_item_number,
        manufacturer_item_number_alt=detail.manufacturer_item_number_alt,
        supplier_name=detail.supplier_name,
        supplier_number=detail.supplier_number,
        category_id=detail.category_id,
        category_name=detail.category_name,
        own_article_number=detail.own_article_number,
        attributes=parse_article_attributes(html),
        images=parse_article_images(html, material_number),
        accessories=parse_article_accessories(html),
        variants=parse_article_variants(html),
        alternatives=parse_article_alternatives(html),
        cross_sell=parse_article_cross_sell(html),
        documents=[],
        cutting_fee=parse_cutting_fee(html),
    )


# --- Deal campaigns (extensions.md 2.7) ---

# cmd=Deal (no ID) lists *campaigns*, not articles - each tile's own
# "Artikel anzeigen" link is cmd=Deal/<id>&mode=1, the same pattern already
# confirmed for the "2. Wahl"/B-Ware campaign. Tile blocks are delimited by
# the next tile's own marker rather than a fixed character window, because
# some tiles embed a base64 data: URI logo of unpredictable length before
# reaching the title.
_DEAL_TILE_START_RE = re.compile(r'fsDealKachel[^"]*"[^>]*data-id="(\d+)"')
_DEAL_TITLE_RE = re.compile(r"<h4>([^<]*)</h4>")


def parse_deal_campaigns(html: str) -> list[DealCampaign]:
    starts = list(_DEAL_TILE_START_RE.finditer(html))
    campaigns = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(html)
        block = html[match.end() : end]
        title_match = _DEAL_TITLE_RE.search(block)
        title = html_lib.unescape(title_match.group(1).strip()) if title_match else ""
        if title:
            campaigns.append(DealCampaign(campaign_id=match.group(1), title=title))
    return campaigns


# --- Cart (extensions.md 2.7) ---

_CART_MATERIAL_RE = re.compile(r'name="pro_id_(\d+)" value="(\d+)"')
_CART_PWAHL_RE = re.compile(r'name="pwahl_id_(\d+)" value="(\d+)"')
_CART_QTY_RE = re.compile(r'name="pro_anz_(\d+)"[^>]*value="([\d.,]*)"')
_CART_COMMENT_RE = re.compile(r'name="user_info_(\d+)" value="([^"]*)"')
_CART_ID_RE = re.compile(r"cmd=BasketView/(\d+)&amp;mode=changeName")
_CART_NAME_RE = re.compile(r'data-wkname="([^"]*)"')
_SEL_WK_BLOCK_RE = re.compile(r'<select[^>]*name="sel_wk"[^>]*>(.*?)</select>', re.DOTALL)
_SEL_WK_OPTION_RE = re.compile(r'<option value="(\d+)">([^<]*)</option>')


def _parse_decimal(raw: str) -> Decimal:
    if not raw:
        return Decimal(0)
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return Decimal(0)


def parse_cart(html: str) -> Cart:
    """Parse the currently-open basket from a BasketView page.

    Field mapping verified against one real cart with items in it: each
    position's hidden inputs ``pro_id_<pos>`` (material number),
    ``pwahl_id_<pos>`` (internal position id, needed for delete/comment
    actions) and ``pro_anz_<pos>`` (quantity) plus a "Kommission"/comment
    field. Item descriptions are not parsed here - look them up via
    get_article_detail(material_number) if needed.
    """
    materials = dict(_CART_MATERIAL_RE.findall(html))
    pwahl_ids = dict(_CART_PWAHL_RE.findall(html))
    quantities = dict(_CART_QTY_RE.findall(html))
    comments = dict(_CART_COMMENT_RE.findall(html))

    items = [
        CartItem(
            position=int(pos_str),
            material_number=material_number,
            description=None,
            quantity=_parse_decimal(quantities.get(pos_str, "")),
            position_id=pwahl_ids.get(pos_str, ""),
            comment=html_lib.unescape(comments.get(pos_str, "")),
        )
        for pos_str, material_number in sorted(materials.items(), key=lambda kv: int(kv[0]))
    ]

    id_match = _CART_ID_RE.search(html)
    name_match = _CART_NAME_RE.search(html)
    return Cart(
        cart_id=id_match.group(1) if id_match else None,
        name=html_lib.unescape(name_match.group(1)) if name_match else "Warenkorb",
        items=items,
    )


def parse_cart_list(html: str) -> list[CartSummary]:
    """Parse the "other carts" switcher (``<select name="sel_wk">``) on a BasketView page.

    Only lists carts *other* than the one currently open - the shop doesn't
    appear to have a dedicated "list all my carts" route (extensions.md 2.7).
    Combine with parse_cart()'s cart_id/name for the complete set.
    """
    block_match = _SEL_WK_BLOCK_RE.search(html)
    if not block_match:
        return []
    return [
        CartSummary(cart_id=cart_id, name=html_lib.unescape(name.strip()))
        for cart_id, name in _SEL_WK_OPTION_RE.findall(block_match.group(1))
    ]


# --- Orders (extensions.md 2.7) ---

_ORDER_ROW_RE = re.compile(r'<tr class="auftr_tr[^"]*"[^>]*data-id="(\d+)_(\d+)"[^>]*>(.*?)</tr>', re.DOTALL)
_ORDER_SORT_VALUE_RE = re.compile(r'data-sort-value="([\d.]{6,10})"')
_ORDER_STATUS_RE = re.compile(r"<td>\s*<span>([^<]+)</span>\s*</td>\s*<td>\s*<span[^>]*fsTourList", re.DOTALL)

_ORDER_ITEM_RE = re.compile(
    r"fsBadge fsBadge--blue20[^>]*>(\d+)</span>\s*"
    r'<span class="position-absolute bottom-0 start-0 m-3">\s*(\d+)\.\s*</span>.*?'
    r'<b class="black">([^<]+)</b>.*?'
    r'<span class="green">([\d.,]+)</span>\s*</td>\s*<td>([\d.,]+)</td>',
    re.DOTALL,
)


def parse_order_list(html: str) -> list[OrderSummary]:
    """Parse the Bestellungen/Aufträge overview table (cmd=Auftraege).

    order_date/status extraction is based on a single observed example row
    (docs/extensions.md 2.7) - the column layout may not be this stable
    across all order/status types. Treat both fields as best-effort; only
    order_number/position are structurally guaranteed (they come from the
    row's own data-id).
    """
    results: list[OrderSummary] = []
    seen: set[str] = set()
    for order_number, position, row_html in _ORDER_ROW_RE.findall(html):
        key = f"{order_number}_{position}"
        if key in seen:
            continue
        seen.add(key)

        sort_values = _ORDER_SORT_VALUE_RE.findall(row_html)
        # The first data-sort-value in a row is the order number itself (repeated); the date is the second.
        order_date = sort_values[1] if len(sort_values) > 1 else None
        status_match = _ORDER_STATUS_RE.search(row_html)
        results.append(
            OrderSummary(
                order_number=order_number,
                position=position,
                order_date=order_date,
                status=html_lib.unescape(status_match.group(1).strip()) if status_match else None,
            )
        )
    return results


def parse_order_detail(order_number: str, html: str) -> Order:
    """Parse an order's line items (cmd=Auftraege/<order>&mode=detail&show_complete=1).

    Verified against one real multi-line order (docs/extensions.md 2.7).
    The two trailing quantity columns are assumed to be "delivered"/"open"
    by table convention (Menge/geliefert/offen is a standard German order
    confirmation layout) but weren't individually labeled in the markup -
    treat quantity_delivered with a bit less confidence than quantity_ordered.
    """
    items = [
        OrderItem(
            position=int(position),
            material_number=material_number,
            description=html_lib.unescape(description.strip()),
            quantity_ordered=_parse_decimal(qty_ordered),
            quantity_delivered=_parse_decimal(qty_delivered),
        )
        for material_number, position, description, qty_ordered, qty_delivered in _ORDER_ITEM_RE.findall(html)
    ]
    return Order(order_number=order_number, items=items)


# --- Cable lengths (extensions.md 2.10) ---

# "Bestand <Standort>" headers (e.g. "Zentrallager", "FEGA & Schmitt
# Erlangen") delimit one location's rows from the next - both locations
# render the identical row markup below, so rows must be scoped to the
# location block they came from rather than parsed globally.
_KLAENG_LOCATION_RE = re.compile(
    r'<div class="col-xs-12 text-center bold height lg bg-blue20">\s*Bestand\s+([^<]+?)\s*</div>'
)
# Anchored on the desktop ("col-sm-*") row layout only - the same data is
# repeated in a mobile ("col-xs-*", Trommelgröße/Anzahl/insgesamt only)
# block further down, which would double-count rows if not excluded.
_KLAENG_ROW_RE = re.compile(
    r'<div class="col-sm-3 height lg height-auto">\s*([^<]+?)\s*</div>\s*'
    r'<div class="col-sm-2 height lg height-auto">\s*([^<]+?)\s*</div>\s*'
    r'<div id="[^"]*" class="col-sm-2 height lg height-auto">\s*([^<]*?)\s*</div>\s*'
    r'<div class="col-sm-2 height lg height-auto text-center">\s*([^<]+?)\s*</div>\s*'
    r'<div class="col-sm-3 height lg height-auto text-right">\s*([^<]+?)\s*</div>',
    re.DOTALL,
)


def parse_cable_lengths(html: str) -> list[CableLength]:
    """Parse the "verfügbare Kabellängen" overlay (``cmd=AjaxKLaeng/<matnr>``)
    into available drums/remainder pieces per warehouse location.

    Only ever tested against one real cable article (extensions.md 2.10) -
    treat the exact column semantics (in particular "fest" vs. "zum
    Ablängen") as best-effort, though the underlying markup extraction
    itself is unambiguous.
    """
    locations = list(_KLAENG_LOCATION_RE.finditer(html))
    results: list[CableLength] = []
    for index, location_match in enumerate(locations):
        end = locations[index + 1].start() if index + 1 < len(locations) else len(html)
        block = html[location_match.end() : end]
        location = html_lib.unescape(location_match.group(1).strip())

        for packaging, length_mode, fixed_length_raw, count_raw, total_raw in _KLAENG_ROW_RE.findall(block):
            try:
                count = int(count_raw.strip())
            except ValueError:
                count = 0
            results.append(
                CableLength(
                    location=location,
                    packaging=html_lib.unescape(packaging.strip()),
                    is_cuttable="Ablängen" in length_mode,
                    fixed_length_m=_parse_decimal(fixed_length_raw) if fixed_length_raw.strip() else None,
                    count=count,
                    total_available_m=_parse_decimal(total_raw),
                )
            )
    return results

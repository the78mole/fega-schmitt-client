"""Data model for fega_schmitt_client.web.

Field names follow the terminology used in docs/extensions.md (section 2),
which in turn follows what the shop's own markup calls things (e.g.
"Warengruppe" -> category, "Meine Artikelnummer" -> own_article_number).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class ArticleSearchResult:
    """A single tile from a search/favorites/deals/category-list result page.

    Shared by search(), get_favorite_list(), get_deals(), get_daily_deals(),
    get_second_choice_articles() and list_articles_by_category() - they all
    render the same "data-compare" tile microformat (see extensions.md 2.3).
    """

    material_number: str
    description: str
    thumbnail_url: str | None
    detail_url: str


@dataclass
class ArticleDetail:
    """Parsed from an article's detail page (extensions.md 2.4/2.5/2.7)."""

    material_number: str
    ean: str | None
    manufacturer_item_number: str | None
    manufacturer_item_number_alt: str | None
    supplier_name: str | None
    supplier_number: str | None
    category_id: str | None
    category_name: str | None
    own_article_number: str | None


@dataclass
class ArticleImage:
    material_number: str
    url: str
    is_primary: bool


@dataclass
class CableLength:
    """One row of a cable article's "verfügbare Kabellängen" breakdown
    (extensions.md 2.10) - a specific drum or remainder piece.

    ``is_cuttable`` is True for "zum Ablängen" rows (order any partial
    length up to ``total_available_m``, may incur a cutting fee - see
    ``Article.cutting_fee``) and False for "fest" rows (take the row's full
    ``total_available_m`` as-is, no partial ordering). ``fixed_length_m`` is
    the drum's nominal length ("Trommelgröße") when the shop states one
    (e.g. a standard 500 m drum) and None for one-off remainder drums with
    no round nominal length.
    """

    location: str
    packaging: str
    is_cuttable: bool
    fixed_length_m: Decimal | None
    count: int
    total_available_m: Decimal


@dataclass
class Article:
    """Everything this library can extract for one article, built from a
    single detail-page fetch (extensions.md 2.4/2.5/2.7/2.9) rather than the
    one-fetch-per-field approach the individual get_article_*() methods used
    before this - they're now thin accessors on top of WebClient.get_article().

    ``documents`` is always an empty list for now: the underlying endpoint
    (``AjaxDetailDocs``) was found but every tested call returned an empty
    body, see extensions.md 2.9. The field exists so callers can already
    code against its eventual shape.

    ``cutting_fee`` (extensions.md 2.10) is only present on cable articles
    that are cut from a drum - None for everything else.

    ``description`` is the shop's article title (the same string
    ``ArticleSearchResult.description`` carries). The detail page itself
    doesn't state it in a form worth scraping, so it is threaded through
    from the search step that ``WebClient.get_article()`` performs anyway
    to find the detail URL. It is None when an ``Article`` is built
    straight from HTML via ``parse_article()`` without that search.
    """

    material_number: str
    fetched_at: datetime
    ean: str | None
    manufacturer_item_number: str | None
    manufacturer_item_number_alt: str | None
    supplier_name: str | None
    supplier_number: str | None
    category_id: str | None
    category_name: str | None
    own_article_number: str | None
    description: str | None = None
    cutting_fee: Decimal | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    images: list[ArticleImage] = field(default_factory=list)
    accessories: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    cross_sell: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable form (``json.dumps(article.to_dict())``) - a
        flat dataclass field dump wouldn't be, since ``fetched_at`` is a
        ``datetime`` and ``images`` holds nested dataclasses."""
        return {
            "material_number": self.material_number,
            "fetched_at": self.fetched_at.isoformat(),
            "description": self.description,
            "own_article_number": self.own_article_number,
            "ean": self.ean,
            "manufacturer_item_number": self.manufacturer_item_number,
            "manufacturer_item_number_alt": self.manufacturer_item_number_alt,
            "supplier_name": self.supplier_name,
            "supplier_number": self.supplier_number,
            "category": {"id": self.category_id, "name": self.category_name},
            "cutting_fee": str(self.cutting_fee) if self.cutting_fee is not None else None,
            "attributes": self.attributes,
            "images": [{"url": image.url, "is_primary": image.is_primary} for image in self.images],
            "accessories": self.accessories,
            "variants": self.variants,
            "alternatives": self.alternatives,
            "cross_sell": self.cross_sell,
            "documents": self.documents,
        }


@dataclass
class DealCampaign:
    """One entry from the cmd=Deal campaign overview (extensions.md 2.7).

    cmd=Deal lists campaigns, not articles - fetch a campaign's articles via
    WebClient.get_deal_articles(campaign_id).
    """

    campaign_id: str
    title: str


@dataclass
class CartSummary:
    """One entry of the "other carts" switcher on a Warenkorb page (extensions.md 2.7)."""

    cart_id: str
    name: str


@dataclass
class CartItem:
    position: int
    material_number: str
    description: str | None
    quantity: Decimal
    position_id: str
    comment: str


@dataclass
class Cart:
    cart_id: str | None
    name: str
    items: list[CartItem] = field(default_factory=list)


@dataclass
class OrderSummary:
    """One row of the Bestellungen/Aufträge overview (extensions.md 2.7)."""

    order_number: str
    position: str
    order_date: str | None
    status: str | None


@dataclass
class OrderItem:
    position: int
    material_number: str
    description: str | None
    quantity_ordered: Decimal | None
    quantity_delivered: Decimal | None


@dataclass
class Order:
    order_number: str
    items: list[OrderItem] = field(default_factory=list)

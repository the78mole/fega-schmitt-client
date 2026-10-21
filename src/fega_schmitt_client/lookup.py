"""Article search and lookup across all sources, cheapest first.

1. DATANORM (the local database from ``fega datanorm import``): article
   master data and the prices of the last delivery, no request at all.
2. SOAP price/availability service: today's price, surcharges and stock.
3. Webshop: only for what the other two cannot provide (images, technical
   attributes, accessories/variants, shop category, own article number,
   cutting fee), or for a search with no DATANORM hit. Article pages are
   read from the web cache (web/cache.py) while they are fresh enough.

Every source is optional. A failing SOAP or webshop request becomes a
warning on the result instead of an error, as long as some source knew the
article.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from types import TracebackType
from typing import TYPE_CHECKING

from .datanorm.store import DEFAULT_SEARCH_LIMIT, DatanormArticle, DatanormStore
from .exceptions import FegaApiError
from .models import PriceAvailRequestItem, PriceAvailResultItem
from .price_avail import FegaSchmittClient
from .web import Article, WebClient
from .web.cache import DEFAULT_MAX_AGE, WebArticleCache

if TYPE_CHECKING:
    from typing import Self


class ArticleNotFoundError(FegaApiError):
    """No source knows the requested article number."""


@dataclass
class SearchHit:
    material_number: str
    description: str | None
    source: str  # "datanorm" or "web"
    matched: str | None = None  # for DATANORM: material_number, ean, manufacturer_number or text


@dataclass
class ArticleInfo:
    """What the sources know about one article, each kept in its own shape.

    The properties merge the fields more than one source provides: DATANORM
    first, the webshop for articles that are not in the delivery.
    """

    material_number: str
    datanorm: DatanormArticle | None = None
    price_availability: PriceAvailResultItem | None = None
    web: Article | None = None
    web_from_cache: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        present = {"datanorm": self.datanorm, "soap": self.price_availability, "web": self.web}
        return [name for name, value in present.items() if value is not None]

    @property
    def description(self) -> str | None:
        return (self.datanorm and self.datanorm.description) or (self.web and self.web.description) or None

    @property
    def ean(self) -> str | None:
        return (self.datanorm and self.datanorm.ean) or (self.web and self.web.ean) or None

    @property
    def manufacturer_item_number(self) -> str | None:
        return (self.datanorm and self.datanorm.manufacturer_item_number) or (
            self.web and self.web.manufacturer_item_number
        ) or None  # fmt: skip


class ArticleLookup:
    """Combines the sources; any of them may be None.

    ``web_factory`` is called at most once, and only when the webshop is
    actually needed, so a DATANORM-only search never logs in to the shop.
    """

    def __init__(
        self,
        *,
        datanorm: DatanormStore | None = None,
        soap: FegaSchmittClient | None = None,
        web_factory: Callable[[], WebClient] | None = None,
        web_cache: WebArticleCache | None = None,
    ) -> None:
        self._datanorm = datanorm
        self._soap = soap
        self._web_factory = web_factory
        self._web_cache = web_cache
        self._web: WebClient | None = None

    def close(self) -> None:
        if self._web is not None:
            self._web.close()
            self._web = None
        if self._datanorm is not None:
            self._datanorm.close()
        if self._web_cache is not None:
            self._web_cache.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def datanorm_delivery_date(self) -> str | None:
        return self._datanorm.delivery_date if self._datanorm else None

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchHit]:
        """DATANORM first; the webshop only if DATANORM has no hit (or no database)."""
        if self._datanorm is not None:
            hits = self._datanorm.search(query, limit)
            if hits:
                return [SearchHit(h.material_number, h.description, "datanorm", h.matched) for h in hits]
        web = self._get_web()
        if web is None:
            return []
        return [SearchHit(r.material_number, r.description, "web") for r in web.search(query)[:limit]]

    def get_article(
        self,
        material_number: str,
        *,
        use_web: bool = True,
        max_age: timedelta = DEFAULT_MAX_AGE,
        refresh: bool = False,
    ) -> ArticleInfo:
        """``max_age`` is how old a cached shop page may be; ``refresh`` skips the cache."""
        info = ArticleInfo(material_number)
        if self._datanorm is not None:
            info.datanorm = self._datanorm.get_article(material_number)
        else:
            info.warnings.append("Keine DATANORM-Datenbank, erst `fega datanorm import` ausführen.")

        if self._soap is None:
            info.warnings.append("Preis/Verfügbarkeit (SOAP) nicht abgefragt: kein Zugang konfiguriert.")
        else:
            try:
                (result,) = self._soap.get_price_availability([PriceAvailRequestItem(material_number, 1)])
            except Exception as exc:  # noqa: BLE001 - one failing source must not hide the others
                info.warnings.append(f"Preis/Verfügbarkeit (SOAP) fehlgeschlagen: {exc}")
            else:
                if result.status == "error":
                    info.warnings.append(f"SOAP: {result.return_code} {result.return_code_text}")
                else:
                    info.price_availability = result

        if use_web:
            if self._web_cache is not None and not refresh:
                info.web = self._web_cache.get(material_number, max_age)
                info.web_from_cache = info.web is not None
            if info.web is None:
                try:
                    web = self._get_web()
                    if web is not None:
                        info.web = web.get_article(material_number)
                except Exception as exc:  # noqa: BLE001 - same as above
                    info.warnings.append(f"Webshop fehlgeschlagen: {exc}")
                else:
                    if info.web is not None and self._web_cache is not None:
                        self._web_cache.put(info.web)

        if not info.sources:
            raise ArticleNotFoundError(f"Artikel {material_number!r} nicht gefunden. " + " ".join(info.warnings))
        return info

    def _get_web(self) -> WebClient | None:
        if self._web is None and self._web_factory is not None:
            self._web = self._web_factory()
        return self._web

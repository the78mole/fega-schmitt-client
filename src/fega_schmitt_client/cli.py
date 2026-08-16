"""Command-line interface for fega-schmitt-client.

Installed as the ``fega`` console script (see ``[project.scripts]`` in
pyproject.toml, runnable stand-alone via ``uv tool install fega-schmitt-client``).
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import sys
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

import click

from . import FegaSchmittClient, PriceAvailRequestItem, PriceAvailResultItem
from .price_avail import DEFAULT_ENDPOINT
from .web import ArticleSearchResult, WebClient
from .web.client import DEFAULT_SECOND_CHOICE_DEAL_ID


@click.group()
@click.option(
    "--customer-number",
    envvar="FEGA_CUSTOMER_NUMBER",
    help="FEGA & Schmitt-Kundennummer (PARTNER_PURCHASER). Auch als FEGA_CUSTOMER_NUMBER.",
)
@click.option(
    "--shop-password",
    envvar="FEGA_SHOP_PASSWORD",
    help="Shop-Kennwort (LEGITIMATION_ID). Auch als FEGA_SHOP_PASSWORD.",
)
@click.option(
    "--endpoint",
    envvar="FEGA_ENDPOINT",
    default=DEFAULT_ENDPOINT,
    show_default=True,
    help="Abweichende Service-URL, z. B. für Tests gegen einen Mock-Server.",
)
@click.pass_context
def main(ctx: click.Context, customer_number: str | None, shop_password: str | None, endpoint: str) -> None:
    """fega - Kommandozeilen-Client für die FEGA & Schmitt SOAP-Preis-/Verfügbarkeitsschnittstelle."""
    ctx.ensure_object(dict)
    ctx.obj["customer_number"] = customer_number
    ctx.obj["shop_password"] = shop_password
    ctx.obj["endpoint"] = endpoint


@main.command("price-avail")
@click.argument("items", nargs=-1, required=True, metavar="ARTIKELNUMMER[:MENGE[:EINHEIT]]...")
@click.option("--json", "-j", "json_flag", is_flag=True, help="JSON-Ausgabe.")
@click.pass_context
def price_avail(ctx: click.Context, items: tuple[str, ...], json_flag: bool) -> None:
    """Preis und Verfügbarkeit für eine oder mehrere Artikelnummern abfragen.

    Jedes ARTIKELNUMMER-Argument hat die Form ARTIKELNUMMER[:MENGE[:EINHEIT]],
    z. B. "TEST123", "TEST123:5" oder "TEST123:5:MTR" (Menge default 1).

    \b
    Beispiele:
        fega price-avail TEST123
        fega price-avail TEST123:5:MTR 4711 -j
    """
    customer_number = ctx.obj["customer_number"]
    shop_password = ctx.obj["shop_password"]
    if not customer_number or not shop_password:
        click.echo(
            "Error: --customer-number/--shop-password (oder FEGA_CUSTOMER_NUMBER/FEGA_SHOP_PASSWORD) "
            "sind erforderlich.",
            err=True,
        )
        sys.exit(2)

    try:
        request_items = [_parse_item_arg(arg) for arg in items]
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    client = FegaSchmittClient(
        partner_purchaser=customer_number,
        legitimation_id=shop_password,
        endpoint=ctx.obj["endpoint"],
    )

    try:
        results = client.get_price_availability(request_items)
    except Exception as exc:  # noqa: BLE001 - CLI error boundary, converts any failure to a clean message
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if json_flag:
        click.echo(json.dumps([_result_to_json(r) for r in results], indent=2, ensure_ascii=False))
        return

    for result in results:
        click.echo(
            f"\n[{result.line_item_number}] {result.material_number}  "
            f"status={result.status}  ({result.return_code}: {result.return_code_text})"
        )
        if result.availability_status:
            click.echo(
                f"  Verfügbarkeit: {result.availability_status}  "
                f"Lager: {result.warehouse_name or '-'} ({result.warehouse_number or '-'})"
            )
        if result.net_amount is not None:
            click.echo(
                f"  Preis: {result.net_amount} EUR (Liste: {result.list_amount}, vor Zuschlag: {result.price_amount})"
            )
        for surcharge in result.surcharges:
            click.echo(f"    + {surcharge.text}: {surcharge.amount} EUR")
    click.echo()


def _parse_item_arg(arg: str) -> PriceAvailRequestItem:
    parts = arg.split(":")
    material_number = parts[0]
    if not material_number:
        raise ValueError(f"Ungültiges Artikel-Argument: '{arg}'")

    quantity = Decimal(1)
    if len(parts) >= 2 and parts[1]:
        try:
            quantity = Decimal(parts[1])
        except InvalidOperation as exc:
            raise ValueError(f"Ungültige Menge in '{arg}': '{parts[1]}'") from exc

    unit = parts[2] if len(parts) >= 3 and parts[2] else None
    return PriceAvailRequestItem(material_number=material_number, quantity=quantity, unit=unit)


def _result_to_json(result: PriceAvailResultItem) -> dict:
    data = asdict(result)
    for key in ("price_amount", "net_amount", "list_amount"):
        if data[key] is not None:
            data[key] = str(data[key])
    for surcharge in data["surcharges"]:
        surcharge["amount"] = str(surcharge["amount"])
    return data


# --- Web extension (fega_schmitt_client.web) ---
#
# Not an officially documented FEGA & Schmitt interface - see
# docs/extensions.md before relying on this in production. Uses the same
# credentials as price-avail (--customer-number/--shop-password or
# FEGA_CUSTOMER_NUMBER/FEGA_SHOP_PASSWORD on the top-level `fega` command),
# not repeated on each `web` subcommand.


@main.group("web")
def web_group() -> None:
    """Webshop-Zugriff (shop.fega.de) - Suche, Artikeldetails, Warenkorb, Bestellungen, ..."""


@contextlib.contextmanager
def _web_session(ctx: click.Context):
    customer_number = ctx.obj["customer_number"]
    shop_password = ctx.obj["shop_password"]
    if not customer_number or not shop_password:
        click.echo(
            "Error: --customer-number/--shop-password (oder FEGA_CUSTOMER_NUMBER/FEGA_SHOP_PASSWORD) "
            "sind erforderlich.",
            err=True,
        )
        sys.exit(2)
    try:
        with WebClient(customer_number=customer_number, shop_password=shop_password) as client:
            yield client
    except Exception as exc:  # noqa: BLE001 - CLI error boundary, converts any failure to a clean message
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


def _json_safe(value: object) -> object:
    """Recursively turn dataclasses/Decimal/datetime into plain JSON-safe types."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _json_safe(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _echo_json(value: object) -> None:
    click.echo(json.dumps(_json_safe(value), indent=2, ensure_ascii=False))


def _echo_tiles(results: list[ArticleSearchResult]) -> None:
    if not results:
        click.echo("Keine Treffer.")
        return
    for r in results:
        click.echo(f"{r.material_number}  {r.description}")


_json_option = click.option("--json", "-j", "json_flag", is_flag=True, help="JSON-Ausgabe.")


@web_group.command("search")
@click.argument("query")
@_json_option
@click.pass_context
def web_search(ctx: click.Context, query: str, json_flag: bool) -> None:
    """Artikel suchen (Artikelnummer, EAN, Herstellerteilenummer oder Freitext)."""
    with _web_session(ctx) as client:
        results = client.search(query)
    _echo_json(results) if json_flag else _echo_tiles(results)


@web_group.command("article")
@click.argument("material_number")
@_json_option
@click.pass_context
def web_article(ctx: click.Context, material_number: str, json_flag: bool) -> None:
    """Alle bekannten Daten zu einem Artikel (EAN, Hersteller, Kategorie, Attribute, Bilder, Zubehör/Varianten/...)."""
    with _web_session(ctx) as client:
        article = client.get_article(material_number)
    if json_flag:
        click.echo(json.dumps(article.to_dict(), indent=2, ensure_ascii=False))
        return
    click.echo(f"{article.material_number}  EAN={article.ean or '-'}")
    click.echo(f"  Bezeichnung: {article.description or '-'}")
    click.echo(f"  Hersteller: {article.supplier_name or '-'} ({article.manufacturer_item_number or '-'})")
    click.echo(f"  Kategorie: {article.category_name or '-'} ({article.category_id or '-'})")
    click.echo(f"  Meine Artikelnummer: {article.own_article_number or '-'}")
    if article.cutting_fee is not None:
        click.echo(f"  Schnittkosten: {article.cutting_fee} EUR")
    click.echo(f"  Attribute: {len(article.attributes)}, Bilder: {len(article.images)}")
    click.echo(
        f"  Zubehör: {len(article.accessories)}, Varianten: {len(article.variants)}, "
        f"Alternativen: {len(article.alternatives)}, Oft zusammengekauft: {len(article.cross_sell)}"
    )


@web_group.command("images")
@click.argument("material_number")
@_json_option
@click.pass_context
def web_images(ctx: click.Context, material_number: str, json_flag: bool) -> None:
    """Bild-URLs eines Artikels."""
    with _web_session(ctx) as client:
        images = client.get_article_images(material_number)
    if json_flag:
        _echo_json(images)
        return
    if not images:
        click.echo("Keine Bilder gefunden.")
        return
    for image in images:
        click.echo(f"{'[primär] ' if image.is_primary else '         '}{image.url}")


@web_group.command("category")
@click.argument("material_number")
@click.pass_context
def web_category(ctx: click.Context, material_number: str) -> None:
    """Warengruppe eines Artikels."""
    with _web_session(ctx) as client:
        category_id, category_name = client.get_article_category(material_number)
    click.echo(f"{category_id or '-'}  {category_name or '-'}")


@web_group.command("article-number")
@click.argument("material_number")
@click.pass_context
def web_article_number(ctx: click.Context, material_number: str) -> None:
    """Eigene Artikelnummer ("Meine Artikelnummer") eines Artikels lesen."""
    with _web_session(ctx) as client:
        own_number = client.get_article_number(material_number)
    click.echo(own_number or "(nicht gesetzt)")


@web_group.command("set-article-number")
@click.argument("material_number")
@click.argument("value")
@click.pass_context
def web_set_article_number(ctx: click.Context, material_number: str, value: str) -> None:
    """Eigene Artikelnummer für einen Artikel setzen.

    Schreibt auf den echten Account - siehe docs/extensions.md 2.8 für den
    Stand der End-to-End-Verifikation dieses Endpunkts.
    """
    with _web_session(ctx) as client:
        client.set_article_number(material_number, value)
    click.echo(f"OK: {material_number} -> {value!r}")


@web_group.command("attributes")
@click.argument("material_number")
@_json_option
@click.pass_context
def web_attributes(ctx: click.Context, material_number: str, json_flag: bool) -> None:
    """Technische Attribute eines Artikels (Produktdetails-Grid, variiert je Warengruppe)."""
    with _web_session(ctx) as client:
        attributes = client.get_article_attributes(material_number)
    if json_flag:
        _echo_json(attributes)
        return
    if not attributes:
        click.echo("Keine Attribute gefunden.")
        return
    for label, val in attributes.items():
        click.echo(f"{label}: {val}")


def _material_number_list_command(name: str, doc: str, method_name: str) -> None:
    """Register a `fega web <name> MATERIAL_NUMBER` command for one of the
    Article.{accessories,variants,alternatives,cross_sell} list[str] fields -
    they all share the same shape, hence one factory instead of four
    near-identical command bodies."""

    @web_group.command(name, help=doc)
    @click.argument("material_number")
    @_json_option
    @click.pass_context
    def command(ctx: click.Context, material_number: str, json_flag: bool) -> None:
        with _web_session(ctx) as client:
            numbers = getattr(client, method_name)(material_number)
        if json_flag:
            _echo_json(numbers)
            return
        click.echo(", ".join(numbers) if numbers else "Keine Einträge.")


_material_number_list_command("accessories", "Zubehör-Artikelnummern eines Artikels.", "get_article_accessories")
_material_number_list_command(
    "variants", "Varianten-Artikelnummern eines Artikels (Farbe/Größe/...).", "get_article_variants"
)
_material_number_list_command("alternatives", "Alternativen-Artikelnummern eines Artikels.", "get_article_alternatives")
_material_number_list_command("cross-sell", 'Artikelnummern aus "Oft zusammengekauft mit".', "get_article_cross_sell")


@web_group.command("cutting-fee")
@click.argument("material_number")
@click.pass_context
def web_cutting_fee(ctx: click.Context, material_number: str) -> None:
    """Schnittkosten für einen Kabelartikel, falls angegeben."""
    with _web_session(ctx) as client:
        fee = client.get_cutting_fee(material_number)
    click.echo(f"{fee} EUR" if fee is not None else "Keine Schnittkosten angegeben.")


@web_group.command("cable-lengths")
@click.argument("material_number")
@_json_option
@click.pass_context
def web_cable_lengths(ctx: click.Context, material_number: str, json_flag: bool) -> None:
    """Verfügbare Kabellängen (Trommeln/Reststücke) eines Kabelartikels je Lagerstandort."""
    with _web_session(ctx) as client:
        lengths = client.get_cable_lengths(material_number)
    if json_flag:
        _echo_json(lengths)
        return
    if not lengths:
        click.echo("Keine Kabellängen gefunden.")
        return
    for entry in lengths:
        mode = "zum Ablängen" if entry.is_cuttable else "fest"
        size = f", {entry.fixed_length_m} m/Trommel" if entry.fixed_length_m is not None else ""
        click.echo(
            f"[{entry.location}] {entry.packaging}, {mode}{size}  {entry.count}x, insgesamt {entry.total_available_m} m"
        )


@web_group.command("list-category")
@click.argument("category_id")
@_json_option
@click.pass_context
def web_list_category(ctx: click.Context, category_id: str, json_flag: bool) -> None:
    """Artikel einer UWG-Kategorie auflisten (siehe docs/fega_categories.md für IDs)."""
    with _web_session(ctx) as client:
        results = client.list_articles_by_category(category_id)
    _echo_json(results) if json_flag else _echo_tiles(results)


@web_group.command("favorites")
@_json_option
@click.pass_context
def web_favorites(ctx: click.Context, json_flag: bool) -> None:
    """Merkliste/Favoriten."""
    with _web_session(ctx) as client:
        results = client.get_favorite_list()
    _echo_json(results) if json_flag else _echo_tiles(results)


@web_group.command("deals")
@_json_option
@click.pass_context
def web_deals(ctx: click.Context, json_flag: bool) -> None:
    """Aktionsangebote-Kampagnen (Artikel einer Kampagne: `fega web deal-articles KAMPAGNEN-ID`)."""
    with _web_session(ctx) as client:
        campaigns = client.get_deal_campaigns()
    if json_flag:
        _echo_json(campaigns)
        return
    if not campaigns:
        click.echo("Keine Kampagnen gefunden.")
        return
    for c in campaigns:
        click.echo(f"{c.campaign_id}  {c.title}")


@web_group.command("deal-articles")
@click.argument("campaign_id")
@_json_option
@click.pass_context
def web_deal_articles(ctx: click.Context, campaign_id: str, json_flag: bool) -> None:
    """Artikel einer Aktionsangebote-Kampagne (ID via `fega web deals`)."""
    with _web_session(ctx) as client:
        results = client.get_deal_articles(campaign_id)
    _echo_json(results) if json_flag else _echo_tiles(results)


@web_group.command("daily-deals")
@_json_option
@click.pass_context
def web_daily_deals(ctx: click.Context, json_flag: bool) -> None:
    """Tagesangebote (kann leer sein, siehe docs/extensions.md 2.7)."""
    with _web_session(ctx) as client:
        results = client.get_daily_deals()
    _echo_json(results) if json_flag else _echo_tiles(results)


@web_group.command("second-choice")
@click.option(
    "--deal-id", default=DEFAULT_SECOND_CHOICE_DEAL_ID, show_default=True, help="Kampagnen-ID für 2. Wahl/B-Ware."
)
@_json_option
@click.pass_context
def web_second_choice(ctx: click.Context, deal_id: str, json_flag: bool) -> None:
    """B-Ware-/Zweitwahl-Artikel."""
    with _web_session(ctx) as client:
        results = client.get_second_choice_articles(deal_id)
    _echo_json(results) if json_flag else _echo_tiles(results)


@web_group.command("cart")
@click.argument("cart_id", required=False)
@_json_option
@click.pass_context
def web_cart(ctx: click.Context, cart_id: str | None, json_flag: bool) -> None:
    """Einen Warenkorb anzeigen (ohne CART_ID: der aktuell offene)."""
    with _web_session(ctx) as client:
        cart = client.get_cart(cart_id)
    if json_flag:
        _echo_json(cart)
        return
    click.echo(f"{cart.name} (ID: {cart.cart_id or '-'})")
    if not cart.items:
        click.echo("  (leer)")
    for item in cart.items:
        click.echo(f"  {item.material_number}  {item.quantity}x" + (f"  [{item.comment}]" if item.comment else ""))


@web_group.command("carts")
@_json_option
@click.pass_context
def web_carts(ctx: click.Context, json_flag: bool) -> None:
    """Alle Warenkörbe auflisten."""
    with _web_session(ctx) as client:
        carts = client.get_cart_list()
    if json_flag:
        _echo_json(carts)
        return
    if not carts:
        click.echo("Keine Warenkörbe gefunden.")
        return
    for c in carts:
        click.echo(f"{c.cart_id}  {c.name}")


@web_group.command("orders")
@_json_option
@click.pass_context
def web_orders(ctx: click.Context, json_flag: bool) -> None:
    """Bestellungen auflisten."""
    with _web_session(ctx) as client:
        orders = client.get_order_list()
    if json_flag:
        _echo_json(orders)
        return
    if not orders:
        click.echo("Keine Bestellungen gefunden.")
        return
    for o in orders:
        click.echo(f"{o.order_number}/{o.position}  {o.order_date or '-'}  {o.status or '-'}")


@web_group.command("order")
@click.argument("order_number")
@_json_option
@click.pass_context
def web_order(ctx: click.Context, order_number: str, json_flag: bool) -> None:
    """Positionen einer Bestellung anzeigen."""
    with _web_session(ctx) as client:
        order = client.get_order(order_number)
    if json_flag:
        _echo_json(order)
        return
    click.echo(f"Bestellung {order.order_number}")
    for item in order.items:
        click.echo(
            f"  [{item.position}] {item.material_number}  {item.description or '-'}  "
            f"bestellt={item.quantity_ordered}  geliefert={item.quantity_delivered}"
        )


if __name__ == "__main__":
    main()

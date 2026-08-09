"""Command-line interface for fega-schmitt-client.

Installed as the ``fega`` console script (see ``[project.scripts]`` in
pyproject.toml, runnable stand-alone via ``uv tool install fega-schmitt-client``).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal, InvalidOperation

import click

from . import FegaSchmittClient, PriceAvailRequestItem, PriceAvailResultItem
from .price_avail import DEFAULT_ENDPOINT


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


if __name__ == "__main__":
    main()

"""Data model for the FEGA & Schmitt price/availability service.

Field names mirror the XML structure from the spec 1:1 (see
docs/architecture.md, section 5) so no information is lost on the way in or
out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

AvailabilityStatus = Literal["V", "T", "N", "B", "0"]
ResultStatus = Literal["ok", "hint", "error"]


@dataclass
class PriceAvailRequestItem:
    """A single requested article line (``ITEM`` in ``PRICE_AVAIL_REQUEST/ITEM_LIST``)."""

    material_number: str
    quantity: Decimal | int | float | str
    unit: str | None = None
    line_item_number: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))


@dataclass
class Surcharge:
    """A single ``SURCHARGE_REBATE`` entry (e.g. copper/metal surcharge)."""

    code: str
    text: str
    amount: Decimal


@dataclass
class PriceAvailResultItem:
    """Result for a single requested article (``ITEM`` in ``PRICE_AVAIL_RESPONSE/ITEM_LIST``)."""

    line_item_number: int
    material_number: str
    status: ResultStatus
    return_code: str
    return_code_text: str
    availability_status: AvailabilityStatus | None = None
    warehouse_number: str | None = None
    warehouse_name: str | None = None
    price_amount: Decimal | None = None
    net_amount: Decimal | None = None
    list_amount: Decimal | None = None
    surcharges: list[Surcharge] = field(default_factory=list)

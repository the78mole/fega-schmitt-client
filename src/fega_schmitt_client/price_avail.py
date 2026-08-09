"""SOAP client for the FEGA & Schmitt price/availability service."""

from __future__ import annotations

import uuid

import httpx

from ._soap import build_request, parse_response
from .exceptions import FegaAuthError, FegaTransportError
from .models import PriceAvailRequestItem, PriceAvailResultItem

DEFAULT_ENDPOINT = "https://soap.fega.de/priceavail.php"

# Section 1 of the spec says "max. 1000 Artikel"; the format table in 3.1.1
# says "maximal 999 Artikelelemente" for the item list. We enforce the
# stricter, more specific limit from the format definition.
MAX_ITEMS = 999


class FegaSchmittClient:
    """Client for FEGA & Schmitt's SOAP price/availability web service.

    Credentials are passed explicitly and never read from environment
    variables here - that is the caller's responsibility (see
    docs/architecture.md, section 6).
    """

    def __init__(
        self,
        *,
        partner_purchaser: str,
        legitimation_id: str,
        partner_company: str = "50",
        eshop_id: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._partner_purchaser = partner_purchaser
        self._legitimation_id = legitimation_id
        self._partner_company = partner_company
        self._eshop_id = eshop_id
        self._endpoint = endpoint
        self._timeout = timeout
        self._http_client = http_client

    def get_price_availability(
        self,
        items: list[PriceAvailRequestItem],
        *,
        shipment_type: str = "01",
        partner_warehouse: str | None = None,
        request_currency: str = "EUR",
        postal_code: str | None = None,
        country_code: str | None = None,
        transaction_id: str | None = None,
    ) -> list[PriceAvailResultItem]:
        """Query price and availability for up to :data:`MAX_ITEMS` articles.

        Errors on individual positions are reported per item in the result
        (``status="error"``); only transport-level failures (timeout,
        non-200 HTTP status, malformed SOAP, rejected credentials) raise.
        """
        items = list(items)
        if not items:
            raise ValueError("items darf nicht leer sein")
        if len(items) > MAX_ITEMS:
            raise ValueError(f"maximal {MAX_ITEMS} Artikel pro Anfrage erlaubt, erhalten: {len(items)}")

        request_body = build_request(
            items,
            partner_purchaser=self._partner_purchaser,
            legitimation_id=self._legitimation_id,
            partner_company=self._partner_company,
            eshop_id=self._eshop_id,
            transaction_id=transaction_id or uuid.uuid4().hex,
            shipment_type=shipment_type,
            partner_warehouse=partner_warehouse,
            request_currency=request_currency,
            postal_code=postal_code,
            country_code=country_code,
        )

        response = self._post(request_body)

        if response.status_code in (401, 403):
            raise FegaAuthError(f"FEGA & Schmitt hat die Anmeldedaten abgelehnt (HTTP {response.status_code})")
        if response.status_code != 200:
            raise FegaTransportError(f"Unerwarteter HTTP-Status {response.status_code} von {self._endpoint}")

        parsed = parse_response(response.content)
        return parsed.items

    def _post(self, body: bytes) -> httpx.Response:
        client = self._http_client or httpx.Client(timeout=self._timeout)
        owns_client = self._http_client is None
        try:
            return client.post(
                self._endpoint,
                content=body,
                headers={"Content-Type": "text/xml; charset=ISO-8859-1"},
            )
        except httpx.TimeoutException as exc:
            raise FegaTransportError(f"Zeitüberschreitung bei Anfrage an {self._endpoint}") from exc
        except httpx.HTTPError as exc:
            raise FegaTransportError(f"HTTP-Anfrage an {self._endpoint} fehlgeschlagen: {exc}") from exc
        finally:
            if owns_client:
                client.close()

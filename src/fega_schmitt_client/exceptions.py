"""Exceptions raised by fega_schmitt_client."""

from __future__ import annotations


class FegaApiError(Exception):
    """Base exception for all fega-schmitt-client errors."""


class FegaAuthError(FegaApiError):
    """Raised when FEGA & Schmitt rejects the customer number/shop password.

    The SOAP spec (Schnittstellenbeschreibung_SOAP.pdf) does not document a
    dedicated return code for "Anmeldedaten komplett abgelehnt" - this is
    raised on HTTP 401/403 responses as a best-effort interpretation until
    confirmed against the real service.
    """


class FegaTransportError(FegaApiError):
    """Raised for transport-level failures: timeout, non-200 HTTP status, or malformed SOAP XML."""

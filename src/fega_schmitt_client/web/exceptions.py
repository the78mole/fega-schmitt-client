"""Exceptions raised by fega_schmitt_client.web.

Separate from the SOAP client's exceptions (fega_schmitt_client.exceptions)
because this extension talks to an undocumented, scraped web frontend
rather than a documented protocol - see docs/extensions.md, section 10.
Both still subclass FegaApiError so callers can catch that alone if they
don't care which part of the library raised.
"""

from __future__ import annotations

from ..exceptions import FegaApiError


class FegaLoginError(FegaApiError):
    """Raised when the webshop rejects login or a session unexpectedly expires mid-use."""


class FegaScrapingError(FegaApiError):
    """Raised when a response's HTML doesn't contain the data a parser expects.

    This is the "the frontend markup changed under us" failure mode described
    in docs/extensions.md - distinct from FegaLoginError (auth problem) and
    FegaTransportError (network/HTTP-status problem, reused from the SOAP
    client's exceptions since it's the same kind of failure).
    """

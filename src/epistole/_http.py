"""The HTTP transports send each request through `request`, on the one `httpx2.Client` a connection holds.

`Tokens` is the private shape `connect()` adapts each credential to (ADR-0011). Importing this module imports `httpx2`, so a backend imports it only after checking its extra.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Protocol

import httpx2

if TYPE_CHECKING:
    from epistole._backend import TokenCredential

_TIMEOUT = 60
"""Seconds for connect, read, write and pool, on token and mail endpoint requests alike. No setting changes it (ADR-0009)."""


class Tokens(Protocol):
    """The tokens a connection's requests carry, in the one shape `connect()` adapts every credential to.

    `TokenCredential` has no method that forces a new token, so `refresh` adds one for the `401` retry.
    """

    def token(self) -> str:
        """Return an access token, reusing one that has not expired."""
        ...

    def refresh(self) -> str:
        """Return a new access token, because the service rejected the last one."""
        ...


class ForeignTokens:
    """The tokens of a caller's `TokenCredential`, which caches its own (ADR-0011)."""

    def __init__(self, credential: TokenCredential, scope: str, /) -> None:
        self._credential = credential
        self._scope = scope

    def token(self) -> str:
        """Return the token `get_token` returns."""
        return self._credential.get_token(self._scope).token

    refresh = token


def client() -> httpx2.Client:
    """Return the client a connection sends every request on, its token requests included."""
    return httpx2.Client(timeout=_TIMEOUT)


def request(
    client: httpx2.Client,
    tokens: Tokens,
    method: str,
    url: str,
    *,
    content: bytes | None = None,
) -> httpx2.Response:
    """Send one request with a bearer token, and on `401` refresh once and retry it once.

    `content` is a JSON body. The caller serializes it, so a pre-check can measure the bytes sent (ADR-0019). The budget is per request, not per send, because a token can expire partway through a send of several requests (ADR-0009).
    """
    headers = {"Authorization": f"Bearer {tokens.token()}"}
    if content is not None:
        headers["Content-Type"] = "application/json"

    response: httpx2.Response = client.request(
        method, url, headers=headers, content=content
    )
    if response.status_code == HTTPStatus.UNAUTHORIZED:
        headers["Authorization"] = f"Bearer {tokens.refresh()}"
        response = client.request(method, url, headers=headers, content=content)

    return response.raise_for_status()


def retry_after(response: httpx2.Response) -> float | None:
    """Return the delay in `Retry-After` as seconds, from either RFC 9110 form, or `None` when the response has no header that parses."""
    value: str | None = response.headers.get("Retry-After")
    if value is None:
        return None

    if value.isascii() and value.isdigit():
        return float(value)

    try:
        when: datetime = parsedate_to_datetime(value)
    except ValueError:
        return None

    # RFC 9110: an asctime-date carries no zone and is in UTC.
    when = when if when.tzinfo else when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())

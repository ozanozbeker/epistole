"""`RESTTransport` is the base of the Gmail and Graph transports, which send each request with a bearer token on the one `httpx2.Client` a connection holds.

`request_mapping` holds the rows every HTTP mapping shares, the token adapters' included. Importing this module imports `httpx2`, so a backend imports it only after checking its extra.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, ClassVar, Self

import httpx2

from epistole import _tokens
from epistole.exceptions import ProviderError, TransportError

if TYPE_CHECKING:
    from collections.abc import Generator

    from epistole._tokens import Credential, Purpose, Tokens
    from epistole.exceptions import EpistoleError

_TIMEOUT = 60
"""Seconds for connect, read, write and pool, on token and mail endpoint requests alike. No setting changes it (ADR-0009)."""


def client() -> httpx2.Client:
    """Return the client a connection sends every request on, its token requests included."""
    return httpx2.Client(timeout=_TIMEOUT)


@contextmanager
def request_mapping(vendor: str) -> Generator[None]:
    """Raise the Epistole error for a request that failed, or for a reply that could not be read (ADR-0004).

    A status outside 2xx passes, so the caller maps it by its own table.
    """
    try:
        yield
    except httpx2.HTTPStatusError:
        raise
    except httpx2.TransportError as error:
        msg = f"the request to {vendor} failed: {error}"
        raise TransportError(msg) from error
    except httpx2.HTTPError as error:
        msg = f"{vendor}'s reply could not be read: {error}"
        raise ProviderError(msg) from error


class RESTTransport(ABC):
    """The connection lifecycle `_GmailTransport` and `_GraphTransport` share: one client, the tokens, and the `401` retry.

    A subclass sets `vendor` and `purpose`, and supplies `_mapped` and `submit`. Each keeps its whole status table, because ADR-0004 documents one table per backend and the order of its rows matters.
    """

    vendor: ClassVar[str]
    """The owner of the service, as the mapping's messages name it."""

    purpose: ClassVar[Purpose]
    """What the connection's tokens are for."""

    def __init__(self, client: httpx2.Client, tokens: Tokens, /) -> None:
        self._client = client
        self._tokens = tokens

    @classmethod
    def connect(cls, credential: Credential) -> Self:
        """Open the client, build the tokens, and get the first token, closing the client on failure."""
        opened: httpx2.Client = client()
        with ExitStack() as on_failure:
            on_failure.callback(opened.close)
            tokens: Tokens = _tokens.tokens(credential, cls.purpose, opened)
            tokens.token()
            on_failure.pop_all()

        return cls(opened, tokens)

    def request(
        self, method: str, url: str, *, content: bytes | None = None
    ) -> httpx2.Response:
        """Send one request with a bearer token, and on `401` refresh once and retry it once.

        `content` is a JSON body. The caller serializes it, so a pre-check can measure the bytes sent (ADR-0019). The budget is per request, not per send, because a token can expire partway through a send of several requests (ADR-0009).

        Only the requests run under `mapping`. Each issued `Tokens` maps its own errors, and an error from a caller's `get_token` propagates unchanged (ADR-0009).
        """
        headers = {"Authorization": f"Bearer {self._tokens.token()}"}
        if content is not None:
            headers["Content-Type"] = "application/json"

        with self.mapping():
            response: httpx2.Response = self._client.request(
                method, url, headers=headers, content=content
            )
            if response.status_code != HTTPStatus.UNAUTHORIZED:
                return response.raise_for_status()

        headers["Authorization"] = f"Bearer {self._tokens.refresh()}"
        with self.mapping():
            return self._client.request(
                method, url, headers=headers, content=content
            ).raise_for_status()

    def close(self) -> None:
        """Close the client."""
        self._client.close()

    @classmethod
    @contextmanager
    def mapping(cls) -> Generator[None]:
        """Raise the Epistole error for a native failure, by the subclass's status table and `request_mapping`'s rows (ADR-0004)."""
        try:
            with request_mapping(cls.vendor):
                yield
        except httpx2.HTTPStatusError as error:
            raise cls._mapped(error.response) from error

    @staticmethod
    @abstractmethod
    def _mapped(response: httpx2.Response) -> EpistoleError:
        """Return the Epistole error for a status outside 2xx."""


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

"""`_GmailTransport` posts each message to the Gmail API, and `_Request` sends `google-auth`'s token requests on the connection's client.

`epistole.gmail` imports this module only after checking the extra, because it imports `httpx2` and `google-auth`.
"""

from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, NamedTuple, cast, override

import httpx2
from google.auth.credentials import TokenState
from google.auth.exceptions import GoogleAuthError
from google.auth.exceptions import TransportError as GoogleTransportError
from google.auth.transport import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

from epistole import _http
from epistole._rfc5322 import build
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RejectedError,
    ThrottledError,
    TransportError,
)
from epistole.gmail import AuthorizedUser, ServiceAccount

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from google.auth.credentials import Credentials

    from epistole._backend import Submission, TokenCredential
    from epistole._result import Refusal

_SCOPE = "https://www.googleapis.com/auth/gmail.send"
"""Narrower than the `https://mail.google.com/` SMTP needs, which also grants reading and deleting messages (ADR-0011)."""

_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
"""`me` names the mailbox the access token was issued for (ADR-0011)."""

_MAX_BYTES = 36_700_160
"""The v1 discovery document's `maxSize` for `messages.send`: 35 MiB of RFC 5322 message (ADR-0019)."""

_MAX_RECIPIENTS = 500
"""Google's API usage limits page, taken over a Workspace page that says 2,000 (ADR-0019)."""

_THROTTLED = frozenset(
    {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded"}
)
"""The `errors[].reason` values that make a `403` a `ThrottledError` (ADR-0004)."""


def connect(
    credential: ServiceAccount | AuthorizedUser | TokenCredential,
) -> _GmailTransport:
    """Build the client and the tokens, and get the first token."""
    client: httpx2.Client = _http.client()
    with ExitStack() as on_failure:
        on_failure.callback(client.close)
        tokens: _http.Tokens = _tokens(credential, client)
        with _mapping():
            tokens.token()

        on_failure.pop_all()

    return _GmailTransport(client, tokens)


def _tokens(
    credential: ServiceAccount | AuthorizedUser | TokenCredential,
    client: httpx2.Client,
) -> _http.Tokens:
    """Build the tokens for `credential`, reading its file if it has one."""
    match credential:
        case ServiceAccount(path=path, subject=subject):
            credentials: Credentials = (
                ServiceAccountCredentials.from_service_account_file(
                    path, scopes=[_SCOPE], subject=subject
                )
            )
        case AuthorizedUser(path=path):
            credentials = UserCredentials.from_authorized_user_file(
                path, scopes=[_SCOPE]
            )
        case _:
            return _http.ForeignTokens(credential, _SCOPE)

    return _GoogleTokens(credentials, _Request(client))


class _GmailTransport:
    """`GmailBackend` opens this transport, which holds the connection's client and tokens."""

    def __init__(self, client: httpx2.Client, tokens: _http.Tokens, /) -> None:
        self._client = client
        self._tokens = tokens

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Post the RFC 5322 message as base64url `raw`."""
        recipients: int = len(submission.message.recipients)
        if recipients > _MAX_RECIPIENTS:
            msg = f"the message has {recipients} recipients, and Gmail accepts at most {_MAX_RECIPIENTS}."
            raise RejectedError(msg)

        data: bytes = build(submission).as_bytes()
        if len(data) > _MAX_BYTES:
            msg = f"the message is {len(data):,} bytes once encoded, and Gmail accepts at most {_MAX_BYTES:,}."
            raise RejectedError(msg)

        raw: str = base64.urlsafe_b64encode(data).decode("ascii")
        with _mapping():
            _http.request(self._client, self._tokens, "POST", _SEND, json={"raw": raw})

        return {}

    def close(self) -> None:
        """Close the client."""
        self._client.close()


@contextmanager
def _mapping() -> Generator[None]:
    """Raise the Epistole error for a native failure, by the Gmail mapping in ADR-0004."""
    try:
        yield
    except httpx2.HTTPStatusError as error:
        raise _mapped(error.response) from error
    except httpx2.TransportError as error:
        msg = f"the request to Google failed: {error}"
        raise TransportError(msg) from error
    except httpx2.HTTPError as error:
        msg = f"Google's reply could not be read: {error}"
        raise ProviderError(msg) from error
    except GoogleAuthError as error:
        # _Request raises google-auth's TransportError from httpx2's, so a network failure is one level down (ADR-0009).
        network: BaseException | None = error.__cause__
        if isinstance(network, httpx2.TransportError):
            msg = f"the token request to Google failed: {network}"
            raise TransportError(msg) from network

        msg = f"the credential could not get an access token: {error}"
        raise AuthenticationError(msg) from error


def _mapped(response: httpx2.Response) -> EpistoleError:
    """Return the Epistole error for a status outside 2xx, preferring a row qualified by `errors[].reason` (ADR-0004)."""
    status: int = response.status_code
    reason, detail = _envelope(response)
    label: str = f"{status} {reason}" if reason else str(status)
    msg = f"Gmail replied {label}: {detail}"
    if status == HTTPStatus.TOO_MANY_REQUESTS or (
        status == HTTPStatus.FORBIDDEN and reason in _THROTTLED
    ):
        return ThrottledError(msg, retry_after=_http.retry_after(response))

    if status in {HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND} or (
        status == HTTPStatus.FORBIDDEN and reason == "domainPolicy"
    ):
        return RejectedError(msg)

    if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        return AuthenticationError(msg)

    return ProviderError(msg)


def _envelope(response: httpx2.Response) -> tuple[str, str]:
    """Return the first `errors[].reason` and the `message` of Google's error envelope."""
    try:
        error: dict[str, Any] = response.json()["error"]
        errors: list[dict[str, Any]] = error.get("errors") or [{}]
        return str(errors[0].get("reason", "")), str(error.get("message", ""))
    except (ValueError, LookupError, TypeError, AttributeError):
        return "", response.reason_phrase


class _GoogleTokens:
    """The tokens of a `google-auth` credential."""

    def __init__(self, credentials: Credentials, request: _Request, /) -> None:
        self._credentials = credentials
        self._request = request

    def token(self) -> str:
        """Return the credential's token, refreshing it once it is within google-auth's expiry margin."""
        # before_request would also start google-auth's background Regional Access Boundary lookup on this client.
        if self._credentials.token_state is not TokenState.FRESH:
            return self.refresh()

        return cast("str", self._credentials.token)

    def refresh(self) -> str:
        """Refresh the credential's token, even before its expiry."""
        self._credentials.refresh(self._request)
        return cast("str", self._credentials.token)


class _Request(Request):
    """A request adapter that sends `google-auth`'s token requests on the connection's client, so they share its timeout, proxy and CA (ADR-0009)."""

    def __init__(self, client: httpx2.Client, /) -> None:
        self._client = client

    @override
    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: object,
    ) -> _Response:
        """Ignore `timeout`, because the client's 60 seconds covers token requests too (ADR-0009)."""
        try:
            response = self._client.request(method, url, content=body, headers=headers)
        except httpx2.TransportError as error:
            raise GoogleTransportError(error) from error

        return _Response(response.status_code, response.headers, response.content)


class _Response(NamedTuple):
    """The status, headers and body of an `httpx2` response, under the names `google-auth` reads."""

    status: int
    headers: Mapping[str, str]
    data: bytes

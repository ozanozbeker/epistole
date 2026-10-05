"""`_google_auth` adapts `google-auth` to `Tokens`, and `_Request` sends its token requests on the connection's client.

`_tokens` imports this module only for a Gmail value, because it imports `google-auth` and `httpx2`. Each token call maps its own errors, because SMTP has no mail mapping around its token.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, override

import httpx2
from google.auth.credentials import TokenState
from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.exceptions import TransportError as GoogleTransportError
from google.auth.transport import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

from epistole import _http
from epistole._tokens import REPLY_ERRORS, status_error, usable
from epistole.exceptions import AuthenticationError, ProviderError, TransportError
from epistole.gmail import AuthorizedUser, ServiceAccount

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from google.auth.credentials import Credentials

    from epistole._tokens import Tokens


def tokens(
    credential: ServiceAccount | AuthorizedUser,
    scope: str,
    client: httpx2.Client,
    /,
) -> Tokens:
    """Build the tokens for `credential`, reading its file if it has one.

    The build runs outside `_mapping`, so a malformed key file raises `google-auth`'s own error (`docs/spec.md`).
    """
    match credential:
        case ServiceAccount(path=path, subject=subject):
            credentials: Credentials = (
                ServiceAccountCredentials.from_service_account_file(
                    path, scopes=[scope], subject=subject
                )
            )
        case AuthorizedUser(path=path):
            consent: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
            # Every connect() requests a token for this scope, so an expired or revoked refresh token raises there (ADR-0011).
            consent.pop("token", None)
            consent.pop("expiry", None)
            credentials = UserCredentials.from_authorized_user_info(
                consent, scopes=[scope]
            )

    return _GoogleTokens(credentials, _Request(client))


@contextmanager
def _mapping() -> Generator[None]:
    """Raise the Epistole error for a failed token request, by the Gmail token rows in ADR-0009."""
    try:
        with _http.request_mapping("Google", token=True):
            yield
    except GoogleAuthError as error:
        # _Request raises google-auth's TransportError from the httpx2 error, so a network failure or a token reply other than 200 is one level down (ADR-0009).
        cause: BaseException | None = error.__cause__
        if isinstance(cause, httpx2.TransportError):
            msg = f"the token request to Google failed: {cause}"
            raise TransportError(msg) from cause

        if isinstance(cause, httpx2.HTTPStatusError):
            raise status_error(cause.response, "Google") from cause

        msg = f"the credential could not get an access token: {error}"
        raise AuthenticationError(msg) from error


class _GoogleTokens:
    """The tokens of a `google-auth` credential."""

    def __init__(self, credentials: Credentials, request: _Request, /) -> None:
        self._credentials = credentials
        self._request = request

    def token(self) -> str:
        """Return the credential's token, refreshing it once it is within google-auth's expiry margin."""
        token: object = self._credentials.token
        # before_request would also start google-auth's background Regional Access Boundary lookup on this client.
        # google-auth keeps the token of a reply it fails to read, so a fresh one may not be usable.
        if self._credentials.token_state is TokenState.FRESH and usable(token):
            return token

        return self.refresh()

    def refresh(self) -> str:
        """Drop the credential's token and request a new one, because google-auth keeps the old token when a grant fails."""
        self._credentials.token = None
        replies: int = self._request.replies
        with _mapping():
            try:
                self._credentials.refresh(self._request)
            except REPLY_ERRORS as error:
                # With no new 200, these come from the caller's file rather than from google-auth reading a reply (ADR-0009).
                if self._request.replies == replies:
                    raise

                msg = f"Google's token reply could not be read: {error}"
                raise ProviderError(msg) from error
            except RefreshError as error:
                # After a 200, google-auth raises RefreshError only for a reply without an access token.
                if self._request.replies == replies:
                    raise

                msg = "Google's token reply holds no access token."
                raise ProviderError(msg) from error

        token: object = self._credentials.token
        if not usable(token):
            msg = "Google's token reply holds no access token."
            raise ProviderError(msg)

        return token


class _Request(Request):
    """A request adapter that sends `google-auth`'s token requests on the connection's client, so they share its timeout, proxy and CA (ADR-0009)."""

    def __init__(self, client: httpx2.Client, /) -> None:
        self._client = client
        self.replies = 0
        """How many `200` replies this adapter has returned to `google-auth`."""

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
        """Raise `google.auth.exceptions.TransportError` for any status but `200`, the one `google-auth` accepts, so it never retries a token request (ADR-0009).

        Ignore `timeout`, because the client's 60 seconds covers token requests too.
        """
        try:
            response = self._client.request(method, url, content=body, headers=headers)
        except httpx2.TransportError as error:
            raise GoogleTransportError(error) from error

        if response.status_code != HTTPStatus.OK:
            msg = f"Google replied {response.status_code} to a token request"
            status = httpx2.HTTPStatusError(
                msg, request=response.request, response=response
            )
            raise GoogleTransportError(status) from status

        self.replies += 1
        return _Response(response.status_code, response.headers, response.content)


class _Response(NamedTuple):
    """The status, headers and body of an `httpx2` response, under the names `google-auth` reads."""

    status: int
    headers: Mapping[str, str]
    data: bytes

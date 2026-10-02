"""`_msal` adapts `msal` to `Tokens`, and `_HttpClient` sends its token requests on the connection's client.

`_tokens` imports this module only for a Graph value, because it imports `msal` and `httpx2`. Each token call maps its own errors, because SMTP has no mail mapping around its token.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from typing import TYPE_CHECKING, Any, override

import httpx2
import msal

from epistole import _http
from epistole._tokens import CREDENTIAL_REJECTED, REPLY_ERRORS, oauth_error
from epistole.exceptions import AuthenticationError, ProviderError
from epistole.graph import Certificate, ClientSecret, ManagedIdentity

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

    from epistole._tokens import Tokens


def tokens(
    credential: ClientSecret | Certificate | ManagedIdentity,
    audience: str,
    client: httpx2.Client,
    /,
) -> Tokens:
    """Build the tokens for `credential`, in the spelling of `audience` its `msal` client takes (ADR-0011).

    The build runs inside `_mapping`, because `msal` fetches the tenant's OpenID configuration when it builds a confidential client.
    """
    cache = msal.TokenCache()
    http_client = _HttpClient(client)
    with _mapping():
        match credential:
            case ManagedIdentity(client_id=client_id):
                identity = (
                    msal.SystemAssignedManagedIdentity()
                    if client_id is None
                    else msal.UserAssignedManagedIdentity(client_id=client_id)
                )
                managed = msal.ManagedIdentityClient(
                    identity,
                    http_client=http_client,
                    token_cache=cache,
                    http_cache=_NoCache(),
                )
                return _MsalTokens(
                    partial(managed.acquire_token_for_client, resource=audience),
                    cache,
                    http_client,
                )
            case ClientSecret() | Certificate():
                app = msal.ConfidentialClientApplication(
                    credential.client_id,
                    client_credential=_client_credential(credential),
                    authority=f"https://login.microsoftonline.com/{credential.tenant_id}",
                    http_client=http_client,
                    token_cache=cache,
                    http_cache=_NoCache(),
                    # Otherwise msal fetches the host's aliases after a rejection, to find a refresh token a client credential never has.
                    instance_discovery=False,
                )
                return _MsalTokens(
                    partial(app.acquire_token_for_client, [f"{audience}/.default"]),
                    cache,
                    http_client,
                )


def _client_credential(
    credential: ClientSecret | Certificate,
) -> str | dict[str, object]:
    """Return `credential` in the `client_credential` shape `ConfidentialClientApplication` takes."""
    match credential:
        case ClientSecret(client_secret=secret):
            return secret
        case Certificate(pfx=None, private_key=key, thumbprint=thumbprint):
            return {"private_key": key, "thumbprint": thumbprint}
        case Certificate(pfx=pfx, passphrase=passphrase):
            return {"private_key_pfx_path": pfx, "passphrase": passphrase}


@contextmanager
def _mapping() -> Generator[None]:
    """Raise the Epistole error for a failed token request, by the Graph token rows in ADR-0009.

    A plain `httpx2.HTTPStatusError` passes, so `_graph` maps it by its mail table.
    """
    try:
        with _http.request_mapping("Microsoft"):
            yield
    except _TokenStatusError as error:
        raise _token_mapped(error.response) from error


def _token_mapped(response: httpx2.Response) -> ProviderError:
    """Return the `ProviderError` for a token reply `msal` never read, naming its status and its RFC 6749 error (ADR-0009)."""
    status: int = response.status_code
    error, description = oauth_error(response)
    label: str = f"{status} {error}" if error else str(status)
    msg = f"Microsoft replied {label} to a token request: {description}"
    return ProviderError(msg)


class _MsalTokens:
    """The tokens of an `msal` client, which caches them in `cache`."""

    def __init__(
        self,
        acquire: Callable[[], dict[str, Any]],
        cache: msal.TokenCache,
        http_client: _HttpClient,
        /,
    ) -> None:
        self._acquire = acquire
        self._cache = cache
        self._http_client = http_client

    def token(self) -> str:
        """Return the cached token, or a new one once the cached one is within five minutes of expiry."""
        replies: int = self._http_client.replies
        with _mapping():
            try:
                result: dict[str, Any] = self._acquire()
            except REPLY_ERRORS as error:
                # With no new reply, these come from the caller's key rather than from msal reading a reply (ADR-0009).
                if self._http_client.replies == replies:
                    raise

                msg = f"Microsoft's token reply could not be read: {error}"
                raise ProviderError(msg) from error

        if "access_token" not in result:
            # msal returns its error rather than raising it, so the error has no __cause__ (ADR-0009).
            msg = f"the credential could not get an access token: {result.get('error')}: {result.get('error_description')}"
            raise AuthenticationError(msg)

        return result["access_token"]

    def refresh(self) -> str:
        """Drop the cached tokens and return a new one, because `acquire_token_for_client` takes no `force_refresh`."""
        for entry in list(
            self._cache.search(msal.TokenCache.CredentialType.ACCESS_TOKEN)
        ):
            self._cache.remove_at(entry)

        return self.token()


class _HttpClient:
    """The `http_client` that `msal` takes.

    It sends `msal`'s token requests on the connection's client, so they share its timeout, proxy and CA (ADR-0009).
    """

    def __init__(self, client: httpx2.Client, /) -> None:
        self._client = client
        self.replies = 0
        """How many replies this adapter has returned to `msal`."""

    def get(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **_: object,
    ) -> httpx2.Response:
        """Ignore `timeout` and any other keyword, because the client's 60 seconds covers token requests too (ADR-0009)."""
        return self._to_msal(self._client.get(url, params=params, headers=headers))

    def post(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **_: object,
    ) -> httpx2.Response:
        """Ignore any other keyword, as `get` does."""
        return self._to_msal(
            self._client.post(url, params=params, data=data, headers=headers)
        )

    def _to_msal(self, response: httpx2.Response) -> httpx2.Response:
        """Count `response` and return it to `msal`, or raise `_TokenStatusError` for a status outside 2xx that does not reject the credential (ADR-0009)."""
        if not response.is_success and response.status_code not in CREDENTIAL_REJECTED:
            msg = f"Microsoft replied {response.status_code} to a token request"
            raise _TokenStatusError(msg, request=response.request, response=response)

        self.replies += 1
        return response


class _TokenStatusError(httpx2.HTTPStatusError):
    """`_HttpClient` raises this for a token reply, so `_mapping` maps it by the token table and never by the mail endpoint's (ADR-0009)."""


class _NoCache(dict[str, object]):
    """An `http_cache` for `msal` that keeps nothing, so `msal` sends every token request (ADR-0009)."""

    @override
    def __setitem__(self, key: str, value: object, /) -> None:
        pass

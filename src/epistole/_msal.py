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
from epistole._tokens import CREDENTIAL_REJECTED, REPLY_ERRORS, replied, status_error
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
    """Raise the Epistole error for a failed token request, by the Graph token rows in ADR-0009."""
    try:
        with _http.request_mapping("Microsoft", token=True):
            yield
    except httpx2.HTTPStatusError as error:
        # Only token requests run here, so a status error is always a token reply's (ADR-0009).
        raise status_error(error.response, "Microsoft") from error


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
        self._http_client.rejected = None
        with _mapping():
            try:
                result: dict[str, Any] = self._acquire()
            except REPLY_ERRORS as error:
                # With no new reply, these come from the caller's key rather than from msal reading a reply (ADR-0009).
                if self._http_client.replies == replies:
                    raise

                msg = f"Microsoft's token reply could not be read: {error}"
                raise ProviderError(msg) from error

        if "access_token" in result:
            return result["access_token"]

        # msal returns its error rather than raising it, so the error has no __cause__ (ADR-0009).
        rejected: httpx2.Response | None = self._http_client.rejected
        if rejected is not None:
            # msal reads App Service's and Azure ML's error bodies, which oauth_error cannot.
            msg = replied(
                "Microsoft",
                rejected.status_code,
                result.get("error") or "",
                result.get("error_description") or rejected.reason_phrase,
            )
            raise AuthenticationError(msg)

        if "error" not in result:
            msg = "Microsoft's token reply holds no access token."
            raise AuthenticationError(msg)

        msg = f"the credential could not get an access token: {result['error']}: {result.get('error_description')}"
        raise AuthenticationError(msg)

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
        self.rejected: httpx2.Response | None = None
        """The last reply this adapter returned to `msal`, if it was a `400`, `401` or `403`. `msal`'s error dict holds no status, so `_MsalTokens` reads it here."""

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
        """Count `response` and return it to `msal`, or raise `httpx2.HTTPStatusError` for a status outside 2xx that does not reject the credential (ADR-0009)."""
        # Azure Arc replies 401 to its first request, so each reply resets `rejected`.
        self.rejected = (
            response if response.status_code in CREDENTIAL_REJECTED else None
        )
        if not response.is_success and self.rejected is None:
            msg = f"Microsoft replied {response.status_code} to a token request"
            raise httpx2.HTTPStatusError(
                msg, request=response.request, response=response
            )

        self.replies += 1
        return response


class _NoCache(dict[str, object]):
    """An `http_cache` for `msal` that keeps nothing, so `msal` sends every token request (ADR-0009)."""

    @override
    def __setitem__(self, key: str, value: object, /) -> None:
        pass

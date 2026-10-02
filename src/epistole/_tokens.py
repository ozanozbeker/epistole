"""`_tokens` builds the tokens of every credential for a `Purpose` (ADR-0009, ADR-0011).

`_google_auth` and `_msal` hold the adapters: this module imports `_msal` only for a Graph value, and `_google_auth` only for a Gmail value. It imports no third-party library at module level, so `GmailBackend`, `GraphBackend` and an `SMTPBackend` with a `TokenCredential` import without any extra.
"""

from __future__ import annotations

import importlib
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from epistole._backend import TokenCredential

if TYPE_CHECKING:
    import httpx2

    from epistole import gmail, graph

type Purpose = Literal["gmail", "graph", "smtp"]

type Credential = (
    gmail.ServiceAccount
    | gmail.AuthorizedUser
    | graph.ClientSecret
    | graph.Certificate
    | graph.ManagedIdentity
    | TokenCredential
)

_SCOPES: dict[tuple[Literal["google", "microsoft"], Purpose], str] = {
    ("google", "gmail"): "https://www.googleapis.com/auth/gmail.send",
    ("google", "smtp"): "https://mail.google.com/",
    ("microsoft", "graph"): "https://graph.microsoft.com",
    ("microsoft", "smtp"): "https://outlook.office365.com",
}
"""The scope each issuer grants for each purpose (ADR-0011).

`gmail.send` grants no right to read or delete messages. Gmail's XOAUTH2 requires `https://mail.google.com/`, which grants both. A Microsoft row holds an audience. `_msal` requests it as a scope or as a resource by the credential's type, and `tokens` appends `/.default` for a `TokenCredential`.
"""

_EXTRAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "gmail": ("httpx2 and google-auth", ("google.auth", "httpx2")),
    "graph": ("httpx2 and msal", ("httpx2", "msal")),
}
"""The libraries each extra installs, by the names `pip` and `import` use."""

REPLY_ERRORS = (
    AttributeError,
    LookupError,
    OverflowError,
    RecursionError,
    TypeError,
    ValueError,
)
"""The classes `json`, `google-auth` and `msal` raise reading a reply they cannot parse, such as one that is not a JSON object or is nested too deeply (ADR-0009)."""

CREDENTIAL_REJECTED = frozenset(
    {HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}
)
"""The token reply statuses that reject the credential on both HTTP backends (ADR-0009). `_google_auth` maps each to `AuthenticationError`. `_msal`'s adapter returns each to `msal` for its error dict."""


class Tokens(Protocol):
    """The tokens a connection's requests carry, in the one shape `tokens` adapts every credential to.

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


def require(credential: Credential, purpose: Purpose, /) -> None:
    """Raise `ImportError` naming the extra `credential` needs for `purpose`, unless its libraries import."""
    from epistole import gmail, graph  # noqa: PLC0415

    match purpose, credential:
        case "gmail", _:
            extra, dependent = "gmail", "GmailBackend"
        case "graph", _:
            extra, dependent = "graph", "GraphBackend"
        case _, gmail.ServiceAccount() | gmail.AuthorizedUser():
            extra, dependent = (
                "gmail",
                f"OAuth over a gmail.{type(credential).__name__}",
            )
        case _, graph.ClientSecret() | graph.Certificate() | graph.ManagedIdentity():
            extra, dependent = (
                "graph",
                f"OAuth over a graph.{type(credential).__name__}",
            )
        case _:
            return

    libraries, modules = _EXTRAS[extra]
    try:
        for module in modules:
            importlib.import_module(module)
    except ImportError as error:
        msg = f"{dependent} needs {libraries}, so install the extra: pip install 'epistole[{extra}]'"
        raise ImportError(msg) from error


def tokens(
    credential: Credential, purpose: Purpose, client: httpx2.Client, /
) -> Tokens:
    """Build the tokens for `credential` on the connection's `client`, and request no token.

    The caller owns `client`, so this never opens or closes it.
    """
    from epistole import gmail, graph  # noqa: PLC0415

    # GmailBackend accepts a Graph value that has get_token as a TokenCredential, so the purpose decides first.
    match credential:
        case graph.ClientSecret() | graph.Certificate() | graph.ManagedIdentity() if (
            purpose != "gmail"
        ):
            from epistole import _msal  # noqa: PLC0415

            return _msal.tokens(credential, _SCOPES["microsoft", purpose], client)
        case TokenCredential() if purpose == "graph":
            return ForeignTokens(
                credential, f"{_SCOPES['microsoft', purpose]}/.default"
            )
        case gmail.ServiceAccount() | gmail.AuthorizedUser():
            from epistole import _google_auth  # noqa: PLC0415

            return _google_auth.tokens(credential, _SCOPES["google", purpose], client)
        case TokenCredential():
            return ForeignTokens(credential, _SCOPES["google", purpose])
        case _:
            msg = f"a {type(credential).__name__} gets no token for {purpose}."
            raise TypeError(msg)


def token(
    credential: Credential, purpose: Purpose, /, *, scope: str | None = None
) -> str:
    """Return one access token for `purpose`.

    `scope` is the scope a `TokenCredential`'s `get_token` receives on `"smtp"`, because Epistole cannot read its issuer. SMTP sends a token once in `AUTH`, so the client closes before this returns.
    """
    from epistole import _http, gmail, graph  # noqa: PLC0415

    issued = (
        gmail.ServiceAccount,
        gmail.AuthorizedUser,
        graph.ClientSecret,
        graph.Certificate,
        graph.ManagedIdentity,
    )
    if purpose == "smtp" and not isinstance(credential, issued):
        return credential.get_token(cast("str", scope)).token

    with _http.client() as client:
        return tokens(credential, purpose, client).token()


def oauth_error(response: httpx2.Response) -> tuple[str, str]:
    """Return the `error` and `error_description` of an RFC 6749 error reply."""
    try:
        body: dict[str, Any] = response.json()
        return str(body.get("error", "")), str(
            body.get("error_description", response.reason_phrase)
        )
    except REPLY_ERRORS:
        return "", response.reason_phrase

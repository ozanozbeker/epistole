"""`GraphBackend` sends through Microsoft Graph, and `ClientSecret`, `Certificate` and `ManagedIdentity` are the credentials it takes.

The module is public, because a caller imports a credential value from its backend's module (ADR-0011). `epistole._graph` holds the code that needs the extra, so `from epistole import GraphBackend` works without it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

from epistole._backend import Backend, TokenCredential

if TYPE_CHECKING:
    from pathlib import Path

    from epistole._backend import Transport

__all__ = ["Certificate", "ClientSecret", "GraphBackend", "ManagedIdentity"]


class GraphBackend(Backend):
    """A Graph backend sends each message through Microsoft Graph, as JSON.

    `connect()` builds one HTTP client and gets an access token. So a rejected credential raises `AuthenticationError` on that line. A tenant ID that does not exist in Entra raises `msal`'s `ValueError` there instead. It sends nothing to Graph, so an app without the `Mail.Send` permission raises on the first send instead. Every request times out after 60 seconds, and no setting changes it. See ADR-0005 and ADR-0009.

    Every request names the from address's mailbox as `/users/{addr-spec}`. No request uses `/me`, because an app-only token has no signed-in user. See ADR-0012.

    A Graph body holds HTML or plain text, not both. So an HTML message goes out without its plain text, and Exchange derives its own. See ADR-0012.

    A message whose `sendMail` request would be 4,000,000 bytes or more goes through a draft instead: Epistole creates the draft, adds each attachment by its own call, and sends it. That path needs the `Mail.ReadWrite` permission as well as `Mail.Send`. Without it, the send raises `AuthenticationError`. When a send fails partway, Epistole deletes the draft. See ADR-0012.

    Before writing, a send raises `RejectedError` for more than 500 recipients, for an attachment over 150,000,000 bytes, or for a custom header whose name does not start with `x-`. See ADR-0016 and ADR-0019.

    Graph accepts or refuses the whole message, so `SendResult.refused` is always empty.

    Parameters
    ----------
    credential
        Epistole calls a `TokenCredential`'s `get_token` with the scope `https://graph.microsoft.com/.default` before each request.

    Raises
    ------
    TypeError
        When `credential` is none of the four.
    ImportError
        When `epistole[graph]` is not installed.
    """

    def __init__(
        self,
        *,
        from_address: str,
        credential: ClientSecret | Certificate | ManagedIdentity | TokenCredential,
    ) -> None:
        super().__init__(from_address=from_address)
        if not isinstance(
            credential, (ClientSecret, Certificate, ManagedIdentity, TokenCredential)
        ):
            msg = f"credential= is a {type(credential).__name__}. Pass a graph.ClientSecret, a graph.Certificate, a graph.ManagedIdentity, or an object with get_token()."
            raise TypeError(msg)

        # A job without the extra fails at construction rather than on its first send (ADR-0009).
        try:
            import httpx2  # noqa: F401, PLC0415
            import msal  # noqa: F401, PLC0415
        except ImportError as error:
            msg = "GraphBackend needs httpx2 and msal, so install the extra: pip install 'epistole[graph]'"
            raise ImportError(msg) from error

        self._credential = credential

    @override
    def _open(self) -> Transport:
        from epistole._graph import connect  # noqa: PLC0415

        return connect(self._credential)


@dataclass(frozen=True)
class ClientSecret:
    """A client secret authenticates an Entra app registration, which needs the `Mail.Send` application permission.

    Epistole requests the scope `https://graph.microsoft.com/.default`, which grants the permissions an administrator consented to for the app. See ADR-0011.

    Attributes
    ----------
    tenant_id
        The directory the app is registered in, as a GUID or a domain.
    client_id
        The app's application ID.
    client_secret
        The secret. It is not in the `repr`, so no traceback or log line holds it.
    """

    tenant_id: str
    client_id: str
    client_secret: str = field(repr=False)


@dataclass(frozen=True)
class Certificate:
    """A certificate authenticates an Entra app registration with a certificate instead of a secret.

    It takes one of the two forms `msal` accepts: `pfx` with an optional `passphrase`, or `private_key` and `thumbprint` together. Any other combination raises `TypeError`. Prefer `pfx`, because `msal` deprecates the second form for its SHA-1 thumbprint. See ADR-0011.

    Attributes
    ----------
    tenant_id
        The directory the app is registered in, as a GUID or a domain.
    client_id
        The app's application ID.
    pfx
        A PKCS #12 file that holds the private key and the certificate. `connect()` reads it.
    passphrase
        The passphrase of an encrypted `pfx`. It is not in the `repr`.
    private_key
        The private key, in unencrypted PEM. It is not in the `repr`.
    thumbprint
        The certificate's SHA-1 thumbprint, in hex.
    """

    tenant_id: str
    client_id: str
    pfx: Path | None = None
    passphrase: str | None = field(default=None, repr=False)
    private_key: str | None = field(default=None, repr=False)
    thumbprint: str | None = None

    def __post_init__(self) -> None:
        """Raise `TypeError` unless the fields hold exactly one complete form (ADR-0011)."""
        key_form: tuple[str | None, str | None] = (self.private_key, self.thumbprint)
        complete: bool = (
            key_form == (None, None)
            if self.pfx is not None
            else None not in key_form and self.passphrase is None
        )
        if not complete:
            msg = "Certificate takes pfx= with an optional passphrase=, or private_key= and thumbprint= together, and nothing else."
            raise TypeError(msg)


@dataclass(frozen=True)
class ManagedIdentity:
    """A managed identity is the identity Azure gives the resource the code runs on, so the caller stores no secret.

    Epistole requests the resource `https://graph.microsoft.com`, because `msal`'s managed identity client takes a resource and no scope. It does not work on Service Fabric, where `msal` requires its own `requests.Session` to pin the endpoint's certificate. See ADR-0011.

    Attributes
    ----------
    client_id
        The client ID of a user-assigned identity, or `None` for the system-assigned one.
    """

    client_id: str | None = None

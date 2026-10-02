"""`GmailBackend` sends through the Gmail API, and `ServiceAccount` and `AuthorizedUser` are the credentials it takes.

The module is public, because a caller imports a credential value from its backend's module (ADR-0011). `epistole._gmail` and `epistole._google_auth` hold the code that needs the extra, so `from epistole import GmailBackend` works without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from epistole import _tokens
from epistole._backend import Backend, TokenCredential

if TYPE_CHECKING:
    from pathlib import Path

    from epistole._backend import Transport

__all__ = ["AuthorizedUser", "GmailBackend", "ServiceAccount"]


class GmailBackend(Backend):
    """A Gmail backend sends each message through the Gmail API's `messages.send`, as the RFC 5322 message SMTP would write.

    `connect()` reads the credential's file, builds one HTTP client, and gets an access token. So a rejected credential raises `AuthenticationError` on that line. A token request makes one attempt, and a failure on Google's side raises `ProviderError` there. It sends nothing to the Gmail API, so a token without the scope raises on the first send instead. Every request times out after 60 seconds, and no setting changes it. See ADR-0005 and ADR-0009.

    Epistole requests the scope `https://www.googleapis.com/auth/gmail.send` alone, which grants no right to read or delete messages. See ADR-0011.

    Before writing, a send raises `RejectedError` for more than 500 recipients, or for a message over 36,700,160 bytes once encoded. Both limits are Google's. See ADR-0019.

    Gmail accepts or refuses the whole message, so `SendResult.refused` is always empty.

    Gmail replaces the `Message-ID` Epistole sets with its own. When `from_address` is neither the account nor one of its verified aliases, Gmail sends from the account's own address and raises nothing. `docs/research/live-send-findings.md` records both.

    Parameters
    ----------
    credential
        Epistole calls a `TokenCredential`'s `get_token` with the `gmail.send` scope before each request.

    Raises
    ------
    TypeError
        When `credential` is none of the three.
    ImportError
        When `epistole[gmail]` is not installed.
    """

    def __init__(
        self,
        *,
        from_address: str,
        credential: ServiceAccount | AuthorizedUser | TokenCredential,
    ) -> None:
        super().__init__(from_address=from_address)
        if not isinstance(
            credential, (ServiceAccount, AuthorizedUser, TokenCredential)
        ):
            msg = f"credential= is a {type(credential).__name__}. Pass a gmail.ServiceAccount, a gmail.AuthorizedUser, or an object with get_token()."
            raise TypeError(msg)

        # A job without the extra fails at construction rather than on its first send (ADR-0009).
        _tokens.require(credential, "gmail")
        self._credential = credential

    @override
    def _open(self) -> Transport:
        from epistole._gmail import _GmailTransport  # noqa: PLC0415

        return _GmailTransport.connect(self._credential)


@dataclass(frozen=True)
class ServiceAccount:
    """A service account sends as `subject` through domain-wide delegation.

    A Workspace administrator grants the service account's client ID the `https://www.googleapis.com/auth/gmail.send` scope. Inside `smtp.OAuth`, it requests `https://mail.google.com/` instead, so the administrator grants that.

    Attributes
    ----------
    path
        The service account's JSON key file. `connect()` reads it.
    subject
        The mailbox the service account acts as.
    """

    path: Path
    subject: str


@dataclass(frozen=True)
class AuthorizedUser:
    """An authorized user is a saved user consent.

    Epistole runs no consent flow and never rewrites the file. `connect()` ignores any access token the file holds and always requests one. So a refresh token that Google has expired or revoked raises `AuthenticationError` on `connect()`.

    Inside `smtp.OAuth`, it requests `https://mail.google.com/`, so the consent must include that scope.

    Attributes
    ----------
    path
        The JSON file that holds the refresh token, as `google.oauth2.credentials.Credentials.to_json()` writes it. `connect()` reads it.
    """

    path: Path

"""`SMTPBackend` submits through `smtplib`, and `Password` and `OAuth` are the credentials it takes.

The module is public, because a caller imports a credential value from its backend's module (ADR-0011).
"""

from __future__ import annotations

import ssl
from contextlib import ExitStack
from dataclasses import dataclass, field
from smtplib import (
    SMTP,
    SMTP_SSL,
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPException,
    SMTPHeloError,
    SMTPNotSupportedError,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPSenderRefused,
    SMTPServerDisconnected,
)
from typing import TYPE_CHECKING, Literal, cast, override

from epistole import gmail, graph
from epistole._address import addr_spec
from epistole._backend import Backend, TokenCredential
from epistole._result import Refusal
from epistole._rfc5322 import build
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RejectedError,
    SenderRefusedError,
    TransportError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from email.message import EmailMessage
    from email.policy import EmailPolicy

    from epistole._backend import Submission, Transport

__all__ = ["OAuth", "Password", "SMTPBackend"]

_GRAPH_VALUES = (graph.ClientSecret, graph.Certificate, graph.ManagedIdentity)
_GMAIL_VALUES = (gmail.ServiceAccount, gmail.AuthorizedUser)

_TIMEOUT = 60
"""Seconds each socket operation may take. No setting changes it (ADR-0017)."""

_CLOSING = 421
"""RFC 5321: the server closes its socket after this reply."""

_TOO_BIG = 552
"""RFC 5321: the server sends this for a message over a storage limit, such as the SIZE it advertised."""

_PERMANENT = 5
"""RFC 5321: a reply code that starts with this digit is a permanent failure."""

_OUTLOOK_AUDIENCE = "https://outlook.office365.com"
"""Exchange Online's audience for SMTP AUTH, which `_graph.token` requests as a resource or as a scope by the credential's type (ADR-0011)."""

_GMAIL_SCOPE = "https://mail.google.com/"
"""Gmail requires it for XOAUTH2, though it also grants reading and deleting every message (ADR-0011)."""


class SMTPBackend(Backend):
    """An SMTP backend submits each message to an SMTP server through `smtplib`.

    `connect()` opens the socket, starts TLS unless `security` is `"none"`, and authenticates. So a wrong password or a rejected token raises `AuthenticationError` on that line. Every socket operation times out after 60 seconds, and no setting changes it. See ADR-0005 and ADR-0017.

    A server may refuse some recipients and accept the rest. The send then returns normally with the refusals in `SendResult.refused`, so a caller who ignores the send result loses them. See ADR-0004.

    There is no size pre-check. `smtplib` sends the message size to a server that advertises `SIZE`, and the server's `552` raises `RejectedError`. See ADR-0019.

    Parameters
    ----------
    host
        The server's host name. TLS checks the server's certificate against it.
    port
        Pass 465 with `security="tls"`, because 587 is the STARTTLS port.
    security
        `"starttls"` upgrades after EHLO and raises `TransportError` when the server does not offer it. `"tls"` starts TLS on connect. `"none"` sends in plaintext, a password included. There is no opportunistic mode, and nothing infers the mode from the port.
    credential
        `None` submits anonymously. A `Password` logs in, and an `OAuth` authenticates with an access token through XOAUTH2.

    Raises
    ------
    TypeError
        When `credential` is none of `Password`, `OAuth` and `None`.
    ImportError
        When an `OAuth` holds a Graph or Gmail value, and that backend's extra is not installed.
    ValueError
        When `security` is not one of the three modes.
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = 587,
        security: Literal["starttls", "tls", "none"] = "starttls",
        from_address: str,
        credential: Password | OAuth | None = None,
    ) -> None:
        super().__init__(from_address=from_address)
        # A typo would otherwise fall through to plaintext and send the password in the clear.
        if security not in {"starttls", "tls", "none"}:
            msg = f"security={security!r} is not one of 'starttls', 'tls' or 'none'."
            raise ValueError(msg)

        if credential is not None and not isinstance(credential, (Password, OAuth)):
            msg = f"credential= is a {type(credential).__name__}. Pass an smtp.Password, an smtp.OAuth, or None to submit anonymously."
            raise TypeError(msg)

        # A job without the extra fails at construction rather than on its first send (ADR-0009).
        if isinstance(credential, OAuth):
            wrapped: object = credential.credential
            if isinstance(wrapped, _GRAPH_VALUES):
                graph._check_extra(f"OAuth over a graph.{type(wrapped).__name__}")  # noqa: SLF001
            elif isinstance(wrapped, _GMAIL_VALUES):
                gmail._check_extra(f"OAuth over a gmail.{type(wrapped).__name__}")  # noqa: SLF001

        self._host = host
        self._port = port
        self._security = security
        self._credential = credential

    @override
    def _open(self) -> Transport:
        # Outside the mapping below, so a missing key file stays a FileNotFoundError.
        xoauth2: str | None = (
            _xoauth2(self._credential) if isinstance(self._credential, OAuth) else None
        )
        try:
            return _SMTPTransport(self._connect(xoauth2))
        except (SMTPException, OSError) as error:
            raise _mapped(error, sending=False) from error

    def _connect(self, xoauth2: str | None) -> SMTP:
        """Open the socket, start TLS unless `security` is `"none"`, and authenticate."""
        # smtplib's own default context checks no certificate.
        context: ssl.SSLContext = ssl.create_default_context()
        smtp: SMTP = (
            SMTP_SSL(self._host, self._port, timeout=_TIMEOUT, context=context)
            if self._security == "tls"
            else SMTP(self._host, self._port, timeout=_TIMEOUT)
        )
        with ExitStack() as on_failure:
            on_failure.callback(smtp.close)
            smtp.ehlo_or_helo_if_needed()
            if self._security == "starttls":
                if not smtp.has_extn("starttls"):
                    msg = f"{self._host} does not offer STARTTLS. Pass security='tls' if it starts TLS on connect, or security='none' to send in plaintext."
                    raise TransportError(msg)

                smtp.starttls(context=context)
                smtp.ehlo_or_helo_if_needed()

            if isinstance(self._credential, Password):
                smtp.login(self._credential.username, self._credential.password)
            elif xoauth2 is not None:
                # smtplib's auth returns normally on a 503 reply, which a server without AUTH sends.
                if "XOAUTH2" not in smtp.esmtp_features.get("auth", "").split():
                    msg = f"{self._host} does not offer AUTH XOAUTH2 with security={self._security!r}, so an OAuth credential cannot authenticate there."
                    raise AuthenticationError(msg)

                # Gmail sends a 334 challenge for a rejected token, then 535 after an empty response.
                smtp.auth(
                    "XOAUTH2",
                    lambda challenge=None: xoauth2 if challenge is None else "",
                )

            on_failure.pop_all()

        return smtp


@dataclass(frozen=True)
class Password:
    """A password is the username and password `SMTPBackend` logs in with, through `smtplib.SMTP.login`.

    `smtplib` encodes both as ASCII, so `connect()` raises `UnicodeEncodeError` for any other character.

    Attributes
    ----------
    username
        The name the server authenticates, often the from address.
    password
        The secret. It is not in the `repr`, so no traceback or log line holds it.
    """

    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class OAuth:
    """An OAuth credential authenticates to SMTP with an access token instead of a password, through XOAUTH2.

    `connect()` gets one token from `credential`, and sends it with `username` through `smtplib.SMTP.auth`. It sends no token to a server that does not offer `AUTH XOAUTH2`, and raises `AuthenticationError` instead.

    Epistole derives the scope from the issuer. A `graph.ClientSecret` or `graph.Certificate` requests `https://outlook.office365.com/.default`. A `graph.ManagedIdentity` requests the resource `https://outlook.office365.com` instead, because `msal`'s managed identity client takes no scope. A Gmail value requests `https://mail.google.com/`, which Gmail requires though it also grants reading and deleting every message. Epistole cannot read the issuer of a `TokenCredential`, so it takes `scope` instead. See ADR-0011.

    Attributes
    ----------
    username
        The mailbox the token belongs to, sent as XOAUTH2's `user`. `smtplib` encodes it as ASCII, so `connect()` raises `UnicodeEncodeError` for any other character.
    credential
        A value from `epistole.graph` or `epistole.gmail`, or a `TokenCredential`.
    scope
        The scope a `TokenCredential`'s `get_token` receives. It is required with a `TokenCredential`, and `OAuth` raises `TypeError` for it with any other credential.
    """

    username: str
    credential: (
        graph.ClientSecret
        | graph.Certificate
        | graph.ManagedIdentity
        | gmail.ServiceAccount
        | gmail.AuthorizedUser
        | TokenCredential
    )
    scope: str | None = None

    def __post_init__(self) -> None:
        """Raise `TypeError` for a credential of another type, for a `TokenCredential` without `scope`, or for any other credential with it (ADR-0011)."""
        issued: bool = isinstance(self.credential, (*_GRAPH_VALUES, *_GMAIL_VALUES))
        name: str = type(self.credential).__name__
        if not issued and not isinstance(self.credential, TokenCredential):
            msg = f"credential= is a {name}. Pass a value from epistole.graph or epistole.gmail, or an object with get_token()."
            raise TypeError(msg)

        if issued and self.scope is not None:
            msg = f"OAuth derives the scope from the issuer of a {name}, so it takes no scope=."
            raise TypeError(msg)

        if not issued and self.scope is None:
            msg = "An object with get_token() needs scope=, because OAuth cannot read its issuer."
            raise TypeError(msg)


def _xoauth2(oauth: OAuth) -> str:
    """Return the XOAUTH2 initial response, with a token from `oauth.credential`."""
    credential = oauth.credential
    if isinstance(credential, _GRAPH_VALUES):
        from epistole import _graph  # noqa: PLC0415

        token: str = _graph.token(credential, _OUTLOOK_AUDIENCE)
    elif isinstance(credential, _GMAIL_VALUES):
        from epistole import _gmail  # noqa: PLC0415

        token = _gmail.token(credential, _GMAIL_SCOPE)
    else:
        token = credential.get_token(cast("str", oauth.scope)).token

    return f"user={oauth.username}\x01auth=Bearer {token}\x01\x01"


class _SMTPTransport:
    """`SMTPBackend` opens this transport, which holds one `smtplib.SMTP`."""

    def __init__(self, smtp: SMTP, /) -> None:
        self._smtp = smtp

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Write the RFC 5322 message to the server, and return the refusals keyed by addr-spec."""
        mime: EmailMessage = build(submission)
        mail_from: str = addr_spec(submission.from_address)
        # smtplib counts the refusals against this list's length, so each addr-spec appears once.
        rcpt_to: list[str] = list(
            dict.fromkeys(addr_spec(one) for one in submission.message.recipients)
        )
        options: tuple[str, ...] = ()
        if cast("EmailPolicy", mime.policy).utf8 and all(
            one.isascii() for one in (mail_from, *rcpt_to)
        ):
            # send_message adds SMTPUTF8 for a non-ASCII envelope alone, and sendmail drops every option after HELO (ADR-0014).
            if not self._smtp.has_extn("smtputf8"):
                msg = "Reply-To holds a non-ASCII address, which requires SMTPUTF8. The server does not advertise SMTPUTF8."
                raise RejectedError(msg)

            options = ("SMTPUTF8", "BODY=8BITMIME")

        try:
            refused: dict[str, tuple[int, bytes]] = self._smtp.send_message(
                mime, mail_from, rcpt_to, mail_options=options
            )
        except SMTPRecipientsRefused as error:
            if any(code == _CLOSING for code, _ in error.recipients.values()):
                raise _mapped(error, sending=True) from error

            # smtplib raises when every recipient was refused, which Connection.send reports instead (ADR-0015).
            refused = error.recipients
        except (SMTPException, OSError) as error:
            raise _mapped(error, sending=True) from error

        return {
            spec: Refusal(code, _text(reason))
            for spec, (code, reason) in refused.items()
        }

    def close(self) -> None:
        """Send `QUIT`, and close the socket even when that fails."""
        try:
            self._smtp.quit()
        finally:
            self._smtp.close()


def _mapped(error: OSError, /, *, sending: bool) -> EpistoleError:
    """Return the Epistole error for a native `smtplib` failure, by the SMTP mapping in ADR-0004.

    `sending` is whether `send_message` raised it rather than a step of `connect()`, because `SMTPNotSupportedError` and a bare `SMTPException` map to a different class in each.
    """
    code: int = getattr(error, "smtp_code", 0)
    reply: bytes | str = getattr(error, "smtp_error", str(error))
    if isinstance(error, SMTPRecipientsRefused):
        # submit passes only a refusal that holds a 421, and smtplib raises straight after that reply.
        code, reply = [*error.recipients.values()][-1]

    msg: str = f"the server replied {code} {_text(reply)}" if code else _text(reply)
    kind: type[EpistoleError]
    if code == _CLOSING:
        # smtplib closes the socket after a 421 reply to any command.
        kind = TransportError
    elif isinstance(error, SMTPSenderRefused):
        # The server sends 552 for a message over its advertised SIZE, and the from address is not at fault.
        kind = RejectedError if code == _TOO_BIG else SenderRefusedError
    elif isinstance(error, SMTPAuthenticationError):
        kind = AuthenticationError
    elif isinstance(error, SMTPNotSupportedError):
        # send_message raises it for a missing SMTPUTF8, and login for a missing AUTH.
        kind = RejectedError if sending else AuthenticationError
    elif isinstance(
        error, (SMTPConnectError, SMTPHeloError, SMTPServerDisconnected)
    ) or not isinstance(error, SMTPException):
        kind = TransportError
    elif isinstance(error, SMTPResponseException):
        kind = RejectedError if code // 100 == _PERMANENT else ProviderError
    else:
        # login raises a bare SMTPException when smtplib supports none of the server's mechanisms, and no retry fixes that.
        kind = ProviderError if sending else AuthenticationError

    return kind(msg)


def _text(reply: bytes | str) -> str:
    """Decode a server reply as UTF-8, replacing each byte that does not decode (ADR-0004)."""
    return (
        reply.decode("utf-8", errors="replace") if isinstance(reply, bytes) else reply
    )

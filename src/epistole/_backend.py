"""The send path: a backend opens a connection, which stamps a submission and hands it to a transport."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass
from email.utils import localtime, make_msgid
from typing import TYPE_CHECKING, Protocol, Self

from epistole._address import addr_spec, check_address
from epistole._result import SendResult
from epistole.exceptions import EpistoleError, RecipientsRefusedError, TransportError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from epistole._message import Message
    from epistole._result import Refusal


class Backend(ABC):
    """One configured route to a mail service.

    A backend is immutable configuration: the credentials, the from address, and every setting only its mail service understands. It holds no live link, so it is safe to share across threads and it is not a context manager. `with backend:` is a `TypeError`, and `backend.connect()` is the one way to get a link.

    A subclass implements `_open()` and nothing else. Nothing else will ever become abstract, because adding an abstract method later breaks every backend already written against this one.

    Parameters
    ----------
    from_address
        Checked here, so a malformed address fails at construction rather than at the first send.

    Attributes
    ----------
    from_address
        The mailbox every submission goes out under. There is no per-send override, and the mail service decides whether this backend may use it.
    """

    from_address: str

    def __init__(self, *, from_address: str) -> None:
        check_address(from_address)
        self.from_address = from_address

    def send(self, message: Message, /) -> SendResult:
        """Send one message over a connection opened and closed for it.

        This is the one-shot. A loop over many messages opens one connection with `connect()` instead.

        Returns
        -------
        The send result the connection built.
        """
        with self.connect() as connection:
            return connection.send(message)

    def connect(self) -> Connection:
        """Open one live link and hand back the connection holding it.

        Opening is eager: socket, TLS, and AUTH on SMTP; a client and a token on the HTTP backends; nothing on the doubles. `AuthenticationError` and `TransportError` therefore surface on this line rather than on the first send.

        Use it in a `with`. A connection left unclosed holds its link until the service times it out.

        Returns
        -------
        A fresh connection, which carries as many sends as the caller makes before it closes.

        Examples
        --------
        ```python
        backend = MemoryBackend()
        with backend.connect() as connection:
            connection.send(Message(text="Weekly numbers").to("ada@example.com"))

        len(backend.submissions)  # 1
        ```
        """
        try:
            transport: Transport = self._open()
        except EpistoleError as error:
            error.backend = self
            raise

        return Connection(self, transport)

    @abstractmethod
    def _open(self) -> Transport:
        """Open the wire object this backend speaks through.

        Returns
        -------
        A live transport.
        """


class Connection:
    """One live link a backend opened, carrying many sends and then closing for good.

    A connection belongs to one thread and one `with`. It cannot be reopened: `send` or re-entry after `close()` raises `ValueError`, because a loop that kept a connection past its `with` is a bug in the calling code and a silent reconnect would hide it. Reopening means calling `connect()` again.

    It does the work every send needs before the wire, which is what leaves a third-party backend writing a `Transport` alone: it checks the message, stamps the `Message-ID` and the `Date`, and builds the send result from what the transport answered.

    `Backend.connect()` builds one and nothing else does.

    Parameters
    ----------
    backend
        The backend that opened this connection. It names the route on every error that leaves `send`.
    transport
        The wire object to submit through. The connection owns it and closes it.

    Attributes
    ----------
    backend
        The route this connection runs on.
    """

    backend: Backend

    def __init__(self, backend: Backend, transport: Transport, /) -> None:
        self.backend = backend
        self._transport = transport
        self._closed = False

    def send(self, message: Message, /) -> SendResult:
        """Check `message`, submit it, and build the send result.

        In order: refuse a closed connection, check the message is complete, stamp a `Submission`, hand it to the transport, re-key the refusals that came back, and raise if every recipient was refused.

        Returns
        -------
        The record that the service accepted the submission, carrying the stamps and any refusals.

        Raises
        ------
        ValueError
            When the connection is closed, or when the message names no recipient. Both are mistakes in the calling code, found before the wire.
        RecipientsRefusedError
            When the service refused every recipient, so nothing was submitted.
        EpistoleError
            Whatever the transport mapped the service's answer onto, carrying this connection's backend.
        """
        if self._closed:
            msg = "this connection is closed; open another with backend.connect()"
            raise ValueError(msg)

        if not message.recipients:
            msg = "the message names no recipient; address it with .to(), .cc(), or .bcc()"
            raise ValueError(msg)

        submission = Submission(
            message=message,
            from_address=self.backend.from_address,
            message_id=make_msgid(domain=_domain(self.backend.from_address)),
            date=localtime(),
        )

        try:
            refusals: Mapping[str, Refusal] = self._transport.submit(submission)
        except TransportError as error:
            error.backend = self.backend
            self.close()
            raise
        except EpistoleError as error:
            error.backend = self.backend
            raise

        refused: dict[str, Refusal] = {}
        if refusals:
            specs: tuple[str, ...] = tuple(addr_spec(one) for one in message.recipients)
            refused = _rekey(refusals, message.recipients, specs)
            if all(spec in refusals for spec in specs):
                msg = f"every recipient was refused, so nothing was submitted: {', '.join(refused)}"
                raise RecipientsRefusedError(msg, refused=refused, backend=self.backend)

        return SendResult(
            message_id=submission.message_id,
            date=submission.date,
            refused=refused,
        )

    def close(self) -> None:
        """Close the link for good.

        Idempotent, and it never raises. An SMTP `QUIT` on a dead socket is swallowed, so an error from a `with` body is not masked by the exit.
        """
        if self._closed:
            return

        self._closed = True
        with suppress(Exception):
            self._transport.close()

    def __enter__(self) -> Self:
        """Hand back this connection, unless it is closed.

        Returns
        -------
        The receiver. Entering does nothing else, because `connect()` already opened the link.

        Raises
        ------
        ValueError
            When the connection is closed.
        """
        if self._closed:
            msg = "this connection is closed; open another with backend.connect()"
            raise ValueError(msg)

        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the connection, suppressing nothing."""
        self.close()


class Transport(Protocol):
    """The wire object a backend opens: the only code that speaks to a mail service.

    It is the whole of what a third-party backend writes. Both methods take their arguments positionally, so a transport spelling one `submit(self, sub)` still matches.
    """

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Hand `submission` to the mail service.

        Answer with the refusals the service gave, keyed by addr-spec, and empty when it refused none. Never raise `RecipientsRefusedError` and never build a `SendResult`: `Connection.send` does both, so every backend answers a caller the same way.

        Map a native failure onto one `EpistoleError` subclass and raise it with `from`, leaving `backend` unset. A submission is all a transport receives, so it has no backend to name.

        Refuse a message this transport cannot carry before writing anything, with `RejectedError` and no `__cause__`.

        Returns
        -------
        Each refused recipient's refusal, keyed by addr-spec.
        """
        ...

    def close(self) -> None:
        """Close the link. `Connection.close` swallows whatever this raises."""
        ...


@dataclass(frozen=True)
class Submission:
    """One message handed to one transport once.

    `Connection.send` builds it and nothing else does. Sending the same message twice makes two submissions with two ids, because identity belongs to the send and never to the message.

    Attributes
    ----------
    message
        Exactly what the caller built. Nothing is stamped onto it.
    from_address
        The backend's from address, which a `Message` never carries.
    message_id
        `email.utils.make_msgid(domain=...)`, angle brackets kept, so the value reads the same in a log, in the header, and in Graph's `internetMessageId`.
    date
        `email.utils.localtime()`: timezone-aware, carrying the sending machine's offset.
    """

    message: Message
    from_address: str
    message_id: str
    date: datetime


def _domain(from_address: str) -> str:
    """Return the domain a `Message-ID` is stamped under, in ASCII.

    It comes from the backend's from address, never from bare `make_msgid()`, whose default resolves through `socket.getfqdn()` and would put the sending machine's internal hostname in every message a scheduled job sends.

    A non-ASCII domain is IDNA-encoded, because RFC 5322 wants a `msg-id` in ASCII and `EmailMessage.as_bytes()` raises `UnicodeEncodeError` on anything else. Nothing resolves this domain: a `Message-ID` is an identifier, not a route, so the encoding only has to be stable and legal. That also makes the stdlib codec's IDNA 2003 folding harmless here, where `straße.de` becomes `strasse.de` rather than IDNA 2008's `xn--strae-oqa.de`.

    Returns
    -------
    Everything after the last `@` of the from address's addr-spec, IDNA-encoded when it is not already ASCII.

    Raises
    ------
    ValueError
        When the codec refuses the domain, which takes a non-ASCII label over 63 characters or an empty one.
    """
    domain: str = addr_spec(from_address).rpartition("@")[2]
    if domain.isascii():
        return domain

    try:
        return domain.encode("idna").decode("ascii")
    except UnicodeError as error:
        msg = f"{from_address!r} has a domain that cannot be written into a Message-ID: {error}"
        raise ValueError(msg) from error


def _rekey(
    refusals: Mapping[str, Refusal],
    recipients: tuple[str, ...],
    specs: tuple[str, ...],
) -> dict[str, Refusal]:
    """Key `refusals` by the caller's recipient string rather than by addr-spec.

    A service names a mailbox, so a transport answers with addr-spec keys and a display name the caller wrote is lost. Re-keying here makes `SendResult.refused` compare directly against what the caller passed to `.to()`.

    Two recipients sharing an addr-spec resolve to the first in `recipients` order, so one refusal makes one entry.

    Parameters
    ----------
    specs
        The addr-spec of each recipient, in order. The caller reads them again to decide whether every recipient was refused, so they are parsed once and passed in.

    Returns
    -------
    One entry per refused addr-spec, under the recipient string that carried it.
    """
    refused: dict[str, Refusal] = {}
    taken: set[str] = set()
    for recipient, spec in zip(recipients, specs, strict=True):
        refusal: Refusal | None = refusals.get(spec)
        if refusal is not None and spec not in taken:
            taken.add(spec)
            refused[recipient] = refusal

    return refused

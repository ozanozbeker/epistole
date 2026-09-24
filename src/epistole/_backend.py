"""A backend opens a connection, which builds each submission and passes it to a transport."""

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
    """A backend holds the configuration for sending through one mail service.

    It holds immutable configuration and no live link, so threads can share it. It is not a context manager: `connect()` opens a link. A subclass implements `_open()` and nothing else. See ADR-0005 and ADR-0006.

    Attributes
    ----------
    from_address
        The mailbox every submission is sent from, checked at construction. No send can override it. See ADR-0001.
    """

    from_address: str

    def __init__(self, *, from_address: str) -> None:
        check_address(from_address)
        self.from_address = from_address

    def send(self, message: Message, /) -> SendResult:
        """Send one message over a connection opened and closed for it.

        To send many messages, open one connection with `connect()` instead. When the service refuses some recipients and accepts the rest, the send raises nothing and `SendResult.refused` holds the refusals.
        """
        with self.connect() as connection:
            return connection.send(message)

    def connect(self) -> Connection:
        """Open one live link and return the connection that holds it.

        Opening is eager, so this call, not the first send, raises `AuthenticationError` and `TransportError`. See ADR-0005.

        Use it in a `with`. A connection left unclosed holds its link until the service times it out.

        Examples
        --------
        ```python
        from epistole import MemoryBackend, Message

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
        """Open the transport this backend sends through."""


class Connection:
    """A connection is one live link a backend opened, for many sends until it closes for good.

    Build one with `Backend.connect()`. It belongs to one thread and one `with`, and never reopens. It checks each message and builds the submission and the send result, so a third-party backend writes only a `Transport`. See ADR-0005.

    Attributes
    ----------
    backend
        The backend that opened this connection.
    """

    backend: Backend

    def __init__(self, backend: Backend, transport: Transport, /) -> None:
        self.backend = backend
        self._transport = transport
        self._closed = False

    def send(self, message: Message, /) -> SendResult:
        """Check `message`, submit it, and build the send result.

        When the service refuses some recipients and accepts the rest, the send raises nothing and `SendResult.refused` holds the refusals.

        Raises
        ------
        ValueError
            When the connection is closed, or when the message names no recipient.
        RecipientsRefusedError
            When the service refused every recipient.
        EpistoleError
            The error the transport raised, with `backend` set.
        """
        if self._closed:
            msg = "this connection is closed. Open another with backend.connect()."
            raise ValueError(msg)

        if not message.recipients:
            msg = "the message names no recipient. Address it with .to(), .cc(), or .bcc()."
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

        It is idempotent and never raises, so `__exit__` never replaces an error from the `with` body. See ADR-0005.
        """
        if self._closed:
            return

        self._closed = True
        with suppress(Exception):
            self._transport.close()

    def __enter__(self) -> Self:
        """Return this connection, which `connect()` already opened.

        Raises
        ------
        ValueError
            When the connection is closed.
        """
        if self._closed:
            msg = "this connection is closed. Open another with backend.connect()."
            raise ValueError(msg)

        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the connection, suppressing nothing."""
        self.close()


class Transport(Protocol):
    """A transport is the object a backend opens, and the only code that communicates with a mail service.

    A third-party backend writes a transport and nothing else. Both methods take positional-only arguments, so `submit(self, sub)` still matches.
    """

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Submit `submission` to the mail service.

        Map a native failure onto one `EpistoleError` subclass, and raise it with `from` and with `backend` unset. Before writing anything, raise `RejectedError` with no `__cause__` for a message this transport cannot carry. Never raise `RecipientsRefusedError` or build a `SendResult`, because `Connection.send` does both. See ADR-0004 and ADR-0015.

        Returns
        -------
        Each refused recipient's refusal, keyed by addr-spec. It is empty when the service refused none.
        """
        ...

    def close(self) -> None:
        """Close the link. `Connection.close` suppresses any error this raises."""
        ...


@dataclass(frozen=True)
class Submission:
    """A submission is one message passed to one transport once.

    Only `Connection.send` builds one. Sending a message twice makes two submissions with two ids, because identity belongs to the send. See ADR-0015.

    Attributes
    ----------
    message
        The message as the caller built it.
    from_address
        The backend's from address, which a `Message` never carries.
    message_id
        The `Message-ID` Epistole generated, with its angle brackets.
    date
        The `Date` Epistole set, timezone-aware in the sending machine's offset.
    """

    message: Message
    from_address: str
    message_id: str
    date: datetime


def _domain(from_address: str) -> str:
    """Return the from address's domain for a `Message-ID`, IDNA-encoded when it is not ASCII.

    The codec raises on an empty label, or on a label longer than 63 characters once encoded. See ADR-0015 for the rationale.
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
    """Key `refusals` by the caller's recipient string rather than by addr-spec (ADR-0004)."""
    refused: dict[str, Refusal] = {}
    taken: set[str] = set()
    for recipient, spec in zip(recipients, specs, strict=True):
        refusal: Refusal | None = refusals.get(spec)
        if refusal is not None and spec not in taken:
            taken.add(spec)
            refused[recipient] = refusal

    return refused

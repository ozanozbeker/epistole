"""What a send hands back, and the refusals it may carry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


@dataclass(frozen=True)
class Refusal:
    """A mail service's no to one recipient.

    Public because `MemoryBackend(refuse=)` takes one. A bounce is a different thing: it arrives later as a non-delivery report, and Epistole never sees it.

    Attributes
    ----------
    code
        What the service answered with: an SMTP reply code, or the HTTP status where an API refuses one address.
    reason
        The text the service gave. Never bytes: `smtplib` answers in bytes, and the transport decodes them as UTF-8 with `errors="replace"` rather than hand a caller something it has to decode.
    """

    code: int
    reason: str


@dataclass(frozen=True)
class SendResult:
    """The record that a mail service accepted one submission.

    Acceptance is not delivery. A send result never implies that anyone received the message.

    `Connection.send` builds every one, from the submission it stamped plus the refusals the transport answered with. A transport never builds one, so no backend can echo an id it invented.

    Attributes
    ----------
    message_id
        The `Message-ID` the send stamped, angle brackets kept. Never `None`, because Epistole wrote it rather than reading it back: Graph answers `202` with no body, Gmail returns a mailbox-local id that is not a `Message-ID`, and `smtplib` discards the queue id.
    date
        The `Date` the send stamped: timezone-aware, carrying the sending machine's offset.
    refused
        The recipients the service refused while accepting the rest, keyed by the caller's own recipient string. Only SMTP and `MemoryBackend(refuse=)` ever fill it; it is empty on Gmail and Graph, which accept or refuse the whole message.
    """

    message_id: str
    date: datetime
    refused: Mapping[str, Refusal]

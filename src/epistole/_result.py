"""`SendResult` is the value a send returns, and `Refusal` records one refused recipient in it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


@dataclass(frozen=True)
class Refusal:
    """A refusal records one recipient a mail service refused.

    It is public because `MemoryBackend(refuse=)` takes one. A bounce is not a refusal, and Epistole never receives one. See ADR-0004.

    Attributes
    ----------
    code
        The SMTP reply code, or the HTTP status where an API refuses one address.
    reason
        The text the service returned, never bytes.
    """

    code: int
    reason: str


@dataclass(frozen=True)
class SendResult:
    """A send result records that a mail service accepted one submission.

    Acceptance is not delivery, so a send result never means that anyone received the message. See ADR-0004.

    Attributes
    ----------
    message_id
        The `Message-ID` the send set, with its angle brackets.
    date
        The `Date` the send set, timezone-aware in the sending machine's offset.
    refused
        The recipients the service refused while accepting the rest, keyed by the caller's recipient string. Only SMTP and `MemoryBackend(refuse=)` fill it.
    """

    message_id: str
    date: datetime
    refused: Mapping[str, Refusal]

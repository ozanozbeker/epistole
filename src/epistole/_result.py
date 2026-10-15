"""`SendResult` is the value a send returns, and `Refusal` records one refused recipient in it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from epistole._backend import Submission


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
        The `Message-ID` the send set, with its angle brackets. The Gmail API replaces it with its own, so a recipient of a `GmailBackend` send sees a different one.
    date
        The `Date` the send set, timezone-aware in the sending machine's offset.
    refused
        The recipients the service refused while accepting the rest, keyed by the caller's recipient string. Only SMTP and `MemoryBackend(refuse=)` fill it.
    submission
        The submission the transport received. `submission.as_bytes()` returns it as the bytes of an `.eml` file. See ADR-0022.
    """

    refused: Mapping[str, Refusal]
    submission: Submission

    @property
    def message_id(self) -> str:
        """Return the submission's `Message-ID`, which a send result holds once, in `submission` (ADR-0015)."""
        return self.submission.message_id

    @property
    def date(self) -> datetime:
        """Return the submission's `Date`."""
        return self.submission.date

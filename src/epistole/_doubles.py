"""The test doubles are backends that record or render a submission instead of sending it."""

from __future__ import annotations

import sys
from email.utils import format_datetime
from typing import TYPE_CHECKING, override

from epistole._address import addr_spec, check_address
from epistole._backend import Backend

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import TextIO

    from epistole._backend import Submission, Transport
    from epistole._message import Message
    from epistole._result import Refusal


class MemoryBackend(Backend):
    """A memory backend records each submission instead of sending it.

    See ADR-0015 for its design.

    Parameters
    ----------
    refuse
        Maps an address to the refusal it gets, matched by addr-spec. A key that is not an address raises here, rather than never matching.

    Attributes
    ----------
    submissions
        Every submission at least one recipient accepted, from every connection, in the order the submits completed. Reset it with `list.clear()`.

    Examples
    --------
    ```python
    from epistole import MemoryBackend, Message, Refusal

    backend = MemoryBackend(from_address="reports@example.com")
    backend.send(Message(text="Weekly numbers").to("ada@example.com"))

    backend.submissions[0].message.to_  # ("ada@example.com",)
    backend.submissions[0].from_address  # "reports@example.com"
    ```

    Refuse one recipient, and the backend accepts the rest, as SMTP does:

    ```python
    backend = MemoryBackend(refuse={"ada@example.com": Refusal(550, "No such mailbox")})
    result = backend.send(
        Message(text="Weekly numbers").to("ada@example.com", "bob@example.com")
    )

    result.refused  # {"ada@example.com": Refusal(code=550, reason="No such mailbox")}
    ```
    """

    submissions: list[Submission]

    def __init__(
        self,
        *,
        from_address: str = "epistole@example.invalid",
        refuse: Mapping[str, Refusal] | None = None,
    ) -> None:
        super().__init__(from_address=from_address)
        self.submissions = []
        self._refuse: dict[str, Refusal] = _by_addr_spec(refuse or {})

    @override
    def _open(self) -> Transport:
        return _MemoryTransport(self.submissions, self._refuse)


class _MemoryTransport:
    """`MemoryBackend` opens this transport, which appends to the backend's list."""

    def __init__(
        self,
        submissions: list[Submission],
        refuse: Mapping[str, Refusal],
        /,
    ) -> None:
        self._submissions = submissions
        self._refuse = refuse

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Record `submission` unless every recipient was refused (ADR-0015), and return the refusals keyed by addr-spec."""
        refused: dict[str, Refusal] = {}
        accepted = False
        for recipient in submission.message.recipients:
            spec: str = addr_spec(recipient)
            refusal: Refusal | None = self._refuse.get(spec)
            if refusal is None:
                accepted = True
            else:
                refused[spec] = refusal

        if accepted:
            self._submissions.append(submission)

        return refused

    def close(self) -> None:
        """Do nothing, because there is no link to close."""


class ConsoleBackend(Backend):
    """A console backend writes a rendering of each submission to a stream instead of sending it.

    It writes the plain text in full, and the HTML and each attachment as a size. Nothing should parse the rendering. It is never the bytes a backend sends. See ADR-0015.

    Parameters
    ----------
    stream
        `None` means `sys.stdout` as it is at each send, because pytest's `capsys` and Jupyter replace it after import.

    Examples
    --------
    ```python
    from epistole import ConsoleBackend, Message

    backend = ConsoleBackend(from_address="reports@example.com")
    backend.send(
        Message(text="Weekly numbers")
        .to("ada@example.com")
        .subject("Weekly numbers")
        .attach(b"%PDF", filename="weekly.pdf")
    )
    # From: reports@example.com
    # To: ada@example.com
    # Message-ID: <179021486392.66219.11904006491029159968@example.com>
    # Date: Wed, 23 Sep 2026 21:54:23 -0400
    # Subject: Weekly numbers
    # Attachment: weekly.pdf (application/pdf, 4 bytes)
    #
    # Weekly numbers
    # -------------------------------------------------------------------------------
    ```
    """

    def __init__(
        self,
        *,
        from_address: str = "epistole@example.invalid",
        stream: TextIO | None = None,
    ) -> None:
        super().__init__(from_address=from_address)
        self._stream = stream

    @override
    def _open(self) -> Transport:
        return _ConsoleTransport(self._stream)


class _ConsoleTransport:
    """`ConsoleBackend` opens this transport, which writes to the backend's stream."""

    def __init__(self, stream: TextIO | None, /) -> None:
        self._stream = stream

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Write a rendering of `submission`, and return no refusals."""
        stream: TextIO = sys.stdout if self._stream is None else self._stream
        stream.write(_render(submission))
        stream.flush()
        return {}

    def close(self) -> None:
        """Do nothing, because there is no link to close."""


def _render(submission: Submission) -> str:
    """Return the text `ConsoleBackend` writes for `submission`."""
    message: Message = submission.message
    lines: list[str] = [f"From: {submission.from_address}"]
    for name, addresses in (
        ("To", message.to_),
        ("Cc", message.cc_),
        ("Bcc", message.bcc_),
        ("Reply-To", message.reply_to_),
    ):
        if addresses:
            lines.append(f"{name}: {', '.join(addresses)}")

    lines.extend(f"{name}: {value}" for name, value in message.headers_.items())
    lines.append(f"Message-ID: {submission.message_id}")
    lines.append(f"Date: {format_datetime(submission.date)}")
    if message.subject_ is not None:
        lines.append(f"Subject: {message.subject_}")

    if message.html is not None:
        lines.append(f"HTML: {len(message.html.encode()):,} bytes")

    lines.extend(
        f"Attachment: {one.filename} ({one.content_type}, {len(one.data):,} bytes)"
        for one in message.attachments
    )
    # The HTML names an inline image by its content id, which may differ from its filename.
    lines.extend(
        f"Inline image: cid:{one.content_id} ({one.filename}, {one.content_type}, {len(one.data):,} bytes)"
        for one in message.inline_images
    )

    lines += ["", message.text, "-" * 79]
    return "\n".join(lines) + "\n"


def _by_addr_spec(refuse: Mapping[str, Refusal]) -> dict[str, Refusal]:
    """Check each key of `refuse`, and key the refusals by addr-spec so a key with a display name still matches."""
    for address in refuse:
        check_address(address)

    return {addr_spec(address): refusal for address, refusal in refuse.items()}

"""The test doubles are backends that record or render a submission instead of sending it."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from epistole._address import addr_spec, check_address
from epistole._backend import Backend

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epistole._backend import Submission, Transport
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


def _by_addr_spec(refuse: Mapping[str, Refusal]) -> dict[str, Refusal]:
    """Check each key of `refuse`, and key the refusals by addr-spec so a key with a display name still matches."""
    for address in refuse:
        check_address(address)

    return {addr_spec(address): refusal for address, refusal in refuse.items()}

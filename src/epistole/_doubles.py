"""The test doubles: backends that record or render instead of sending."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from epistole._address import addr_spec, check_address
from epistole._backend import Backend

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epistole._backend import Submission, Transport
    from epistole._result import Refusal


class MemoryBackend(Backend):
    """A backend that records what it accepted instead of sending it.

    The submission it records is the same value `SMTPTransport` and `GraphTransport` receive, so a test that asserts on one is asserting about the real send path rather than about a shape invented for tests.

    `refuse=` is the one thing injectable, because a refusal is data on the same channel a real SMTP transport answers on. A hook that raised an arbitrary error on command would test that `raise` works, not that the mapping from native failures is right.

    Parameters
    ----------
    from_address
        Defaulted, because on a double there is no mail service to authorize one. `example.invalid` is reserved by RFC 2606 and passes the address check.
    refuse
        An address to say no to, mapped to the refusal to answer with. Matched against each recipient's addr-spec, and applied at submit. Each key takes the address check here, where the caller wrote it, so a key that could never match a recipient fails loudly rather than silently never firing.

    Attributes
    ----------
    submissions
        Every submission a recipient accepted, in submit-completion order. It lives on the backend, so it survives every connection, and it is the one mutable thing a backend holds. There is no reset method: `list.clear()` already exists, and a fresh backend per test starts empty.

    Examples
    --------
    ```python
    backend = MemoryBackend(from_address="reports@example.com")
    backend.send(Message(text="Weekly numbers").to("ada@example.com"))

    backend.submissions[0].message.to_  # ("ada@example.com",)
    backend.submissions[0].from_address  # "reports@example.com"
    ```

    Refuse one recipient and the rest still go, as on SMTP:

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
        """Hand back a transport that writes to this backend's list.

        Returns
        -------
        A transport holding the backend's list and its refusals.
        """
        return _MemoryTransport(self.submissions, self._refuse)


class _MemoryTransport:
    """The transport `MemoryBackend` opens: it appends where the backend can be read.

    A connection is a no-op here, so the list has to live on the backend to survive the `with`.
    """

    def __init__(
        self,
        submissions: list[Submission],
        refuse: Mapping[str, Refusal],
        /,
    ) -> None:
        self._submissions = submissions
        self._refuse = refuse

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Record `submission`, unless every recipient was refused.

        A send every recipient refused records nothing, so the double never holds a record of a send that raised `RecipientsRefusedError`, whose meaning is that nothing was submitted.

        Returns
        -------
        A refusal for each recipient `refuse=` names, keyed by addr-spec.
        """
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
        """Do nothing. There is no link to close."""


def _by_addr_spec(refuse: Mapping[str, Refusal]) -> dict[str, Refusal]:
    """Key `refuse` by addr-spec, so a key written with a display name still matches.

    Returns
    -------
    The same refusals, under the mailbox each key names.
    """
    for address in refuse:
        check_address(address)

    return {addr_spec(address): refusal for address, refusal in refuse.items()}

"""`Message` is the immutable value a caller builds and a backend sends."""

from __future__ import annotations

from typing import TYPE_CHECKING

from epistole._address import check_address

if TYPE_CHECKING:
    from collections.abc import Mapping


class Message:
    """A message holds the content, addressing, and subject a caller builds, as one frozen value.

    It compares and hashes by content. Every builder method returns a new message and leaves the receiver unchanged.

    A method named for a field replaces that field, so `.to("a").to("b")` addresses `b` alone. Nothing removes a field, so each address method takes at least one address. See ADR-0002.

    A builder method's value is an attribute with the method's name plus a trailing underscore, because the plain name is the method. See ADR-0007.

    Attributes
    ----------
    to_, cc_, bcc_, reply_to_
        The addresses the builder method of the same name set.
    subject_
        The subject `.subject()` set, or `None`.
    text
        The plain text.

    Raises
    ------
    TypeError
        When no content is supplied.
    ValueError
        When `text` is empty. See ADR-0008.
    """

    __slots__ = (
        "bcc_",
        "cc_",
        "reply_to_",
        "subject_",
        "text",
        "to_",
    )

    to_: tuple[str, ...]
    cc_: tuple[str, ...]
    bcc_: tuple[str, ...]
    reply_to_: tuple[str, ...]
    subject_: str | None
    text: str

    def __init__(self, *, text: str | None = None) -> None:
        if text is None:
            msg = "Message() needs content: pass text="
            raise TypeError(msg)

        if not text:
            msg = "text= cannot be empty. Build the message without it instead."
            raise ValueError(msg)

        _write(
            self,
            {
                "to_": (),
                "cc_": (),
                "bcc_": (),
                "reply_to_": (),
                "subject_": None,
                "text": text,
            },
        )

    def to(self, address: str, /, *more: str) -> Message:
        """Return a copy with the to addresses set, replacing any earlier `.to()`."""
        return self._copy(to_=_checked(address, more))

    def cc(self, address: str, /, *more: str) -> Message:
        """Return a copy with the cc addresses set, replacing any earlier `.cc()`."""
        return self._copy(cc_=_checked(address, more))

    def bcc(self, address: str, /, *more: str) -> Message:
        """Return a copy with the bcc addresses set, replacing any earlier `.bcc()`."""
        return self._copy(bcc_=_checked(address, more))

    def reply_to(self, address: str, /, *more: str) -> Message:
        """Return a copy with the reply-to addresses set, replacing any earlier `.reply_to()`."""
        return self._copy(reply_to_=_checked(address, more))

    def subject(self, subject: str, /) -> Message:
        """Return a copy with the subject set, replacing any earlier subject."""
        return self._copy(subject_=subject)

    @property
    def recipients(self) -> tuple[str, ...]:
        """Return every address a backend submits to, in to, cc, bcc order, with duplicates kept (ADR-0007)."""
        return self.to_ + self.cc_ + self.bcc_

    def __eq__(self, other: object) -> bool:
        """Compare by content."""
        if not isinstance(other, Message):
            return NotImplemented

        return self._key() == other._key()

    def __hash__(self) -> int:
        """Hash the content."""
        return hash(self._key())

    def __setattr__(self, name: str, value: object) -> None:
        """Raise `AttributeError`, because a message is frozen."""
        msg = f"Message is immutable, so {name} cannot be set. A builder method returns a new message."
        raise AttributeError(msg)

    def __delattr__(self, name: str) -> None:
        """Raise `AttributeError`, because a message is frozen."""
        msg = f"Message is immutable, so {name} cannot be deleted"
        raise AttributeError(msg)

    def _key(self) -> tuple[object, ...]:
        """Return every field in a fixed order, for `__eq__` and `__hash__`."""
        return (self.to_, self.cc_, self.bcc_, self.reply_to_, self.subject_, self.text)

    def _copy(self, **changes: object) -> Message:
        """Return a shallow copy with `changes` applied, without running `__init__` again."""
        copy: Message = object.__new__(Message)
        _write(
            copy, {name: getattr(self, name) for name in Message.__slots__} | changes
        )
        return copy


def _write(message: Message, fields: Mapping[str, object]) -> None:
    """Set `fields` on `message`, bypassing its frozen `__setattr__`."""
    for name, value in fields.items():
        object.__setattr__(message, name, value)


def _checked(address: str, more: tuple[str, ...]) -> tuple[str, ...]:
    """Check each address where the caller supplies it, and return all of them as a tuple."""
    addresses: tuple[str, *tuple[str, ...]] = (address, *more)
    for one in addresses:
        check_address(one)

    return addresses

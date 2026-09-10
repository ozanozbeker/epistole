"""The message: the immutable value a caller builds and a backend sends."""

from __future__ import annotations

from typing import TYPE_CHECKING

from epistole._address import check_address

if TYPE_CHECKING:
    from collections.abc import Mapping


class Message:
    """The content, addressing, and subject a caller hands to a backend.

    A message is a value. It is frozen. It compares and hashes by content. Every builder method hands back a new message instead of changing the receiver.

    Copy on write protects the loop Epistole exists for: a caller addresses one template per subscriber, and no subscriber carries into the next send.

    A method named for a field replaces that field, so `.to("a").to("b")` addresses `b` alone. Nothing removes. The address methods therefore take at least one address, and `.to(*[])` raises `TypeError` at the call site.

    A builder method's value reads back under the method's name plus a trailing underscore, because the plain name is the method. `recipients` and `text` carry no underscore, because no method claims them.

    Parameters
    ----------
    text
        The plain text the message ships.

    Attributes
    ----------
    to_
        The addresses `.to()` set.
    cc_
        The addresses `.cc()` set.
    bcc_
        The addresses `.bcc()` set.
    reply_to_
        The addresses `.reply_to()` set.
    subject_
        The subject `.subject()` set, or `None`.
    text
        The plain text every message carries.

    Raises
    ------
    TypeError
        When no content is supplied.
    ValueError
        When `text` is empty. A caller never means empty text. Reading it as absent would make `""` and `None` synonyms.
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
            msg = "text= cannot be empty; build the message without it instead"
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
        """Address the message. The new addresses replace any `.to()` already set.

        Returns
        -------
        A new message. The receiver does not change.
        """
        return self._copy(to_=_checked(address, more))

    def cc(self, address: str, /, *more: str) -> Message:
        """Copy the message. The new addresses replace any `.cc()` already set.

        Returns
        -------
        A new message. The receiver does not change.
        """
        return self._copy(cc_=_checked(address, more))

    def bcc(self, address: str, /, *more: str) -> Message:
        """Blind-copy the message. The new addresses replace any `.bcc()` already set.

        Returns
        -------
        A new message. The receiver does not change.
        """
        return self._copy(bcc_=_checked(address, more))

    def reply_to(self, address: str, /, *more: str) -> Message:
        """Point replies elsewhere. The new addresses replace any `.reply_to()` already set.

        Returns
        -------
        A new message. The receiver does not change.
        """
        return self._copy(reply_to_=_checked(address, more))

    def subject(self, subject: str, /) -> Message:
        """Set the subject. The new subject replaces any subject already set.

        Returns
        -------
        A new message. The receiver does not change.
        """
        return self._copy(subject_=subject)

    @property
    def recipients(self) -> tuple[str, ...]:
        """Every address a backend submits to: to, then cc, then bcc.

        A message keeps its duplicates. Dropping one would make the readback disagree with the message as built, and with what SMTP writes.
        """
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
        """Refuse the write, because a message is frozen."""
        msg = f"Message is immutable, so {name} cannot be set; a builder method returns a new message"
        raise AttributeError(msg)

    def __delattr__(self, name: str) -> None:
        """Refuse the deletion, because nothing leaves a message."""
        msg = f"Message is immutable, so {name} cannot be deleted"
        raise AttributeError(msg)

    def _key(self) -> tuple[object, ...]:
        """Return the tuple `__eq__` and `__hash__` read.

        Returns
        -------
        Every field, in a fixed order.
        """
        return (self.to_, self.cc_, self.bcc_, self.reply_to_, self.subject_, self.text)

    def _copy(self, **changes: object) -> Message:
        """Return a shallow copy that carries `changes`, without running construction again.

        Returns
        -------
        A new message.
        """
        copy: Message = object.__new__(Message)
        _write(
            copy, {name: getattr(self, name) for name in Message.__slots__} | changes
        )
        return copy


def _write(message: Message, fields: Mapping[str, object]) -> None:
    """Set `fields` on `message`, going around its frozen `__setattr__`."""
    for name, value in fields.items():
        object.__setattr__(message, name, value)


def _checked(address: str, more: tuple[str, ...]) -> tuple[str, ...]:
    """Return the addresses as a tuple, checking each one here, where the caller supplied it."""
    addresses: tuple[str, *tuple[str, ...]] = (address, *more)
    for one in addresses:
        check_address(one)

    return addresses

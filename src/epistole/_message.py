"""`Message` is the immutable value a caller builds and a backend sends."""

from __future__ import annotations

from typing import TYPE_CHECKING

from epistole._address import check_address
from epistole._text import html_to_text

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class Message:
    """A message holds the content, addressing, and subject a caller builds, as one frozen value.

    It compares and hashes by content. Every builder method returns a new message and leaves the receiver unchanged.

    A method named for a field replaces that field, so `.to("a").to("b")` addresses `b` alone. Nothing removes a field, so each address method takes at least one address. See ADR-0002.

    A builder method's value is an attribute with the method's name plus a trailing underscore, because the plain name is the method. See ADR-0007.

    Parameters
    ----------
    html
        The HTML. Epistole derives the plain text from it with `html_to_text`, unless the caller supplies `text` or `text_renderer`.
    markdown
        The Markdown source. Epistole renders the HTML from it on markdown-it-py's `commonmark` preset and sends the source as the plain text, unless the caller supplies `text`.
    text
        The plain text. Epistole sends it verbatim and derives nothing from `html`. It may be `""` when the subject holds the whole message.
    text_renderer
        Derives the plain text from `html` in place of `html_to_text`. It runs once, at construction. The message does not keep it, so equality compares content alone. An exception it raises propagates unchanged.

    Attributes
    ----------
    to_, cc_, bcc_, reply_to_
        The addresses the builder method of the same name set.
    subject_
        The subject `.subject()` set, or `None`.
    html
        The HTML the caller supplied or Epistole rendered from `markdown`, or `None` on a text-only message.
    text
        The plain text. It is the Markdown source for `markdown=`. It is `""` for `text=""`, and also for HTML that holds no text, such as a lone image with no alt text.

    Raises
    ------
    TypeError
        When both `html` and `markdown` are supplied, when no content is supplied, or when `text_renderer` accompanies `text` or `markdown`.
    ValueError
        When `text_renderer` returns something other than a `str`. See ADR-0008.
    ImportError
        When `markdown` is supplied and `epistole[markdown]` is not installed.
    """

    __slots__ = (
        "bcc_",
        "cc_",
        "html",
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
    html: str | None
    text: str

    def __init__(
        self,
        *,
        html: str | None = None,
        markdown: str | None = None,
        text: str | None = None,
        text_renderer: Callable[[str], str] | None = None,
    ) -> None:
        if html is not None and markdown is not None:
            msg = "Message() takes html= or markdown=, not both"
            raise TypeError(msg)

        if html is None and markdown is None and text is None:
            msg = "Message() needs content: pass html=, markdown=, or text="
            raise TypeError(msg)

        if text_renderer is not None and (text is not None or markdown is not None):
            msg = "text_renderer= applies to html= alone, so pass it without text= or markdown="
            raise TypeError(msg)

        if markdown is not None:
            try:
                from markdown_it import MarkdownIt  # noqa: PLC0415
            except ImportError as error:
                msg = "Message(markdown=) needs markdown-it-py, so install the extra: pip install 'epistole[markdown]'"
                raise ImportError(msg) from error

            html = MarkdownIt("commonmark").render(markdown)
            if text is None:
                text = markdown

        if text is None and html is not None:
            rendered: object = (
                html_to_text if text_renderer is None else text_renderer
            )(html)
            if not isinstance(rendered, str):
                msg = f"text_renderer= returned {type(rendered).__name__}, not str"
                raise ValueError(msg)

            text = rendered

        _write(
            self,
            {
                "to_": (),
                "cc_": (),
                "bcc_": (),
                "reply_to_": (),
                "subject_": None,
                "html": html,
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
        return (
            self.to_,
            self.cc_,
            self.bcc_,
            self.reply_to_,
            self.subject_,
            self.html,
            self.text,
        )

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

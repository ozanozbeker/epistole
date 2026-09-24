"""`Message` is the immutable value a caller builds and a backend sends. `Attachment` holds the bytes, filename, and content type of one attachment or inline image."""

from __future__ import annotations

import mimetypes
import re
from base64 import b64decode
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, override
from urllib.parse import unquote_to_bytes

from epistole._address import LINE_BREAK, check_address
from epistole._text import Parser, html_to_text

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import BinaryIO

# The type and the subtype each match RFC 6838's restricted-name.
_MEDIA_TYPE = re.compile(r"[A-Za-z0-9][\w!#$&^.+-]*/[A-Za-z0-9][\w!#$&^.+-]*", re.ASCII)

# HTMLParser reports attribute values without their offsets, so this tokenizes a start tag's attributes as HTML5 does.
_ATTRIBUTE = re.compile(
    r"""[\t\n\f\r /]*(?P<name>[^\t\n\f\r />][^\t\n\f\r /=>]*)(?:[\t\n\f\r ]*=[\t\n\f\r ]*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\t\n\f\r >]*)))?"""
)

# RFC 5322 ftext: printable ASCII 33 to 126, except the colon.
_FIELD_NAME = re.compile(r"[!-9;-~]+")

# ADR-0016 lists the headers Epistole writes, lowercased because RFC 5322 names are case-insensitive.
_OWNED_NAMES = frozenset(
    {
        "from",
        "to",
        "cc",
        "bcc",
        "reply-to",
        "subject",
        "message-id",
        "date",
        "mime-version",
        "content-type",
        "content-transfer-encoding",
        "content-id",
        "content-disposition",
    }
)


class Message:
    """A message holds the content, addressing, subject, custom headers, and attachments a caller builds, as one frozen value.

    It compares and hashes by content. Every builder method returns a new message and leaves the receiver unchanged.

    A method named for a field replaces that field, so `.to("a").to("b")` addresses `b` alone. `.attach()` and `.embed()` append instead. Nothing removes a field, so each address method takes at least one address. See ADR-0002.

    A builder method's value is an attribute with the method's name plus a trailing underscore, because the plain name is the method. See ADR-0007.

    Parameters
    ----------
    html
        The HTML. Epistole moves each `data:` image in an `<img src>` into an inline image and rewrites the `src` to `cid:`. It then derives the plain text from the result with `html_to_text`, unless the caller supplies `text` or `text_renderer`. See ADR-0003.
    markdown
        The Markdown source. Epistole renders the HTML from it on markdown-it-py's `commonmark` preset and sends the source as the plain text, unless the caller supplies `text`.
    text
        The plain text. Epistole sends it verbatim and derives nothing from `html`. It may be `""` when the subject holds the whole message.
    text_renderer
        Derives the plain text from the rewritten `html` in place of `html_to_text`. It runs once, at construction. The message does not keep it, so equality compares content alone. An exception it raises propagates unchanged.

    Attributes
    ----------
    to_, cc_, bcc_, reply_to_
        The addresses the builder method of the same name set.
    subject_
        The subject `.subject()` set, or `None`.
    headers_
        The custom headers `.headers()` set, as a read-only mapping in the caller's order. It is empty until `.headers()` sets it, and it never holds a header Epistole writes.
    html
        The HTML the caller supplied or Epistole rendered from `markdown`, or `None` on a text-only message. The rewrite has replaced each `data:` image in it with a `cid:` reference.
    text
        The plain text. It is the Markdown source for `markdown=`. It is `""` for `text=""`, and also for HTML that holds no text, such as a lone image with no alt text.
    attachments
        What `.attach()` added, in call order.
    inline_images
        The inline images the `data:` rewrite made come first, one per distinct media type and bytes. What `.embed()` added follows, in call order.

    Raises
    ------
    TypeError
        When both `html` and `markdown` are supplied, when no content is supplied, or when `text_renderer` accompanies `text` or `markdown`.
    ValueError
        When `text_renderer` returns something other than a `str`, or when the payload of a `data:` image does not decode. See ADR-0003 and ADR-0008.
    ImportError
        When `markdown` is supplied and `epistole[markdown]` is not installed.
    """

    __slots__ = (
        "_header_pairs",
        "attachments",
        "bcc_",
        "cc_",
        "headers_",
        "html",
        "inline_images",
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
    headers_: Mapping[str, str]
    _header_pairs: tuple[tuple[str, str], ...]
    html: str | None
    text: str
    attachments: tuple[Attachment, ...]
    inline_images: tuple[Attachment, ...]

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

        inline_images: tuple[Attachment, ...] = ()
        if html is not None:
            html, inline_images = _rewrite_data_images(html)

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
                "headers_": MappingProxyType({}),
                "_header_pairs": (),
                "html": html,
                "text": text,
                "attachments": (),
                "inline_images": inline_images,
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
        """Return a copy with the subject set, replacing any earlier subject.

        Raises
        ------
        ValueError
            When `subject` holds a line break. See ADR-0016.
        """
        if LINE_BREAK.search(subject):
            msg = f"{subject!r} holds a line break, such as \\r or \\n. A subject is one line."
            raise ValueError(msg)

        return self._copy(subject_=subject)

    def headers(self, mapping: Mapping[str, str], /) -> Message:
        """Return a copy with the custom headers set, replacing any earlier `.headers()`.

        It copies `mapping` at the call and keeps its order. See ADR-0016.

        Raises
        ------
        ValueError
            When `mapping` is empty, or when two names differ only in case. When a name holds a space, a colon, or a character outside printable ASCII, or is a name Epistole writes. When a value is not a `str`, or holds a line break.
        """
        pairs: tuple[tuple[str, str], ...] = _checked_headers(mapping)
        return self._copy(_header_pairs=pairs, headers_=MappingProxyType(dict(pairs)))

    def attach(
        self,
        source: Path | bytes | BinaryIO,
        /,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> Message:
        """Return a copy with `source` appended as an attachment.

        Parameters
        ----------
        source
            The bytes, or a `Path` or binary file object to read them from. Epistole reads it at call time. A `Path` supplies its own filename. A file object is read from its current position and left open.
        filename
            The name the recipient sees. Bytes and a file object need one, because Epistole never reads a file object's `.name`.
        content_type
            A bare media type such as `application/pdf`. It defaults to the type `filename` implies, or to `application/octet-stream` when the filename implies none or names a compressed file. Epistole never inspects the bytes.

        Raises
        ------
        TypeError
            When `source` is a `str`, a `bytearray`, a `memoryview`, or a text-mode file, or when the caller passes a source other than a `Path` without `filename`. See ADR-0018.
        ValueError
            When the filename holds a line break, or when `content_type` is not a bare `type/subtype`, such as one with parameters.
        """
        name: str = _filename(source, filename)
        attachment = Attachment(
            filename=name,
            content_type=_content_type(name, content_type),
            data=_read(source),
            content_id=None,
        )
        return self._copy(attachments=(*self.attachments, attachment))

    def embed(
        self,
        source: Path | bytes | BinaryIO,
        /,
        *,
        filename: str | None = None,
        cid: str | None = None,
        content_type: str | None = None,
    ) -> Message:
        """Return a copy with `source` appended as an inline image, which the HTML names as `cid:` plus its content id.

        Parameters
        ----------
        source
            The image, read now, as for `.attach()`.
        filename
            The name the recipient sees. It defaults to a `Path` source's own name, or else to `cid`.
        cid
            The content id. It defaults to `filename`, so `.embed(Path("logo.png"))` matches `<img src="cid:logo.png">`.
        content_type
            As for `.attach()`, and it must be `image/*`.

        Raises
        ------
        TypeError
            As for `.attach()`, or when the caller passes a source other than a `Path` with neither `filename` nor `cid`.
        ValueError
            When the filename or the content id holds a line break, when the content type is not `image/*`, or when the message already holds an inline image under the same content id, including one the `data:` rewrite made. See ADR-0018.
        """
        # Runs before _filename, so a line break in cid raises the content id error, not the filename one.
        if cid is not None and LINE_BREAK.search(cid):
            msg = f"the content id {cid!r} holds a line break, such as \\r or \\n. Pass cid= without one."
            raise ValueError(msg)

        name: str = _filename(source, filename, cid)
        kind: str = _content_type(name, content_type)
        # RFC 2045 makes a media type case-insensitive.
        if not kind.lower().startswith("image/"):
            msg = f"an inline image needs an image/* content type, and {name!r} has {kind!r}. Pass content_type=, or add it with .attach()."
            raise ValueError(msg)

        content_id: str = name if cid is None else cid
        if any(image.content_id == content_id for image in self.inline_images):
            msg = f"the message already holds an inline image under content id {content_id!r}. Pass cid= to embed this one under another."
            raise ValueError(msg)

        image = Attachment(
            filename=name, content_type=kind, data=_read(source), content_id=content_id
        )
        return self._copy(inline_images=(*self.inline_images, image))

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
            self._header_pairs,
            self.html,
            self.text,
            self.attachments,
            self.inline_images,
        )

    def _copy(self, **changes: object) -> Message:
        """Return a shallow copy with `changes` applied, without running `__init__` again."""
        copy: Message = object.__new__(Message)
        _write(
            copy, {name: getattr(self, name) for name in Message.__slots__} | changes
        )
        return copy


@dataclass(frozen=True)
class Attachment:
    """An attachment is bytes with a filename and a content type that a message carries.

    `Message.attach()` and `Message.embed()` build one. See ADR-0018.

    Attributes
    ----------
    filename
        The name the recipient sees.
    content_type
        A bare media type, with no parameters.
    data
        The bytes, which the builder method reads at call time.
    content_id
        The name the HTML uses after `cid:` on an inline image, or `None` on an attachment.
    """

    filename: str
    content_type: str
    data: bytes
    content_id: str | None


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


def _checked_headers(mapping: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Check each custom header where the caller supplies it, and return them as pairs in the caller's order."""
    pairs: tuple[tuple[str, str], ...] = tuple(mapping.items())
    if not pairs:
        msg = ".headers() takes at least one custom header, because no builder method removes anything. Build the message without .headers() to send none."
        raise ValueError(msg)

    seen: set[str] = set()
    for name, value in pairs:
        if not isinstance(name, str) or _FIELD_NAME.fullmatch(name) is None:
            msg = f"{name!r} is not a header name. A name is a str of one or more printable ASCII characters, with no space and no colon."
            raise ValueError(msg)

        lowered: str = name.lower()
        if lowered in _OWNED_NAMES:
            msg = f"Epistole writes the {name!r} header itself, so it cannot be a custom header"
            raise ValueError(msg)

        # A dict holds both spellings of one name, and a backend would write a line for each.
        if lowered in seen:
            msg = f"{name!r} repeats an earlier header name in another case. RFC 5322 names are case-insensitive, so pass one value per name."
            raise ValueError(msg)

        seen.add(lowered)

        # Graph sends JSON, so no stdlib check raises on a line break there (ADR-0016).
        if not isinstance(value, str) or LINE_BREAK.search(value):
            msg = f"the value of custom header {name!r} must be a str with no line break, such as \\r or \\n"
            raise ValueError(msg)

    return pairs


def _filename(
    source: Path | bytes | BinaryIO, filename: str | None, cid: str | None = None
) -> str:
    """Check the type of `source`, then return `filename`, or else a `Path` source's own name, or else `cid`, once checked for a line break."""
    if isinstance(source, str):
        msg = "Epistole never reads a str as a path. Wrap it in Path()."
        raise TypeError(msg)

    if not isinstance(source, Path | bytes) and not hasattr(source, "read"):
        msg = f"source is a {type(source).__name__}, not a Path, bytes, or binary file. Convert a bytearray or memoryview with bytes()."
        raise TypeError(msg)

    if filename is not None:
        name: str = filename
    elif isinstance(source, Path):
        name = source.name
    elif cid is not None:
        name = cid
    else:
        msg = f"a {type(source).__name__} source needs filename=, because only a Path supplies its own filename. .embed() takes cid= as well."
        raise TypeError(msg)

    if LINE_BREAK.search(name):
        msg = f"the filename {name!r} holds a line break, such as \\r or \\n. Pass filename= to name it without one."
        raise ValueError(msg)

    return name


def _content_type(filename: str, content_type: str | None) -> str:
    """Return `content_type` once checked, or else the type `filename` implies, or else `application/octet-stream`."""
    if content_type is None:
        guessed, encoding = mimetypes.guess_file_type(filename)
        # A compressed file's bytes are not its inner type, and MIME has no header to mark the compression.
        return guessed if guessed and not encoding else "application/octet-stream"

    if _MEDIA_TYPE.fullmatch(content_type) is None:
        msg = f"content_type={content_type!r} is not a media type without parameters, such as 'application/pdf'"
        raise ValueError(msg)

    return content_type


def _read(source: Path | bytes | BinaryIO) -> bytes:
    """Return the bytes of `source`, reading it now."""
    if isinstance(source, Path):
        return source.read_bytes()

    if isinstance(source, bytes):
        return source

    data: object = source.read()
    if not isinstance(data, bytes):
        msg = f"{type(source).__name__}.read() returned {type(data).__name__}, not bytes. Open the file in binary mode, with 'rb'."
        raise TypeError(msg)

    return data


def _rewrite_data_images(html: str) -> tuple[str, tuple[Attachment, ...]]:
    """Return `html` with the `src` of each `data:` image rewritten to `cid:`, and the inline images the rewrite made (ADR-0003)."""
    found: list[tuple[int, int, Attachment]] = _DataImageFinder(html).found
    parts: list[str] = []
    end: int = 0
    for start, stop, image in found:
        parts += (html[end:start], f"cid:{image.content_id}")
        end = stop

    parts.append(html[end:])
    # Two images with one media type and one set of bytes are equal, so this keeps the first of each.
    return "".join(parts), tuple(dict.fromkeys(image for *_, image in found))


class _DataImageFinder(Parser):
    """A finder holds the span of each `<img>` `src` value that is a `data:` image in the HTML it parses, and the inline image decoded from that value."""

    def __init__(self, html: str) -> None:
        super().__init__()
        # getpos() counts only "\n" as a line end, so the index of a position is its line's start plus its column.
        self._line_starts: list[int] = [
            0,
            *(match.end() for match in re.finditer("\n", html)),
        ]
        self.found: list[tuple[int, int, Attachment]] = []
        self.feed(html)
        self.close()

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return

        # HTML5 keeps the first of two attributes with one name.
        src: str | None = next((value for name, value in attrs if name == "src"), None)
        if src is None:
            return

        line, column = self.getpos()
        try:
            image: Attachment | None = _inline_image(src)
        except ValueError as error:
            msg = f"the <img> at line {line}, column {column + 1} holds a data: URI whose payload does not decode ({error}). Fix the payload, or reference the image as cid: and add it with .embed()."
            raise ValueError(msg) from error

        span: tuple[int, int] | None = _src_span(self.get_starttag_text() or "")
        if image is not None and span is not None:
            start: int = self._line_starts[line - 1] + column
            self.found.append((start + span[0], start + span[1], image))


def _src_span(start_tag: str) -> tuple[int, int] | None:
    """Return the span of the first `src` value in the text of an `<img>` start tag, without its quotes."""
    for match in _ATTRIBUTE.finditer(start_tag, len("<img")):
        if match["name"].lower() == "src":
            for form in ("double", "single", "bare"):
                if match[form] is not None:
                    return match.span(form)

            return None

    return None


def _inline_image(uri: str) -> Attachment | None:
    """Return the inline image decoded from `uri` when it is a `data:` URI with an `image/*` media type, else `None`."""
    scheme, _, rest = uri.strip().partition(":")
    header, comma, payload = rest.partition(",")
    # RFC 2045 makes a media type case-insensitive, so lowercasing it lets two spellings share one inline image.
    media_type, *parameters = (part.strip().lower() for part in header.split(";"))
    if (
        scheme.lower() != "data"
        or not comma
        or not media_type.startswith("image/")
        or _MEDIA_TYPE.fullmatch(media_type) is None
    ):
        return None

    data: bytes = unquote_to_bytes(payload)
    if parameters and parameters[-1] == "base64":
        # Browsers skip whitespace and missing padding in a base64 payload, so this does too.
        data = b"".join(data.split())
        data = b64decode(data + b"=" * (-len(data) % 4), validate=True)

    # The digest covers the media type, so image/jpeg and image/pjpeg over the same bytes get two ids.
    content_id: str = sha256(f"{media_type}\0".encode() + data).hexdigest()[:16] + (
        mimetypes.guess_extension(media_type) or ""
    )
    return Attachment(
        filename=content_id, content_type=media_type, data=data, content_id=content_id
    )

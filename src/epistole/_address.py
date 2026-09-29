"""`Address` writes an address with its display name. `check_address` checks an address string. `_message.py` imports `LINE_BREAK` and `check_text` from here, because other text a caller passes takes the same checks as an address."""

import re
from email.policy import default
from email.utils import formataddr, getaddresses
from typing import Self

LINE_BREAK = re.compile(r"[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
"""str.splitlines() splits on each of these, and EmailMessage raises on a value it splits."""

_SURROGATE = re.compile(r"[\ud800-\udfff]")
"""UTF-8 cannot encode a code point in this range, so no backend sends one intact (ADR-0016)."""


class Address(str):
    """An `Address` is a `str` that holds one address in its display-name form.

    `email.utils.formataddr` writes the value, so a hand-written string with the same text is indistinguishable from it. See ADR-0014.

    Parameters
    ----------
    name
        The display name, quoted or RFC 2047-encoded as needed. An empty name leaves the address bare.
    email
        The address, in ASCII. Pass a non-ASCII address as a plain string instead.

    Raises
    ------
    TypeError
        When `name` or `email` is not a `str`.
    ValueError
        When `name` or `email` holds a surrogate. When `email` is not ASCII, with the `UnicodeEncodeError` as `__cause__`.

    Examples
    --------
    ```python
    from epistole import Address

    Address("Ada Lovelace", "ada@example.com")  # "Ada Lovelace <ada@example.com>"
    Address("Lovelace, Ada", "ada@example.com")  # '"Lovelace, Ada" <ada@example.com>'
    ```
    """

    __slots__ = ()

    def __new__(cls, name: str, email: str) -> Self:
        """Return the formatted address."""
        # formataddr raises the same UnicodeEncodeError for a surrogate in either argument, so only a check before it can name which.
        check_text(name, f"name={name!r}")
        check_text(email, f"email={email!r}")
        try:
            formatted: str = formataddr((name, email))
        except UnicodeEncodeError as error:
            msg = f"{email!r} is not ASCII, so `Address()` cannot format it. Pass it as a plain string instead."
            raise ValueError(msg) from error

        return super().__new__(cls, formatted)


def check_address(address: str, label: str) -> None:
    """Raise `ValueError` unless `address` holds exactly one address on one line and no surrogate, with something on both sides of its last `@`.

    A non-`str` raises `TypeError` instead, from `check_text`. See ADR-0014 for why the check looks no further.
    """
    check_text(address, label)
    if LINE_BREAK.search(address):
        msg = f"{address!r} holds a line break, such as \\r or \\n. An address is one line."
        raise ValueError(msg)

    pairs: list[tuple[str, str]] = getaddresses([address])
    if len(pairs) != 1:
        msg = (
            f"{address!r} holds {len(pairs)} addresses. Pass one address per argument."
        )
        raise ValueError(msg)

    local, _, domain = pairs[0][1].rpartition("@")
    if not local or not domain:
        msg = f"{address!r} is not an address: it needs something on both sides of its last @"
        raise ValueError(msg)


def check_text(text: object, label: str) -> None:
    """Raise `TypeError` naming `label` when `text` is not a `str`, and `ValueError` when it holds a surrogate, the one kind of code point UTF-8 cannot encode.

    Every text a caller passes takes this check before any other, so no caller sees the `TypeError` that `re` raises for a non-`str` (ADR-0004, ADR-0016).
    """
    if not isinstance(text, str):
        msg = f"{label} must be a str, not {type(text).__name__}"
        raise TypeError(msg)

    if match := _SURROGATE.search(text):
        msg = f"{label} holds the surrogate U+{ord(match[0]):04X} at index {match.start()}. UTF-8 cannot encode one. os.fsdecode writes one for each byte it cannot decode, so decode those bytes in their real encoding instead."
        raise ValueError(msg)


def addr_spec(address: str) -> str:
    """Return the addr-spec of `address`, without its display name.

    Every caller has run `check_address` first, so `getaddresses` returns exactly one pair.
    """
    return getaddresses([address])[0][1]


def name_and_addr_spec(address: str) -> tuple[str, str]:
    """Return the display name of `address` as text, and its addr-spec.

    `Address` writes a non-ASCII name as RFC 2047 encoded-words, and an unstructured header decodes them without raising on a malformed one.
    """
    name, spec = getaddresses([address])[0]
    return str(default.header_factory("Comments", name)), spec

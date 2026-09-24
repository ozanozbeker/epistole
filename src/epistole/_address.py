"""`Address` writes an address with its display name. `check_address` and `addr_spec` check and parse an address string. `LINE_BREAK` matches what no header value may hold."""

import re
from email.utils import formataddr, getaddresses
from typing import Self

LINE_BREAK = re.compile(r"[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
"""str.splitlines() splits on each of these, and EmailMessage raises on a value it splits."""


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
    ValueError
        When `email` is not ASCII, with the `UnicodeEncodeError` as `__cause__`.

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
        try:
            formatted: str = formataddr((name, email))
        except UnicodeEncodeError as error:
            msg = f"{email!r} is not ASCII, so `Address()` cannot format it. Pass it as a plain string instead."
            raise ValueError(msg) from error

        return super().__new__(cls, formatted)


def check_address(address: str) -> None:
    """Raise `ValueError` unless `address` holds exactly one address on one line, with something on both sides of its last `@`.

    See ADR-0014 for why the check looks no further.
    """
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


def addr_spec(address: str) -> str:
    """Return the addr-spec of `address`, without its display name.

    Every caller has run `check_address` first, so `getaddresses` returns exactly one pair.
    """
    return getaddresses([address])[0][1]

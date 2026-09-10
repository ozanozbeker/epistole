"""The address type and the structural check every address passes."""

from email.utils import formataddr, getaddresses
from typing import Self


class Address(str):
    """One address that carries a display name.

    This helper writes the display-name form and nothing else. `email.utils.formataddr` produces the value, so a hand-written string reads the same and nothing tells the two apart. The class subclasses `str`, so `str` stays the only address type in every Epistole signature.

    `formataddr` cannot format a non-ASCII address, so neither can this helper. The plain-string path stays open for those addresses.

    Parameters
    ----------
    name
        The display name. `formataddr` quotes it when it needs quoting, and RFC 2047-encodes it when it is not ASCII. An empty name leaves the address bare.
    email
        The address. It must be ASCII.

    Raises
    ------
    ValueError
        When `email` is not ASCII. The `UnicodeEncodeError` rides along as `__cause__`.

    Examples
    --------
    ```python
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
            msg = f"{email!r} is not ASCII, so `Address()` cannot format it; pass it as a plain string instead"
            raise ValueError(msg) from error

        return super().__new__(cls, formatted)


def check_address(address: str) -> None:
    """Raise unless `address` holds exactly one structurally sound address.

    Sound means two things. `getaddresses` reads exactly one pair out of the string. Both halves of that pair's addr-spec, split on its last `@`, hold something.

    The check looks no further. It reads no character set, requires no dot in the domain, consults no TLD list, and makes no DNS query. The mail service answers whether the mailbox exists.

    The check splits on the last `@` rather than the only one, because a quoted local part may carry an `@` of its own. `'"a@b"@example.com'` is legal.

    Parameters
    ----------
    address
        The string the caller supplied.

    Raises
    ------
    ValueError
        When the string holds more than one address. Also when its addr-spec has nothing on one side of its last `@`.
    """
    pairs: list[tuple[str, str]] = getaddresses([address])
    if len(pairs) != 1:
        msg = f"{address!r} holds {len(pairs)} addresses; pass one address per argument"
        raise ValueError(msg)

    local, _, domain = pairs[0][1].rpartition("@")
    if not local or not domain:
        msg = f"{address!r} is not an address: it needs something on both sides of its last @"
        raise ValueError(msg)

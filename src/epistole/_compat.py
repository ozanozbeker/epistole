"""`_compat` holds `typing.override`, which the floor Python lacks.

A type checker reads `typing_extensions.override`, and the runtime gets a no-op, so Epistole keeps no runtime dependency. Ruff's UP035 flags the import once the floor Python has `typing.override`, so delete this module and the `typing-modules` entry in `ruff.toml` then.
"""

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from typing_extensions import override
else:
    _F = TypeVar("_F")

    def override(method: _F, /) -> _F:
        """Return `method` unchanged, without the `__override__` attribute that `typing.override` sets."""
        return method

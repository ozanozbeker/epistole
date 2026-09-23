"""Every error a mail service's no becomes: one base and seven classes under it.

The one module in the public surface that `epistole` does not re-export. A caller writes `from epistole.exceptions import ThrottledError`, or `from epistole import exceptions` and then `exceptions.ThrottledError`.

Named for `Exception` rather than for `Error` because `Warning` is an `Exception` too, so a warning Epistole raises later lands here without the module name going wrong. `polars.exceptions`, `numpy.exceptions`, and `sqlalchemy.exc` each hold both; `pandas.errors` is the counterexample.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epistole._backend import Backend
    from epistole._result import Refusal


class EpistoleError(Exception):
    """What a mail service said no with, or what the wire under it failed with.

    A mistake Epistole finds before touching the wire is a `TypeError` or a `ValueError` instead, never one of these: no recipient, a `send` on a closed connection, an address that is not an address.

    The hierarchy is flat. Seven classes sit directly under this one and nothing sits between them, so a caller catches the one it can act on and this base for the rest. The transient set is `(ThrottledError, TransportError, ProviderError)`, written out at the call site rather than expressed as a base class, because the other four are permanent for reasons that do not group.

    Parameters
    ----------
    message
        Positional, so `raise RejectedError("...")` keeps the shape every Python exception has.
    backend
        The route that failed. A raise site leaves it out: a transport receives a submission and nothing else, so it has no backend to name.

    Attributes
    ----------
    backend
        The backend the error came from. `Connection.send` and `Backend.connect` each set it on the way out, so it is `None` only on an error inspected before it has propagated.
    """

    backend: Backend | None

    def __init__(self, message: str, /, *, backend: Backend | None = None) -> None:
        super().__init__(message)
        self.backend = backend

    def __reduce__(self) -> tuple[object, ...]:
        """Rebuild through `_rebuild` when pickled, going around `__init__`.

        `BaseException.__reduce__` answers with `(cls, self.args)`, and `args` holds the message alone. Unpickling therefore calls `cls(message)`, which `RecipientsRefusedError` refuses because `refused` is required. The error then dies on its way home from a worker process, and the caller sees `BrokenProcessPool` instead of the refusal.

        `__cause__`, `__context__`, and `__traceback__` do not survive, exactly as they do not survive pickling any other exception.

        Returns
        -------
        The rebuilder, the class, the positional args, and the attribute state.
        """
        return (_rebuild, (type(self), self.args, self.__dict__))


class RejectedError(EpistoleError):
    """The service refused the message as invalid, or a backend pre-check did.

    Permanent. The two share a class because the same message succeeds on another backend either way, and the caller should see one class whether Epistole or the service noticed first. A pre-check raises with `__cause__` of `None`.
    """


class SenderRefusedError(EpistoleError):
    """The service will not send as the backend's from address.

    Apart from `RejectedError` because the fix is an administrator's grant, not the message.

    RFC 5322 `Sender` names the transmitter, which is a different header and not what this means. The word appears here alone.
    """


class RecipientsRefusedError(EpistoleError):
    """Every recipient was refused, so nothing was submitted.

    `Connection.send` raises it and nothing else does, on every backend including the doubles. A transport answers with refusals and never raises it, so the check is Epistole's own and `__cause__` is `None`.

    Some recipients refused with the rest accepted is not this error. It rides on `SendResult.refused`.

    Parameters
    ----------
    refused
        Keyword-only, and required: the error means nothing without the reasons.

    Attributes
    ----------
    refused
        Each recipient's refusal, keyed by the caller's own recipient string.
    """

    refused: Mapping[str, Refusal]

    def __init__(
        self,
        message: str,
        /,
        *,
        refused: Mapping[str, Refusal],
        backend: Backend | None = None,
    ) -> None:
        super().__init__(message, backend=backend)
        self.refused = refused


class AuthenticationError(EpistoleError):
    """The credential was rejected, or the permission behind it is insufficient.

    Both are permanent until someone changes a setting, which is why an expired token that refreshes cleanly is not an error and a refresh that failed is.
    """


class ThrottledError(EpistoleError):
    """The provider asked for a slower rate.

    Epistole never sleeps and never retries. SMTP never raises it: the protocol cannot tell a throttle from a hiccup.

    Parameters
    ----------
    retry_after
        Seconds, parsed from either RFC 9110 form of the `Retry-After` header.

    Attributes
    ----------
    retry_after
        What the response asked for, or `None` when it carried no header.
    """

    retry_after: float | None

    def __init__(
        self,
        message: str,
        /,
        *,
        retry_after: float | None = None,
        backend: Backend | None = None,
    ) -> None:
        super().__init__(message, backend=backend)
        self.retry_after = retry_after


class TransportError(EpistoleError):
    """The wire failed: connect, TLS, disconnect, or timeout.

    The one error that closes the connection, because the link under it is gone. A client-side timeout is this; a `504` is a status the service returned and so `ProviderError`.
    """


class ProviderError(EpistoleError):
    """The provider's own `5xx`, or a reply the mapper does not know.

    Every mapping table falls back here, so the mapper never raises on its own.
    """


def _rebuild(
    cls: type[EpistoleError],
    args: tuple[object, ...],
    state: dict[str, object],
) -> EpistoleError:
    """Rebuild a pickled error without calling its `__init__`.

    `cls.__new__` allocates, `Exception.__init__` sets `args` so `str()` reads right, and the state carries `backend` plus whatever else the class holds. No constructor runs, so a required keyword-only argument cannot stop the rebuild.

    Returns
    -------
    The error as it was pickled.
    """
    error: EpistoleError = cls.__new__(cls)
    Exception.__init__(error, *args)
    error.__dict__.update(state)
    return error

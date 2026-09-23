"""`epistole` does not re-export `EpistoleError` or its seven subclasses, so a caller imports them from here.

`docs/spec.md` records why the module is named for `Exception` rather than `Error`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epistole._backend import Backend
    from epistole._result import Refusal


class EpistoleError(Exception):
    """An `EpistoleError` reports an error reply from a mail service, or a network failure.

    Epistole raises `TypeError` or `ValueError` instead for a mistake it finds before any network call. A retry loop catches the transient set `(ThrottledError, TransportError, ProviderError)` by name. See ADR-0004.

    Attributes
    ----------
    backend
        The backend the error came from. `Connection.send` and `Backend.connect` set it, so it is `None` only on an error inspected before it propagates.
    """

    backend: Backend | None

    def __init__(self, message: str, /, *, backend: Backend | None = None) -> None:
        super().__init__(message)
        self.backend = backend

    def __reduce__(self) -> tuple[object, ...]:
        """Pickle through `_rebuild`, so unpickling skips `__init__`.

        With the default reduction, unpickling calls `cls(message)`, which raises `TypeError` for `RecipientsRefusedError` because `refused` is required. A process pool would then raise `BrokenProcessPool` instead of the refusal. As with any exception, pickling drops `__cause__`, `__context__` and `__traceback__`.
        """
        return (_rebuild, (type(self), self.args, self.__dict__))


class RejectedError(EpistoleError):
    """The service rejected the message as invalid, or the message failed a backend pre-check.

    The error is permanent. A pre-check raises it with no `__cause__`. See ADR-0004.
    """


class SenderRefusedError(EpistoleError):
    """The service refused to send as the backend's from address.

    The fix is an administrator's grant, not a change to the message. "Sender" here does not mean RFC 5322's `Sender` header.
    """


class RecipientsRefusedError(EpistoleError):
    """The service refused every recipient, so nothing was submitted.

    Only `Connection.send` raises it, so its `__cause__` is `None`. When the service refuses only some recipients, the send returns them in `SendResult.refused` instead.

    Attributes
    ----------
    refused
        Each recipient's refusal, keyed by the caller's recipient string.
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
    """The service rejected the credential, or the credential lacks a permission.

    Both are permanent until someone changes a setting. So an expired token that refreshes cleanly is not an error, and a failed refresh is.
    """


class ThrottledError(EpistoleError):
    """The service throttled the request.

    Epistole never sleeps or retries. The SMTP backend never raises this error. See ADR-0004.

    Attributes
    ----------
    retry_after
        Seconds from the `Retry-After` header in either RFC 9110 form, or `None` when the response had none.
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
    """The link to the service failed at connect, in TLS, by disconnect or by timeout.

    It is the only error that closes the connection. A `504` is a `ProviderError`, because the service returned it. See ADR-0004.
    """


class ProviderError(EpistoleError):
    """The service returned its own `5xx`, or a reply that no mapping table matches.

    See ADR-0004 for the mapping tables.
    """


def _rebuild(
    cls: type[EpistoleError],
    args: tuple[object, ...],
    state: dict[str, object],
) -> EpistoleError:
    """Rebuild a pickled error without calling its `__init__`.

    `Exception.__init__` still runs, to set the `args` that `str()` reads.
    """
    error: EpistoleError = cls.__new__(cls)
    Exception.__init__(error, *args)
    error.__dict__.update(state)
    return error

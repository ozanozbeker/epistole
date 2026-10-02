"""`_GmailTransport` posts each message to the Gmail API, as base64url RFC 5322.

`epistole.gmail` imports this module only after checking the extra, because it imports `httpx2`.
"""

from __future__ import annotations

import base64
import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, override

from epistole import _http
from epistole._rfc5322 import build
from epistole._tokens import REPLY_ERRORS
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RejectedError,
    ThrottledError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx2

    from epistole._backend import Submission
    from epistole._result import Refusal

_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
"""`me` names the mailbox the access token was issued for (ADR-0011)."""

_MAX_BYTES = 36_700_160
"""The v1 discovery document's `maxSize` for `messages.send`: 35 MiB of RFC 5322 message (ADR-0019)."""

_MAX_RECIPIENTS = 500
"""Google's API usage limits page, taken over a Workspace page that says 2,000 (ADR-0019)."""

_THROTTLED = frozenset(
    {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded"}
)
"""The `errors[].reason` values that make a `403` a `ThrottledError` (ADR-0004)."""


class _GmailTransport(_http.RESTTransport):
    """`GmailBackend` opens this transport."""

    vendor = "Google"
    purpose = "gmail"

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Post the RFC 5322 message as base64url `raw`."""
        recipients: int = len(submission.message.recipients)
        if recipients > _MAX_RECIPIENTS:
            msg = f"the message has {recipients} recipients, and Gmail accepts at most {_MAX_RECIPIENTS}."
            raise RejectedError(msg)

        data: bytes = build(submission).as_bytes()
        if len(data) > _MAX_BYTES:
            msg = f"the message is {len(data):,} bytes once encoded, and Gmail accepts at most {_MAX_BYTES:,}."
            raise RejectedError(msg)

        raw: str = base64.urlsafe_b64encode(data).decode("ascii")
        self.request("POST", _SEND, content=json.dumps({"raw": raw}).encode())
        return {}

    @staticmethod
    @override
    def _mapped(response: httpx2.Response) -> EpistoleError:
        """Return the Epistole error for a status outside 2xx, preferring a row qualified by a reason in any entry of `errors[]` (ADR-0004)."""
        status: int = response.status_code
        reasons, detail = _envelope(response)
        label: str = " ".join([str(status), *reasons])
        msg = f"Gmail replied {label}: {detail}"
        if status == HTTPStatus.TOO_MANY_REQUESTS or (
            status == HTTPStatus.FORBIDDEN and not _THROTTLED.isdisjoint(reasons)
        ):
            return ThrottledError(msg, retry_after=_http.retry_after(response))

        if status in {HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND} or (
            status == HTTPStatus.FORBIDDEN and "domainPolicy" in reasons
        ):
            return RejectedError(msg)

        if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
            return AuthenticationError(msg)

        return ProviderError(msg)


def _envelope(response: httpx2.Response) -> tuple[list[str], str]:
    """Return the reason of each entry in `errors[]` that has one, and the `message` of Google's error envelope."""
    try:
        error: dict[str, Any] = response.json()["error"]
        errors: list[dict[str, Any]] = error.get("errors") or []
        reasons = [
            str(one["reason"])
            for one in errors
            if isinstance(one, dict) and one.get("reason")
        ]
        return reasons, str(error.get("message", ""))
    except REPLY_ERRORS:
        return [], response.reason_phrase

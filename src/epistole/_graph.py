"""`_GraphTransport` posts each message to Microsoft Graph as JSON.

`epistole.graph` imports this module only after checking the extra, because it imports `httpx2`.
"""

from __future__ import annotations

import base64
import json
from contextlib import suppress
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, override
from urllib.parse import quote

from epistole import _http
from epistole._address import addr_spec, name_and_addr_spec
from epistole._tokens import REPLY_ERRORS
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RejectedError,
    SenderRefusedError,
    ThrottledError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx2

    from epistole._backend import Submission
    from epistole._message import Attachment, Message
    from epistole._result import Refusal

_USERS = "https://graph.microsoft.com/v1.0/users/"
"""Every request names the mailbox, because `/me` needs a signed-in user and an app-only token has none (ADR-0012)."""

_MAX_REQUEST = 4_000_000
"""Graph caps a write request at 4 MB without defining the unit, so this takes the smaller, decimal reading (ADR-0012)."""

_MIN_UPLOAD = 3_000_000
"""An upload session takes an attachment of this many raw bytes or more, and one `POST` takes a smaller one. It reads Graph's unitless 3 MB as decimal (ADR-0012)."""

_CHUNK = 3_000_000
"""Each upload `PUT` sends at most this many bytes, under the 4 MB per byte range that Graph recommends (ADR-0012)."""

_MAX_ATTACHMENT = 150_000_000
"""Graph caps one attachment at this many raw bytes (ADR-0019)."""


class _GraphTransport(_http.RESTTransport):
    """`GraphBackend` opens this transport."""

    vendor = "Microsoft"
    purpose = "graph"

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Post the message as one `sendMail` JSON body, or through a draft when that body is too large (ADR-0012)."""
        message: Message = submission.message
        for name in message.headers_:
            if not name.lower().startswith("x-"):
                msg = f"Graph sends only custom headers whose names start with x-, so it cannot send {name!r}."
                raise RejectedError(msg)

        attachments: tuple[Attachment, ...] = (
            *message.attachments,
            *message.inline_images,
        )
        for attachment in attachments:
            if len(attachment.data) > _MAX_ATTACHMENT:
                msg = f"{attachment.filename!r} is {len(attachment.data):,} bytes, and Graph accepts at most {_MAX_ATTACHMENT:,} per attachment."
                raise RejectedError(msg)

        fields: dict[str, object] = _message(submission)
        request: bytes = _json({"message": fields})
        mailbox: str = f"{_USERS}{quote(addr_spec(submission.from_address), safe='@')}"
        if len(request) < _MAX_REQUEST:
            self.request("POST", f"{mailbox}/sendMail", content=request)
        else:
            fields.pop("attachments", None)
            self._send_draft(mailbox, fields, attachments)

        return {}

    def _send_draft(
        self,
        mailbox: str,
        fields: dict[str, object],
        attachments: tuple[Attachment, ...],
    ) -> None:
        """Create a draft without attachments, add each attachment by its own call, and send the draft."""
        created: httpx2.Response = self.request(
            "POST", f"{mailbox}/messages", content=_json(fields)
        )
        draft: str = f"{mailbox}/messages/{_read(created, 'id')}"
        try:
            for attachment in attachments:
                if len(attachment.data) < _MIN_UPLOAD:
                    self.request(
                        "POST",
                        f"{draft}/attachments",
                        content=_json(_attachment(attachment)),
                    )
                    continue

                session: httpx2.Response = self.request(
                    "POST",
                    f"{draft}/attachments/createUploadSession",
                    content=_json({"AttachmentItem": _item(attachment)}),
                )
                self._upload(_read(session, "uploadUrl"), attachment.data)

            self.request("POST", f"{draft}/send")
        except BaseException:
            # BaseException, so an interrupt does not leave the draft in the mailbox either (ADR-0012).
            with suppress(Exception):
                self.request("DELETE", draft)

            raise

    def _upload(self, url: str, data: bytes) -> None:
        """PUT `data` to an upload session in sequential chunks, and delete the session if one fails.

        No request carries the bearer, because the URL holds its own token on another host (ADR-0009).
        """
        try:
            with self.mapping():
                for start in range(0, len(data), _CHUNK):
                    chunk: bytes = data[start : start + _CHUNK]
                    self._client.put(
                        url,
                        content=chunk,
                        headers={
                            "Content-Type": "application/octet-stream",
                            "Content-Range": f"bytes {start}-{start + len(chunk) - 1}/{len(data)}",
                        },
                    ).raise_for_status()
        except BaseException:
            with suppress(Exception):
                self._client.delete(url)

            raise

    @staticmethod
    @override
    def _mapped(response: httpx2.Response) -> EpistoleError:
        """Return the Epistole error for a status outside 2xx, preferring a row qualified by `error.code` (ADR-0004)."""
        status: int = response.status_code
        code, detail = _envelope(response)
        label: str = f"{status} {code}" if code else str(status)
        msg = f"Graph replied {label}: {detail}"
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            return ThrottledError(msg, retry_after=_http.retry_after(response))

        if status == HTTPStatus.FORBIDDEN and code == "ErrorSendAsDenied":
            return SenderRefusedError(msg)

        if status in {
            HTTPStatus.BAD_REQUEST,
            HTTPStatus.NOT_FOUND,
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
        }:
            return RejectedError(msg)

        if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
            return AuthenticationError(msg)

        return ProviderError(msg)


def _envelope(response: httpx2.Response) -> tuple[str, str]:
    """Return the `code` and the `message` of Graph's error envelope."""
    try:
        error: dict[str, Any] = response.json()["error"]
        return str(error.get("code", "")), str(error.get("message", ""))
    except REPLY_ERRORS:
        return "", response.reason_phrase


def _read(response: httpx2.Response, name: str) -> str:
    """Return the field `name` of a Graph reply, raising `ProviderError` unless it is a non-empty string."""
    try:
        value: object = response.json()[name]
    except REPLY_ERRORS as error:
        msg = f"Graph's reply holds no {name}."
        raise ProviderError(msg) from error

    if not isinstance(value, str) or not value:
        msg = f"Graph's reply holds {value!r} as its {name}, not a non-empty string."
        raise ProviderError(msg)

    return value


def _json(value: object) -> bytes:
    """Serialize `value` as compact UTF-8 JSON, the bytes the `sendMail` size check measures."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _message(submission: Submission) -> dict[str, object]:
    """Return Graph's JSON `message` for `submission`, without the fields it leaves empty."""
    message: Message = submission.message
    # A body has one contentType, so Exchange derives its own plain text beside HTML (ADR-0012).
    body: dict[str, str] = (
        {"contentType": "text", "content": message.text}
        if message.html is None
        else {"contentType": "html", "content": message.html}
    )
    fields: dict[str, object] = {
        "from": _recipient(submission.from_address),
        "toRecipients": [_recipient(one) for one in message.to_],
        "ccRecipients": [_recipient(one) for one in message.cc_],
        "bccRecipients": [_recipient(one) for one in message.bcc_],
        "replyTo": [_recipient(one) for one in message.reply_to_],
        "subject": message.subject_,
        "body": body,
        "internetMessageId": submission.message_id,
        "internetMessageHeaders": [
            {"name": name, "value": value} for name, value in message.headers_.items()
        ],
        "attachments": [
            _attachment(one) for one in (*message.attachments, *message.inline_images)
        ],
    }
    return {name: value for name, value in fields.items() if value}


def _recipient(address: str) -> dict[str, dict[str, str]]:
    """Return Graph's `recipient` for `address`, with its display name when it has one."""
    name, spec = name_and_addr_spec(address)
    return {
        "emailAddress": {"address": spec, "name": name} if name else {"address": spec}
    }


def _attachment(attachment: Attachment) -> dict[str, object]:
    """Return Graph's `fileAttachment` for `attachment`, marked inline under its bare content id when it is an inline image."""
    fields: dict[str, object] = {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": attachment.filename,
        "contentType": attachment.content_type,
        "contentBytes": base64.b64encode(attachment.data).decode("ascii"),
    }
    if attachment.content_id is not None:
        fields |= {"isInline": True, "contentId": attachment.content_id}

    return fields


def _item(attachment: Attachment) -> dict[str, object]:
    """Return Graph's `attachmentItem` for an upload session, marked inline as `_attachment` marks it."""
    fields: dict[str, object] = {
        "attachmentType": "file",
        "name": attachment.filename,
        "size": len(attachment.data),
        "contentType": attachment.content_type,
    }
    if attachment.content_id is not None:
        fields |= {"isInline": True, "contentId": attachment.content_id}

    return fields

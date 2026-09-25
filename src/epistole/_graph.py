"""`_GraphTransport` posts each message to Microsoft Graph as JSON, and `_HttpClient` sends `msal`'s token requests on the connection's client.

`epistole.graph` imports this module only after checking the extra, because it imports `httpx2` and `msal`.
"""

from __future__ import annotations

import base64
import json
from contextlib import ExitStack, contextmanager, suppress
from functools import partial
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx2
import msal
from msal.exceptions import MsalServiceError

from epistole import _http
from epistole._address import addr_spec, name_and_addr_spec
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RejectedError,
    SenderRefusedError,
    ThrottledError,
    TransportError,
)
from epistole.graph import Certificate, ClientSecret, ManagedIdentity

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

    from epistole._backend import Submission, TokenCredential
    from epistole._message import Attachment, Message
    from epistole._result import Refusal

_AUDIENCE = "https://graph.microsoft.com"
"""`msal`'s managed identity client takes the audience bare, as a resource, because it accepts no scope (ADR-0011)."""

_SCOPE = f"{_AUDIENCE}/.default"
"""`msal`'s confidential client and a `TokenCredential` take the audience as this scope (ADR-0011)."""

_USERS = f"{_AUDIENCE}/v1.0/users/"
"""Every request names the mailbox, because `/me` needs a signed-in user and an app-only token has none (ADR-0012)."""

_MAX_REQUEST = 4_000_000
"""Graph caps a write request at 4 MB without defining the unit, so this takes the smaller, decimal reading (ADR-0012)."""

_MIN_UPLOAD = 3_000_000
"""An upload session takes an attachment of this many raw bytes or more, and one `POST` takes a smaller one. It reads Graph's unitless 3 MB as decimal (ADR-0012)."""

_CHUNK = 3_000_000
"""Each upload `PUT` sends at most this many bytes, under the 4 MB per byte range that Graph recommends (ADR-0012)."""

_MAX_ATTACHMENT = 150_000_000
"""Graph caps one attachment at this many raw bytes (ADR-0019)."""

_MAX_RECIPIENTS = 500
"""Exchange Online's cap across to, cc and bcc, from Graph's `message` resource page (ADR-0019)."""


def connect(
    credential: ClientSecret | Certificate | ManagedIdentity | TokenCredential,
) -> _GraphTransport:
    """Build the client and the tokens, and get the first token."""
    client: httpx2.Client = _http.client()
    with ExitStack() as on_failure:
        on_failure.callback(client.close)
        # msal fetches the tenant's OpenID configuration when it builds a confidential client.
        with _mapping():
            tokens: _http.Tokens = _tokens(credential, client)
            tokens.token()

        on_failure.pop_all()

    return _GraphTransport(client, tokens)


def _tokens(
    credential: ClientSecret | Certificate | ManagedIdentity | TokenCredential,
    client: httpx2.Client,
) -> _http.Tokens:
    """Build the tokens for `credential`, in the spelling of the audience its `msal` client takes (ADR-0011)."""
    cache = msal.TokenCache()
    match credential:
        case ManagedIdentity(client_id=client_id):
            identity = (
                msal.SystemAssignedManagedIdentity()
                if client_id is None
                else msal.UserAssignedManagedIdentity(client_id=client_id)
            )
            managed = msal.ManagedIdentityClient(
                identity, http_client=_HttpClient(client), token_cache=cache
            )
            return _MsalTokens(
                partial(managed.acquire_token_for_client, resource=_AUDIENCE), cache
            )
        case ClientSecret() | Certificate():
            app = msal.ConfidentialClientApplication(
                credential.client_id,
                client_credential=_client_credential(credential),
                authority=f"https://login.microsoftonline.com/{credential.tenant_id}",
                http_client=_HttpClient(client),
                token_cache=cache,
                # Otherwise msal fetches the host's aliases after a rejection, to find a refresh token a client credential never has.
                instance_discovery=False,
            )
            return _MsalTokens(partial(app.acquire_token_for_client, [_SCOPE]), cache)
        case _:
            return _http.ForeignTokens(credential, _SCOPE)


def _client_credential(
    credential: ClientSecret | Certificate,
) -> str | dict[str, object]:
    """Return `credential` in the `client_credential` shape `ConfidentialClientApplication` takes."""
    match credential:
        case ClientSecret(client_secret=secret):
            return secret
        case Certificate(pfx=None, private_key=key, thumbprint=thumbprint):
            return {"private_key": key, "thumbprint": thumbprint}
        case Certificate(pfx=pfx, passphrase=passphrase):
            return {"private_key_pfx_path": pfx, "passphrase": passphrase}


class _GraphTransport:
    """`GraphBackend` opens this transport, which holds the connection's client and tokens."""

    def __init__(self, client: httpx2.Client, tokens: _http.Tokens, /) -> None:
        self._client = client
        self._tokens = tokens

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        """Post the message as one `sendMail` JSON body, or through a draft when that body is too large (ADR-0012)."""
        message: Message = submission.message
        recipients: int = len(message.recipients)
        if recipients > _MAX_RECIPIENTS:
            msg = f"the message has {recipients} recipients, and Graph accepts at most {_MAX_RECIPIENTS}."
            raise RejectedError(msg)

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
        with _mapping():
            if len(request) < _MAX_REQUEST:
                self._request("POST", f"{mailbox}/sendMail", request)
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
        created: httpx2.Response = self._request(
            "POST", f"{mailbox}/messages", _json(fields)
        )
        draft: str = f"{mailbox}/messages/{_read(created, 'id')}"
        try:
            for attachment in attachments:
                if len(attachment.data) < _MIN_UPLOAD:
                    self._request(
                        "POST", f"{draft}/attachments", _json(_attachment(attachment))
                    )
                    continue

                session: httpx2.Response = self._request(
                    "POST",
                    f"{draft}/attachments/createUploadSession",
                    _json({"AttachmentItem": _item(attachment)}),
                )
                self._upload(_read(session, "uploadUrl"), attachment.data)

            self._request("POST", f"{draft}/send")
        except BaseException:
            # BaseException, so an interrupt does not leave the draft in the mailbox either (ADR-0012).
            with suppress(Exception):
                self._request("DELETE", draft)

            raise

    def _upload(self, url: str, data: bytes) -> None:
        """PUT `data` to an upload session in sequential chunks, and delete the session if one fails.

        No request carries the bearer, because the URL holds its own token on another host (ADR-0009).
        """
        try:
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

    def _request(
        self, method: str, url: str, content: bytes | None = None
    ) -> httpx2.Response:
        """Send one request with the bearer, under `_http.request`'s `401` retry."""
        return _http.request(self._client, self._tokens, method, url, content=content)

    def close(self) -> None:
        """Close the client."""
        self._client.close()


@contextmanager
def _mapping() -> Generator[None]:
    """Raise the Epistole error for a native failure, by the Graph mapping in ADR-0004."""
    try:
        yield
    except httpx2.HTTPStatusError as error:
        raise _mapped(error.response) from error
    except httpx2.TransportError as error:
        msg = f"the request to Microsoft failed: {error}"
        raise TransportError(msg) from error
    except httpx2.HTTPError as error:
        msg = f"Microsoft's reply could not be read: {error}"
        raise ProviderError(msg) from error
    except MsalServiceError as error:
        # msal raises this for a 5xx from Entra, where it returns a dict for a rejected credential.
        msg = f"Entra failed: {error}"
        raise ProviderError(msg) from error
    except json.JSONDecodeError as error:
        msg = f"the token reply is not JSON: {error}"
        raise ProviderError(msg) from error


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
    except (ValueError, LookupError, TypeError, AttributeError):
        return "", response.reason_phrase


def _read(response: httpx2.Response, name: str) -> str:
    """Return the field `name` of a Graph reply, raising `ProviderError` when the reply lacks it."""
    try:
        return response.json()[name]
    except (ValueError, LookupError, TypeError) as error:
        msg = f"Graph's reply holds no {name}."
        raise ProviderError(msg) from error


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


class _MsalTokens:
    """The tokens of an `msal` client, which caches them in `cache`."""

    def __init__(
        self, acquire: Callable[[], dict[str, Any]], cache: msal.TokenCache, /
    ) -> None:
        self._acquire = acquire
        self._cache = cache

    def token(self) -> str:
        """Return the cached token, or a new one once the cached one is within five minutes of expiry."""
        result: dict[str, Any] = self._acquire()
        if "access_token" not in result:
            # msal returns its error rather than raising it, so the error has no __cause__ (ADR-0009).
            msg = f"the credential could not get an access token: {result.get('error')}: {result.get('error_description')}"
            raise AuthenticationError(msg)

        return result["access_token"]

    def refresh(self) -> str:
        """Drop the cached tokens and return a new one, because `acquire_token_for_client` takes no `force_refresh`."""
        for entry in list(
            self._cache.search(msal.TokenCache.CredentialType.ACCESS_TOKEN)
        ):
            self._cache.remove_at(entry)

        return self.token()


class _HttpClient:
    """The `http_client` that `msal` takes.

    It sends `msal`'s token requests on the connection's client, so they share its timeout, proxy and CA (ADR-0009).
    """

    def __init__(self, client: httpx2.Client, /) -> None:
        self._client = client

    def get(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **_: object,
    ) -> httpx2.Response:
        """Ignore `timeout` and any other keyword, because the client's 60 seconds covers token requests too (ADR-0009)."""
        return self._client.get(url, params=params, headers=headers)

    def post(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **_: object,
    ) -> httpx2.Response:
        """Ignore any other keyword, as `get` does."""
        return self._client.post(url, params=params, data=data, headers=headers)

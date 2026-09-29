"""`_GraphTransport` posts each message to Microsoft Graph as JSON, and `_HttpClient` sends `msal`'s token requests on the connection's client.

`epistole.graph` imports this module only after checking the extra, because it imports `httpx2` and `msal`.
"""

from __future__ import annotations

import base64
import json
from contextlib import ExitStack, contextmanager, suppress
from functools import partial
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, override
from urllib.parse import quote

import httpx2
import msal

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
"""Graph's audience, which `_tokens` requests as a resource or as a scope by the credential's type (ADR-0011)."""

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
            tokens: _http.Tokens = _tokens(credential, client, _AUDIENCE)
            tokens.token()

        on_failure.pop_all()

    return _GraphTransport(client, tokens)


def token(
    credential: ClientSecret | Certificate | ManagedIdentity, audience: str
) -> str:
    """Return one access token for `audience`.

    SMTP sends a token once in `AUTH`, so the client closes before this returns.
    """
    with _http.client() as client, _mapping():
        return _tokens(credential, client, audience).token()


def _tokens(
    credential: ClientSecret | Certificate | ManagedIdentity | TokenCredential,
    client: httpx2.Client,
    audience: str,
) -> _http.Tokens:
    """Build the tokens for `credential`, in the spelling of `audience` its `msal` client takes (ADR-0011)."""
    cache = msal.TokenCache()
    http_client = _HttpClient(client)
    scope = f"{audience}/.default"
    match credential:
        case ManagedIdentity(client_id=client_id):
            identity = (
                msal.SystemAssignedManagedIdentity()
                if client_id is None
                else msal.UserAssignedManagedIdentity(client_id=client_id)
            )
            managed = msal.ManagedIdentityClient(
                identity,
                http_client=http_client,
                token_cache=cache,
                http_cache=_NoCache(),
            )
            return _MsalTokens(
                partial(managed.acquire_token_for_client, resource=audience),
                cache,
                http_client,
            )
        case ClientSecret() | Certificate():
            app = msal.ConfidentialClientApplication(
                credential.client_id,
                client_credential=_client_credential(credential),
                authority=f"https://login.microsoftonline.com/{credential.tenant_id}",
                http_client=http_client,
                token_cache=cache,
                http_cache=_NoCache(),
                # Otherwise msal fetches the host's aliases after a rejection, to find a refresh token a client credential never has.
                instance_discovery=False,
            )
            return _MsalTokens(
                partial(app.acquire_token_for_client, [scope]), cache, http_client
            )
        case _:
            return _http.ForeignTokens(credential, scope)


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
    except _TokenStatusError as error:
        raise _token_mapped(error.response) from error
    except httpx2.HTTPStatusError as error:
        raise _mapped(error.response) from error
    except httpx2.TransportError as error:
        msg = f"the request to Microsoft failed: {error}"
        raise TransportError(msg) from error
    except httpx2.HTTPError as error:
        msg = f"Microsoft's reply could not be read: {error}"
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


def _token_mapped(response: httpx2.Response) -> ProviderError:
    """Return the `ProviderError` for a token reply `msal` never read, naming its status and its RFC 6749 error (ADR-0009)."""
    status: int = response.status_code
    error, description = _http.oauth_error(response)
    label: str = f"{status} {error}" if error else str(status)
    msg = f"Microsoft replied {label} to a token request: {description}"
    return ProviderError(msg)


def _envelope(response: httpx2.Response) -> tuple[str, str]:
    """Return the `code` and the `message` of Graph's error envelope."""
    try:
        error: dict[str, Any] = response.json()["error"]
        return str(error.get("code", "")), str(error.get("message", ""))
    except _http.REPLY_ERRORS:
        return "", response.reason_phrase


def _read(response: httpx2.Response, name: str) -> str:
    """Return the field `name` of a Graph reply, raising `ProviderError` unless it is a non-empty string."""
    try:
        value: object = response.json()[name]
    except _http.REPLY_ERRORS as error:
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


class _MsalTokens:
    """The tokens of an `msal` client, which caches them in `cache`."""

    def __init__(
        self,
        acquire: Callable[[], dict[str, Any]],
        cache: msal.TokenCache,
        http_client: _HttpClient,
        /,
    ) -> None:
        self._acquire = acquire
        self._cache = cache
        self._http_client = http_client

    def token(self) -> str:
        """Return the cached token, or a new one once the cached one is within five minutes of expiry."""
        replies: int = self._http_client.replies
        try:
            result: dict[str, Any] = self._acquire()
        except _http.REPLY_ERRORS as error:
            # With no new reply, these come from the caller's key rather than from msal reading a reply (ADR-0009).
            if self._http_client.replies == replies:
                raise

            msg = f"Microsoft's token reply could not be read: {error}"
            raise ProviderError(msg) from error

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
        self.replies = 0
        """How many replies this adapter has returned to `msal`."""

    def get(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **_: object,
    ) -> httpx2.Response:
        """Ignore `timeout` and any other keyword, because the client's 60 seconds covers token requests too (ADR-0009)."""
        return self._to_msal(self._client.get(url, params=params, headers=headers))

    def post(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        **_: object,
    ) -> httpx2.Response:
        """Ignore any other keyword, as `get` does."""
        return self._to_msal(
            self._client.post(url, params=params, data=data, headers=headers)
        )

    def _to_msal(self, response: httpx2.Response) -> httpx2.Response:
        """Count `response` and return it to `msal`, or raise `_TokenStatusError` for a status outside 2xx that does not reject the credential (ADR-0009)."""
        if (
            not response.is_success
            and response.status_code not in _http.CREDENTIAL_REJECTED
        ):
            msg = f"Microsoft replied {response.status_code} to a token request"
            raise _TokenStatusError(msg, request=response.request, response=response)

        self.replies += 1
        return response


class _TokenStatusError(httpx2.HTTPStatusError):
    """`_HttpClient` raises this for a token reply, so `_mapping` maps it by the token table and never by the mail endpoint's (ADR-0009)."""


class _NoCache(dict[str, object]):
    """An `http_cache` for `msal` that keeps nothing, so `msal` sends every token request (ADR-0009)."""

    @override
    def __setitem__(self, key: str, value: object, /) -> None:
        pass

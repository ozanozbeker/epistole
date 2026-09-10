# Epistole v1 API specification

The public surface, the backend protocol, and the error model of `epistole` v1, stated once in the order an implementer meets them.
Decided on [#29](https://github.com/ozanozbeker/epistole/issues/29), closing [#2](https://github.com/ozanozbeker/epistole/issues/2).

## Reading this spec

- This file is authoritative for the surface.
  Every rule here cites the ADR that decided it, and a rule with no ADR behind it is a defect in this file.
  Where this file and an ADR disagree, build this file and fix the ADR, or overturn it with a new one.
- ADRs hold the why and the rejected alternatives.
  An ADR is live unless its opening paragraph says `Amended on` or names what reversed it.
  There is no status field.
- `CONTEXT.md` is the glossary.
  A name here means what the glossary says it means.
- Signatures are the contract; docstrings are not written here.
  Rule bullets under a block carry what a signature cannot say.
- `docs/research/*.md` holds the measurements the ADRs cite.

## Modules and exports

```python
# epistole
__all__ = [
    "Address",
    "Attachment",
    "AuthenticationError",
    "Backend",
    "Connection",
    "ConsoleBackend",
    "EpistoleError",
    "GmailBackend",
    "GraphBackend",
    "MemoryBackend",
    "Message",
    "ProviderError",
    "RecipientsRefusedError",
    "Refusal",
    "RejectedError",
    "SMTPBackend",
    "SendResult",
    "SenderRefusedError",
    "Submission",
    "ThrottledError",
    "Transport",
    "TransportError",
    "html_to_text",
]
```

- Credential values live in the module of the backend that issues their tokens: `epistole.smtp`, `epistole.gmail`, `epistole.graph` (ADR-0011).
  The backend classes are defined there too and re-exported from `epistole`.
- `SMTPTransport`, `GmailTransport`, `GraphTransport`, and the doubles' transports are not exported (ADR-0006).
- `from epistole import GmailBackend` and `GraphBackend` always succeed; the vendor imports happen in the constructor (ADR-0009).
- The core has no runtime dependency (ADR-0008, ADR-0009).
  Extras: `gmail` = `google-auth`, `httpx2`; `graph` = `msal`, `httpx2`; `markdown` = `markdown-it-py`; `all` = the three.
- `httpx2` is never re-exported and never appears in a signature (ADR-0009).

## Message and Address

```python
class Address(str):
    def __new__(cls, name: str, email: str) -> Address: ...
```

- Returns `email.utils.formataddr((name, email))`, so `Address("Ada Lovelace", "ada@example.com") == "Ada Lovelace <ada@example.com>"` (ADR-0014).
- Raises `ValueError` with the `UnicodeEncodeError` as `__cause__` when `email` is not ASCII, because `formataddr` cannot format it (ADR-0014).
  The plain-string path accepts the same address.

```python
class Message:
    def __init__(
        self,
        *,
        html: str | None = None,
        markdown: str | None = None,
        text: str | None = None,
        text_renderer: Callable[[str], str] | None = None,
    ) -> None: ...

    # builder methods; each returns a new Message
    def to(self, address: str, /, *more: str) -> Message: ...
    def cc(self, address: str, /, *more: str) -> Message: ...
    def bcc(self, address: str, /, *more: str) -> Message: ...
    def reply_to(self, address: str, /, *more: str) -> Message: ...
    def subject(self, subject: str, /) -> Message: ...
    def headers(self, mapping: Mapping[str, str], /) -> Message: ...
    def attach(
        self,
        source: Path | bytes | BinaryIO,
        /,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> Message: ...
    def embed(
        self,
        source: Path | bytes | BinaryIO,
        /,
        *,
        filename: str | None = None,
        cid: str | None = None,
        content_type: str | None = None,
    ) -> Message: ...

    # readbacks
    to_: tuple[str, ...]
    cc_: tuple[str, ...]
    bcc_: tuple[str, ...]
    reply_to_: tuple[str, ...]
    subject_: str | None
    headers_: Mapping[str, str]
    recipients: tuple[str, ...]
    html: str | None
    text: str
    attachments: tuple[Attachment, ...]
    inline_images: tuple[Attachment, ...]


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    data: bytes
    content_id: str | None
```

**Value semantics (ADR-0002).**

- Frozen, equal by content, hashable.
  Every builder method returns a new message; the receiver is unchanged.
- A field-named method replaces: `.to("a").to("b")` sends to `b`.
  `.attach()` and `.embed()` append: `.attach(x).attach(x)` sends `x` twice.
- Nothing removes.
  Address methods take at least one address, so `.to(*[])` is a `TypeError` at the call site.
  `.headers({})` is a `ValueError` (ADR-0016).
- Attachment bytes are read when `.attach()` or `.embed()` is called.
  A file object is read and left open.
- `Message-ID` and `Date` are never on the message (ADR-0002, ADR-0015).

**Content (ADR-0008).**

- Exactly one of `html=` or `markdown=`, or neither with `text=` alone.
  Both, or none of the three, is a `TypeError`.
- `text=` ships verbatim and is never derived or merged.
  `text=""` is a `ValueError`.
- HTML with no `text=`: `text` is `text_renderer(rewritten_html)` when given, else `html_to_text(rewritten_html)`.
  The renderer runs once at construction on the HTML after the `data:` rewrite, is not stored, and its exceptions propagate unwrapped.
  A return that is not a non-empty `str` is a `ValueError`.
- `text_renderer=` with `text=` or with `markdown=` is a `TypeError`.
- `markdown=` renders through `markdown-it-py`, `commonmark` preset, no options; the source is `text`.
  Missing extra raises `ImportError` naming `epistole[markdown]`.
- `text=` alone ships `text/plain` alone; `html` is `None`.

**The `data:` rewrite (ADR-0003).**

- Every `<img>` whose `src` is a `data:` URI with an `image/*` media type, base64 or percent-encoded, becomes an inline image at construction.
  No flag.
- The HTML is byte-identical except the rewritten `src` values.
  `<img>` inside comments, `data:` in CSS `url()`, `srcset`, and non-image media types stay as written.
- One inline image per distinct (media type, bytes).
  Content id is the first 16 hex characters of the SHA-256 of the bytes plus `mimetypes.guess_extension`'s extension, no `@domain`; the same string is the filename.
- A payload that does not decode raises `ValueError` at construction.
- Rewrite runs before the plain-text renderer.

**Attachments and inline images (#11, ADR-0003).**

- `source` is `Path`, `bytes`, or a binary file object with `.read()`.
  `str` is a `TypeError` that says to wrap it in `Path()`; `bytearray`, `memoryview`, and a text-mode file raise `TypeError`.
- A `Path` names itself.
  Every other source needs `filename=`; `.name` on a file object is not read.
- `content_type` is inferred from the filename, falls back to `application/octet-stream`, and is always explicit on the wire.
  `content_type=` overrides; no parameters; bytes are never sniffed.
- `.embed()`: `filename` and `cid` default to each other, so `.embed(Path("logo.png"))` answers `<img src="cid:logo.png">`.
  The content type must be `image/*` after inference or override, else `ValueError`.
- `attachments` holds what `.attach()` added, `inline_images` what `.embed()` added and what the rewrite made, each in insertion order.
  `content_id` is `None` on an attachment and set on an inline image.
  Neither name takes ADR-0007's underscore, because no method claims it (#29).

**Addresses (ADR-0014).**

- Checked where supplied, in the four address methods and in `from_address`, as `ValueError`.
  A string passes when `email.utils.getaddresses` returns exactly one pair, the addr-spec is non-empty, and both halves of its last `@` are non-empty.
  Nothing else is inspected: no character set, no DNS, no punycode.
- `recipients` is `to_ + cc_ + bcc_` in that order, duplicates kept (ADR-0007).

**Custom headers (ADR-0016).**

- `.headers(mapping)` replaces the whole set with a copy; `headers_` reads it back in the given order as a read-only mapping holding the caller's headers alone.
- A legal name is one or more characters in printable ASCII 33 to 126 excluding `:`.
  A legal value is a `str` with no `\r` and no `\n`.
  Anything else is a `ValueError`, checked in `Message`.
- A name Epistole owns is a `ValueError`, matched case-insensitively on the exact name: `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject`, `Message-ID`, `Date`, `MIME-Version`, `Content-Type`, `Content-Transfer-Encoding`, `Content-ID`, `Content-Disposition`.

**Readbacks (ADR-0007).**

- A builder method's value reads back as the method name plus a trailing underscore.
  `recipients`, `html`, `text`, `attachments`, and `inline_images` carry no underscore because no method claims those names (ADR-0007, ADR-0008, #29).

**What Epistole never does to HTML (ADR-0013).**

- No CSS rewrite, no size warning, no `html_renderer=`.
  The `<img src>` rewrite above is the only edit.

## Backend, Connection, Transport, Submission

```python
class Backend(ABC):
    from_address: str

    def send(self, message: Message, /) -> SendResult: ...
    def connect(self) -> Connection: ...

    @abstractmethod
    def _open(self) -> Transport: ...


class Connection:
    backend: Backend

    def send(self, message: Message, /) -> SendResult: ...
    def close(self) -> None: ...
    def __enter__(self) -> Connection: ...
    def __exit__(self, *exc_info: object) -> None: ...


class Transport(Protocol):
    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class Submission:
    message: Message
    from_address: str
    message_id: str
    date: datetime
```

**Backend (ADR-0001, ADR-0005, ADR-0006).**

- Immutable configuration, safe to share across threads.
  Not a context manager: `with backend:` is a `TypeError`.
- `from_address` is required on every real backend, checked at construction per ADR-0014, and there is no per-send override.
- `Backend.send(message)` is `with self.connect() as c: return c.send(message)`, written once on the base.
- `_open()` is the only abstract method; nothing else will become abstract.

**Connection (ADR-0005, ADR-0006, ADR-0015).**

- `connect()` takes no arguments and opens eagerly: socket, TLS, and AUTH on SMTP; one `httpx2.Client` and a token on Gmail and Graph; nothing on the doubles.
  `AuthenticationError` and `TransportError` surface on the `connect()` line.
- One link, used once, one thread.
  `send` or `__enter__` after `close()` is a `ValueError`.
  `__enter__` returns `self` and does nothing else.
- `close()` is idempotent and never raises; `__exit__` calls it and never suppresses.
- `TransportError` closes the connection.
  Every other `EpistoleError` leaves it open.
- `Connection.send`, in order: raise `ValueError` if closed; check completeness (at least one recipient; every `cid:` the HTML names matched by an inline image) and raise `ValueError` if not; build a `Submission` stamping `message_id` and `date`; call `transport.submit`; raise `RecipientsRefusedError` if every recipient was refused; return `SendResult(message_id, date, refused)`.
- No lock, no pool, no `begin()`, no `dispose()`.

**Transport (ADR-0006, ADR-0015).**

- The whole of what a third-party backend writes.
  `submit` returns the refusals the service gave, empty when none; it never constructs a `SendResult`.
- A transport that cannot carry part of a message raises `RejectedError` with `__cause__` `None` before writing (ADR-0010).
- `submit` maps the native failure onto one `EpistoleError` leaf per the tables below, raised with `from`.

**Submission (ADR-0015).**

- Built by `Connection.send` and by nothing else.
  Sending one message twice makes two submissions with two ids.
- `date` is timezone-aware.

## Concrete backends

```python
# epistole.smtp
class SMTPBackend(Backend):
    def __init__(
        self,
        host: str,
        *,
        port: int = 587,
        security: Literal["starttls", "tls", "none"] = "starttls",
        from_address: str,
        credential: Password | OAuth | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class Password:
    username: str
    password: str


@dataclass(frozen=True)
class OAuth:
    username: str
    credential: (
        graph.ClientSecret
        | graph.Certificate
        | graph.ManagedIdentity
        | gmail.ServiceAccount
        | gmail.AuthorizedUser
        | TokenCredential
    )
    scope: str | None = None


# epistole.gmail
class GmailBackend(Backend):
    def __init__(
        self,
        *,
        from_address: str,
        credential: ServiceAccount | AuthorizedUser | TokenCredential,
    ) -> None: ...


@dataclass(frozen=True)
class ServiceAccount:
    path: Path
    subject: str


@dataclass(frozen=True)
class AuthorizedUser:
    path: Path


# epistole.graph
class GraphBackend(Backend):
    def __init__(
        self,
        *,
        from_address: str,
        credential: ClientSecret | Certificate | ManagedIdentity | TokenCredential,
    ) -> None: ...


@dataclass(frozen=True)
class ClientSecret:
    tenant_id: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class Certificate:
    tenant_id: str
    client_id: str
    pfx: Path | None = None
    passphrase: str | None = None
    private_key: str | None = None
    thumbprint: str | None = None


@dataclass(frozen=True)
class ManagedIdentity:
    client_id: str | None = None


# epistole (doubles)
class MemoryBackend(Backend):
    submissions: list[Submission]

    def __init__(
        self,
        *,
        from_address: str = "epistole@example.invalid",
        refuse: Mapping[str, Refusal] | None = None,
    ) -> None: ...


class ConsoleBackend(Backend):
    def __init__(
        self,
        *,
        from_address: str = "epistole@example.invalid",
        stream: TextIO | None = None,
    ) -> None: ...
```

`TokenCredential` is structural and unexported: any object with `get_token(*scopes: str) -> AccessToken`, where `AccessToken` has `token: str` and `expires_on: int`, the shape `azure.core.credentials.TokenCredential` defines (ADR-0011).

**Every backend.**

- `from_address` is keyword-only on every constructor and takes the ADR-0014 check.
- A provider-only setting is a typed keyword argument on that backend's constructor; a message never carries one and `send` takes the message alone (ADR-0010).
  No such keyword ships in v1.
- Credential values are frozen dataclasses of inputs and import no vendor library.
  The constructor raises `ImportError` naming the extra; `connect()` builds the vendor object (ADR-0009, ADR-0011).
  No bare token, no callable, no vendor client.
- Pre-checks a backend can make from bytes it holds raise `RejectedError` with `__cause__` `None` before writing (ADR-0004, #11).
  Encoded size is raw size times 1.37.

**SMTP (ADR-0011, ADR-0016, ADR-0017).**

- `security="starttls"` requires the upgrade after EHLO and raises `TransportError` when the server does not offer it; `"tls"` is implicit TLS on connect; `"none"` is plaintext.
  No opportunistic mode.
- `credential=None` is anonymous submission.
  `Password` uses `login`; `OAuth` uses XOAUTH2 through `smtplib.SMTP.auth` with `user={username}\x01auth=Bearer {token}\x01\x01`.
- `OAuth.scope` is derived from the issuer of a Graph value (`https://outlook.office365.com/.default`) or a Gmail value (`https://mail.google.com/`); it is required for a `TokenCredential` and a `TypeError` when supplied with the first two.
- Pre-check: server `SIZE` after EHLO, before `DATA`.
- Writes the RFC 5322 message Epistole built: custom headers after Epistole's own, in the caller's order.
- Timeout 60 s, no knob.

**Gmail (ADR-0009, ADR-0011, ADR-0016).**

- REST on `httpx2`, `google-auth` for tokens.
  `ServiceAccount` is domain-wide delegation acting as `subject`; `AuthorizedUser` is a saved user consent.
  Application Default Credentials are not offered.
- `POST users/me/messages/send` with the RFC 5322 bytes as base64url `raw`.
- Pre-checks: encoded size over 36,700,160 bytes; more than 500 recipients.
- Writes every custom header after Epistole's own, in the caller's order.

**Graph (ADR-0009, ADR-0011, ADR-0012, ADR-0016).**

- REST on `httpx2`, `msal` for tokens, scope `https://graph.microsoft.com/.default`.
  `Certificate` takes `pfx` with optional `passphrase`, or `private_key` with `thumbprint`; both forms is a `TypeError`.
- JSON on every request.
  Serialize the `sendMail` body; under 4,000,000 bytes `POST /me/sendMail`.
  Otherwise `POST /me/messages` without attachments, then per attachment in message order `POST /me/messages/{id}/attachments` under 3,000,000 raw bytes or `createUploadSession` plus sequential 3,000,000-byte `PUT`s with `Content-Range` and no bearer, then `POST /me/messages/{id}/send`.
  Automatic; no flag.
- Failure after the draft exists: `DELETE` the upload session if open, then the draft, each best effort; then raise the original error.
- Pre-checks: an attachment over 150,000,000 raw bytes; more than 500 recipients; a custom header whose name does not start with `x-` (case-insensitive), naming the header.
- `internetMessageId` is set to the stamped `Message-ID`; inline images are `fileAttachment` with `isInline: true` and a bare `contentId`.
- The caller's plain text is not carried; Exchange derives its own.
  Documented, not rejected.
- Size constants are private to `GraphTransport`.
- `saveToSentItems` is not exposed.

**HTTP backends, both (ADR-0009).**

- `connect()` builds one `httpx2.Client`, acquires a token, and makes no request to the mail endpoint.
- Every `send` asks the credential for the header, `POST`s, refreshes once on `401`, and retries the same request once; a second `401` is `AuthenticationError`.
- Timeout 60 s on connect, read, write, and pool; no knob.
  No caller-supplied client; proxy and CA come from the environment and the OS trust store.
- Epistole writes both auth adapters over `httpx2`.

**Doubles (ADR-0015).**

- Neither takes a credential; both default `from_address` to `epistole@example.invalid`.
- `MemoryBackend.submissions` is a live list on the backend, in send order, surviving every connection; no reset method.
  `refuse` maps an address to a `Refusal` applied at submit; nothing else is injectable.
- `ConsoleBackend` writes a rendering, never wire bytes: addressing, custom headers (ADR-0016), `Message-ID`, `Date`, subject, the plain text in full, one line per attachment and inline image with name, content type, and size, and HTML as a size line.
  `stream=None` binds `sys.stdout` at write time.

## SendResult, Refusal, errors

```python
@dataclass(frozen=True)
class SendResult:
    message_id: str
    date: datetime
    refused: Mapping[str, Refusal]


@dataclass(frozen=True)
class Refusal:
    code: int
    reason: str


class EpistoleError(Exception):
    backend: Backend | None


class RejectedError(EpistoleError): ...


class SenderRefusedError(EpistoleError): ...


class RecipientsRefusedError(EpistoleError):
    refused: Mapping[str, Refusal]


class AuthenticationError(EpistoleError): ...


class ThrottledError(EpistoleError):
    retry_after: float | None


class TransportError(EpistoleError): ...


class ProviderError(EpistoleError): ...
```

**Send result (ADR-0004, ADR-0015).**

- `message_id` and `date` are what the submission carried; `message_id` is never `None`.
- `refused` is filled only by SMTP and by `MemoryBackend(refuse=)`; empty on Gmail and Graph by contract.
- A returned send result means the service accepted the submission, never that anyone received it.

**Errors (ADR-0004).**

- Flat: seven leaves, no transient base.
  The transient set is `(ThrottledError, TransportError, ProviderError)`.
- `backend` is always the configured backend, or `None` when the failure came before a transport existed.
- The native exception is `__cause__`, raised with `from`; `__cause__` is `None` on an Epistole pre-check.
- `retry_after` is seconds, parsed from both RFC 9110 `Retry-After` forms.
  Epistole never sleeps and never retries.
- Who said no decides the class: a caller mistake before the wire is `TypeError` or `ValueError`, never an `EpistoleError`; a knowable backend limit is `RejectedError`; anything the service said maps below.

| Class | Meaning |
| --- | --- |
| `RejectedError` | the service refused the message or request as invalid, or a backend pre-check refused it; permanent |
| `SenderRefusedError` | the service will not send as `from_address` |
| `RecipientsRefusedError` | every recipient refused, nothing submitted; carries `refused` |
| `AuthenticationError` | credential rejected or permission insufficient |
| `ThrottledError` | the provider asked for a slower rate; carries `retry_after` |
| `TransportError` | connect, TLS, disconnect, timeout; closes the connection (ADR-0005) |
| `ProviderError` | the provider's own `5xx`, or a reply the mapper does not know |

**SMTP mapping (ADR-0004, ADR-0014, ADR-0017).**
Classify on `smtp_code // 100`.

| Native | Epistole |
| --- | --- |
| `SMTPRecipientsRefused` | `RecipientsRefusedError`, `refused` from `.recipients` |
| `SMTPSenderRefused` | `SenderRefusedError` |
| `SMTPAuthenticationError`; `SMTPNotSupportedError` from `login` or `auth` | `AuthenticationError` |
| `SMTPNotSupportedError` from `send_message` (non-ASCII address, no `SMTPUTF8`) | `RejectedError` |
| `SMTPConnectError`, `SMTPHeloError`, `SMTPServerDisconnected`, `421`, `OSError`, `ssl` errors, STARTTLS not offered | `TransportError` |
| `SMTPDataError` `5yz` | `RejectedError` |
| `SMTPDataError` `4yz` | `ProviderError` |

SMTP never raises `ThrottledError`.

**Gmail mapping (ADR-0004, ADR-0009).**
`__cause__` is `httpx2.HTTPStatusError` on a non-2xx, the `httpx2.TransportError` subclass on a network failure, `google.auth.exceptions.RefreshError` on a failed refresh.

| Status and `errors[].reason` | Epistole |
| --- | --- |
| `400`, `404`, `403 domainPolicy` | `RejectedError` |
| `401`, `403 authError`, `403 insufficientPermissions`, refresh failed, second `401` | `AuthenticationError` |
| `403 rateLimitExceeded`, `403 userRateLimitExceeded`, `403 dailyLimitExceeded`, `429` | `ThrottledError`, `retry_after=None` |
| `5xx` | `ProviderError` |
| network failure, including one inside a `RefreshError` | `TransportError` |

**Graph mapping (ADR-0004, ADR-0009, ADR-0012).**
`__cause__` is `httpx2.HTTPStatusError` on a non-2xx, the `httpx2.TransportError` subclass on a network failure, `None` when `msal` returned an error dict.

| Status and `error.code` | Epistole |
| --- | --- |
| `400` (including `ErrorMimeContentInvalidBase64String`), `404`, `413`, `415` | `RejectedError` |
| `401`, other `403` (including `403` on draft creation), msal error dict, second `401` | `AuthenticationError` |
| `403 ErrorSendAsDenied` | `SenderRefusedError` |
| `429` | `ThrottledError`, `retry_after` from `Retry-After` |
| `409`, `500`, `503`, `504`, `509` | `ProviderError` |
| network failure | `TransportError` |

An unmapped status or reason is `ProviderError`; the mapper never raises on its own.

## `html_to_text`

```python
def html_to_text(html: str, /) -> str: ...
```

- The default plain-text extractor, stdlib `html.parser`, no dependency (ADR-0008).
- Keeps links as `label <url>`, marks list items, one table row per line, drops `<head>`, `<style>`, `<script>`, `<title>`, and comments, prints image alt text in brackets, decodes entities, never raises on malformed HTML (ADR-0008).
- Output is best effort and pinned by fixtures, not a contract; it may change in a minor version (ADR-0008).

## Verify in implementation

Facts the ADRs took from documentation or set conservatively.
None moves a signature above; each changes a docstring, a private constant, or a mapping row. [#23](https://github.com/ozanozbeker/epistole/issues/23) ruled them out of the paper spec.

1. Gmail: does `messages.send` keep the stamped `Message-ID` on the wire (ADR-0004, ADR-0011).
2. Gmail: what happens when `From` names neither the account nor a verified alias, and which leaf it maps to (ADR-0001, ADR-0004).
3. Gmail: does `users/me` resolve to `ServiceAccount.subject` on the send endpoint (ADR-0011).
4. Graph: does `internetMessageId` survive to the wire on both paths (ADR-0012).
5. Graph: the exact `sendMail` request cap, and whether any mail endpoint sits below 4 MB (ADR-0012, #22).
6. Graph: the exact `POST /attachments` ceiling and upload-session minimum (ADR-0012).
7. Graph: the shared-mailbox large-attachment `403` and its mapping to `AuthenticationError` (ADR-0012).
8. Graph: `internetMessageHeaders` on create, against the property table's Read-only mark; and whether Exchange caps header count or size (ADR-0016).
9. Graph: whether a MIME-built draft accepts attachments afterwards; if yes, the way to close every Graph fidelity gap (ADR-0012).
10. Graph: whether `singleValueExtendedProperties` with `PS_INTERNET_HEADERS` carries non-`x-` headers; the named reopener for ADR-0016.

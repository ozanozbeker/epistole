# Epistole v1 API specification

The public surface, the backend protocol, and the error model of `epistole` v1, stated once in the order an implementer meets them.
Decided on [#29](https://github.com/ozanozbeker/epistole/issues/29), closing [#2](https://github.com/ozanozbeker/epistole/issues/2).

## Reading this spec

- This file is authoritative for the surface.
  Every rule here cites the ADR that decided it, and a rule with no ADR behind it is a defect in this file.
  Where this file and an ADR disagree, build this file and fix the ADR, or overturn it with a new one.
- ADRs hold the why and the rejected alternatives.
  An ADR is live unless its opening paragraph names what reversed it.
  An `Amended on` line narrows or extends a live ADR rather than retiring it, and the amended text is the ADR.
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
    "AccessToken",
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
    "TokenCredential",
    "Transport",
    "TransportError",
    "html_to_text",
]
```

- Credential values live in the module of the backend that issues their tokens: `epistole.smtp`, `epistole.gmail`, `epistole.graph` (ADR-0011).
  The backend classes are defined there too and re-exported from `epistole`.
- Each backend module carries its own `__all__`: `epistole.smtp` exports `SMTPBackend`, `Password`, and `OAuth`; `epistole.gmail` exports `GmailBackend`, `ServiceAccount`, and `AuthorizedUser`; `epistole.graph` exports `GraphBackend`, `ClientSecret`, `Certificate`, and `ManagedIdentity`.
- `SMTPTransport`, `GmailTransport`, `GraphTransport`, and the doubles' transports are not exported (ADR-0006).
  Each is the `Transport` its backend's `_open()` returns and is named nowhere else.
- One private RFC 5322 builder turns a `Submission` into an `email.message.EmailMessage`.
  `SMTPTransport` writes it and `GmailTransport` sends it as base64url `raw` (ADR-0009); `GraphTransport` never calls it, because every Graph request is JSON (ADR-0012).
  It lives in the core and takes no dependency.
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
- `__eq__` and `__hash__` run over a key of tuples: the address tuples, the subject, the headers as `tuple[tuple[str, str], ...]`, the HTML, the text, and the two attachment tuples (ADR-0016).
  `Attachment` is a frozen dataclass over `bytes`, so it is hashable and the key is too.
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
- `text=` may accompany `html=` or `markdown=`, or stand alone.
  It ships verbatim, wins over anything Epistole would have derived, and is never merged.
  `text=""` is a `ValueError`: an empty part is never what a caller means, and treating it as absent would make `""` and `None` synonyms.
- HTML with no `text=`: `text` is `text_renderer(rewritten_html)` when given, else `html_to_text(rewritten_html)`.
  The renderer runs once at construction on the HTML after the `data:` rewrite, is not stored, and its exceptions propagate unwrapped.
  A return that is not a `str` is a `ValueError`.
- Derived text may be `""`, and that is not an error.
  An image-only body and a body whose only text sits in `<style>` both derive to nothing, so the invariant is that `text` is always a `str`, not that it always holds characters.
  The rule applies to `text_renderer` too, because the renderer stands in for `html_to_text`.
- `text_renderer=` with `text=` or with `markdown=` is a `TypeError`.
- `markdown=` renders through `markdown-it-py`, `commonmark` preset, no options.
  The plain text is the Markdown source verbatim, unless `text=` supplied one.
  Missing extra raises `ImportError` naming `epistole[markdown]`.
- `text=` alone ships `text/plain` alone; `html` is `None`.

**The `data:` rewrite (ADR-0003).**

- Every `<img>` whose `src` is a `data:` URI with an `image/*` media type, base64 or percent-encoded, becomes an inline image at construction.
  No flag.
- The HTML is byte-identical except the rewritten `src` values.
  `<img>` inside comments, `data:` in CSS `url()`, `srcset`, and non-image media types stay as written.
- One inline image per distinct (media type, bytes).
  Content id is the first 16 hex characters of the SHA-256 of the media type, a `NUL` byte, and the payload, plus `mimetypes.guess_extension`'s extension, no `@domain`; the same string is the filename.
  The extension is absent when `guess_extension` returns `None`, so an unregistered `image/*` subtype leaves the bare digest.
  The media type is in the digest so the id is unique per dedupe key: without it, `image/jpeg` and `image/pjpeg` over identical bytes collide.
- A payload that does not decode raises `ValueError` at construction.
- Rewrite runs before the plain-text renderer.

**Attachments and inline images (ADR-0018, ADR-0003).**

- `source` is `Path`, `bytes`, or a binary file object with `.read()`.
  `str` is a `TypeError` that says to wrap it in `Path()`; `bytearray`, `memoryview`, and a text-mode file raise `TypeError`.
- A `Path` names itself.
  Every other source needs `filename=`, and its absence is a `TypeError`; `.name` on a file object is not read.
- `content_type` is inferred from the filename, falls back to `application/octet-stream`, and is always explicit on the wire.
  `content_type=` overrides; bytes are never sniffed.
  A media type carrying parameters is a `ValueError`.
- `.embed()`: `filename` and `cid` default to each other, so `.embed(Path("logo.png"))` answers `<img src="cid:logo.png">`.
  Supplying neither, with a source that is not a `Path`, is a `TypeError`.
  The content type must be `image/*` after inference or override, else `ValueError`.
- A content id the message already holds is a `ValueError` naming it, including one the `data:` rewrite generated at construction.
  `.embed()` still appends; it refuses only the append the HTML could not resolve (ADR-0002).
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
- The set is stored as `tuple[tuple[str, str], ...]`, and `headers_` is a `MappingProxyType` built once at construction and returned by reference.
  The tuple is what `__hash__` reads, because no read-only mapping in the stdlib is hashable.
  `headers_ == {"X-Campaign-Id": "autumn"}` holds, so a test reads it as a dict.
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

    def __init__(self, backend: Backend, transport: Transport, /) -> None: ...
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
- `from_address` is checked at construction on every backend per ADR-0014, and there is no per-send override.
  `SMTPBackend`, `GmailBackend`, and `GraphBackend` require it; the two doubles default it to `epistole@example.invalid`, because on a double there is no mail service to authorize one (ADR-0015).
- `Backend.send(message)` is `with self.connect() as c: return c.send(message)`, written once on the base.
- `connect()` is `Connection(self, self._open())`, written once on the base.
  It catches any `EpistoleError` from `_open()`, sets `backend` to `self`, and re-raises (ADR-0005).
- `_open()` is the only abstract method; nothing else will become abstract.

**Connection (ADR-0005, ADR-0006, ADR-0015).**

- `connect()` takes no arguments and opens eagerly: socket, TLS, and AUTH on SMTP; one `httpx2.Client` and a token on Gmail and Graph; nothing on the doubles.
  `AuthenticationError` and `TransportError` surface on the `connect()` line.
- A connection is built by `Backend.connect()` and by nothing else, and it holds its transport privately.
  It belongs to one thread and cannot be reopened; `send` or `__enter__` after `close()` is a `ValueError`.
  It carries as many sends as the caller makes before that.
  `__enter__` returns `self` and does nothing else.
- `close()` is idempotent and never raises; `__exit__` calls it and never suppresses.
- `TransportError` closes the connection.
  Every other `EpistoleError` leaves it open.
- `Connection.send`, in order: raise `ValueError` if closed; check completeness (at least one recipient; every `cid:` the HTML names matched by an inline image) and raise `ValueError` if not; build a `Submission` stamping `message_id` and `date`; call `transport.submit`; re-key the returned refusals from addr-spec to the matching entry of `message.recipients`; raise `RecipientsRefusedError` if every recipient was refused; return `SendResult(message_id, date, refused)`.
- `Connection.send` is the only place `RecipientsRefusedError` is raised, on every backend including the doubles (ADR-0015).
  A transport answers with refusals and never raises it.
- Any `EpistoleError` leaving `send` gets `backend` set to `self.backend` before it propagates (ADR-0005).
- No lock, no pool, no `begin()`, no `dispose()`.

**Transport (ADR-0006, ADR-0015).**

- The whole of what a third-party backend writes.
  `submit` returns the refusals the service gave, empty when none; it never constructs a `SendResult`.
- A transport that cannot carry part of a message raises `RejectedError` with `__cause__` `None` before writing (ADR-0010).
- `submit` maps the native failure onto one `EpistoleError` leaf per the tables below, raised with `from`.
  It raises the leaf with `backend` unset: a transport receives a `Submission` and nothing else, so it has no backend to name.

**Submission (ADR-0015).**

- Built by `Connection.send` and by nothing else.
  Sending one message twice makes two submissions with two ids.
- `message_id` is `email.utils.make_msgid(domain=...)`, the domain taken from the addr-spec of the backend's `from_address`, keeping its angle brackets.
  It is never `make_msgid()` bare, which resolves the domain through `socket.getfqdn()` and would leak the sending machine's hostname.
- `date` is `email.utils.localtime()`: timezone-aware, carrying the sending machine's offset.

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

`TokenCredential` and `AccessToken` are `Protocol`s exported from `epistole`, because they annotate three public constructors (ADR-0011).
`TokenCredential` is any object with `get_token(*scopes: str) -> AccessToken`; `AccessToken` has `token: str` and `expires_on: int`.
Both are the shape `azure.core.credentials` defines, so an `azure-identity` object satisfies them with no dependency on `azure-core`.

**Every backend (ADR-0001, ADR-0009, ADR-0010, ADR-0011, ADR-0014).**

- `from_address` is keyword-only on every constructor and takes the ADR-0014 check.
- A provider-only setting is a typed keyword argument on that backend's constructor; a message never carries one and `send` takes the message alone (ADR-0010).
  No such keyword ships in v1.
- Credential values are frozen dataclasses of inputs and import no vendor library.
  The backend constructor raises `ImportError` naming the extra its credential value needs, whichever module the value came from, so `SMTPBackend(credential=OAuth(credential=graph.ClientSecret(...)))` names `epistole[graph]`; `connect()` builds the vendor object (ADR-0009, ADR-0011).
  No bare token, no callable, no vendor client.
- Pre-checks a backend can make from bytes it holds raise `RejectedError` with `__cause__` `None` before writing (ADR-0004, ADR-0019).
  A gate measures the bytes it will send and never estimates from a raw size: SMTP and Gmail build the RFC 5322 message first, Graph serializes its JSON body first.
  A ceiling with no vendor source gets no pre-check; the service answers and the reply maps under ADR-0004 (ADR-0019).

**SMTP (ADR-0011, ADR-0016, ADR-0017, ADR-0019).**

- `security="starttls"` requires the upgrade after EHLO and raises `TransportError` when the server does not offer it; `"tls"` is implicit TLS on connect; `"none"` is plaintext.
  No opportunistic mode.
- `credential=None` is anonymous submission.
  `Password` uses `login`; `OAuth` uses XOAUTH2 through `smtplib.SMTP.auth` with `user={username}\x01auth=Bearer {token}\x01\x01`.
- `OAuth.scope` is derived from the issuer: `https://outlook.office365.com/.default` for a Graph value, `https://mail.google.com/` for a Gmail value.
  It is required for a `TokenCredential`, and supplying it alongside a Graph or a Gmail value is a `TypeError`.
  A `graph.ManagedIdentity` inside an `OAuth` requests the resource `https://outlook.office365.com` rather than the scope, per the rule under Graph below.
- No pre-check (ADR-0019).
  `smtplib.sendmail` already appends `size=` when the server advertises the `SIZE` extension, and the server's `552` maps to `RejectedError` (ADR-0004).
- Writes the RFC 5322 message Epistole built: custom headers after Epistole's own, in the caller's order.
- Timeout 60 s, no knob.

**Gmail (ADR-0009, ADR-0011, ADR-0016, ADR-0019).**

- REST on `httpx2`, `google-auth` for tokens.
  `ServiceAccount` is domain-wide delegation acting as `subject`; `AuthorizedUser` is a saved user consent.
  Application Default Credentials are not offered.
- Scope `https://www.googleapis.com/auth/gmail.send`, which is narrower than the `https://mail.google.com/` that SMTP XOAUTH2 requires (ADR-0011).
- `POST users/me/messages/send` with the RFC 5322 bytes as base64url `raw`.
- Pre-checks: an encoded message over 36,700,160 bytes; more than 500 recipients (ADR-0019).
  Both figures are Google's: the byte count from the v1 discovery document, the recipient cap from the API usage limits page, taken as the safe reading against a Workspace page that says 2,000 total with 500 external.
- Writes every custom header after Epistole's own, in the caller's order.

**Graph (ADR-0009, ADR-0011, ADR-0012, ADR-0016, ADR-0019).**

- REST on `httpx2`, `msal` for tokens, audience `https://graph.microsoft.com`.
  `ClientSecret` and `Certificate` request the scope `https://graph.microsoft.com/.default`; `ManagedIdentity` requests the resource `https://graph.microsoft.com`, because `msal.ManagedIdentityClient` takes a resource and accepts no scope (ADR-0011).
  Neither spelling reaches a signature; the private token-source adapter picks one from the credential's type.
- `Certificate` takes exactly one complete form: `pfx` with an optional `passphrase`, or `private_key` and `thumbprint` together.
  Neither form, both forms, either half of the second form alone, and `passphrase` without `pfx` are each a `TypeError`.
- Every request names the mailbox as `/users/{addr-spec}`, the addr-spec of `from_address` percent-encoded into the path.
  There is no `/me` request: `/me` resolves against a signed-in user, and an app-only token has none (ADR-0012).
- JSON on every request.
  Serialize the `sendMail` body; under 4,000,000 bytes `POST /users/{addr-spec}/sendMail`.
  Otherwise `POST /users/{addr-spec}/messages` without attachments, then per attachment in message order `POST /users/{addr-spec}/messages/{id}/attachments` under 3,000,000 raw bytes or `createUploadSession` plus sequential 3,000,000-byte `PUT`s with `Content-Range` and no bearer, then `POST /users/{addr-spec}/messages/{id}/send`.
  Automatic; no flag.
- Failure after the draft exists: `DELETE` the upload session if open, then the draft, each best effort; then raise the original error.
- Pre-checks: an attachment over 150,000,000 raw bytes; more than 500 recipients; a custom header whose name does not start with `x-` (case-insensitive), naming the header (ADR-0012, ADR-0016).
- `internetMessageId` is set to the stamped `Message-ID`; inline images are `fileAttachment` with `isInline: true` and a bare `contentId`.
- With HTML present, the body carries `contentType: "html"` alone and Exchange derives its own text part, so the caller's plain text does not reach the recipient.
  A `text=`-only message carries `contentType: "text"` with the caller's text (ADR-0008).
  Documented, not rejected.
- Size constants are private to `GraphTransport`.
- `saveToSentItems` is not exposed.

**HTTP backends, both (ADR-0009).**

- `connect()` builds one `httpx2.Client`, acquires a token, and makes no request to the mail endpoint.
- Every request asks the credential for the header and goes out on the connection's client.
  On `401` that one request refreshes once and retries itself once; a second `401` on it is `AuthenticationError`.
  The budget is per request, not per send, because Graph's draft path makes `2 + N` requests and a token can expire partway through one send.
  A retry re-sends only a request the service did not accept, so a draft sequence cannot double-submit.
  The Graph upload `PUT`s carry no bearer and are outside this rule; their statuses map under the tables below.
- Timeout 60 s on connect, read, write, and pool; no knob.
  No caller-supplied client; proxy and CA come from the environment and the OS trust store.
- Epistole writes both auth adapters over `httpx2`.

**Doubles (ADR-0015).**

- Neither takes a credential; both default `from_address` to `epistole@example.invalid`.
- `MemoryBackend.submissions` is a live list on the backend, surviving every connection; no reset method.
  `refuse` maps an address to a `Refusal`, matched against each recipient's addr-spec and applied at submit; nothing else is injectable.
- `MemoryBackend` appends a submission only when at least one recipient accepted it, so a fully refused send records nothing and `RecipientsRefusedError`'s "nothing submitted" stays true on the double.
- `submissions` is the one mutable thing a backend holds.
  `list.append` is atomic under both the GIL and a free-threaded build, so concurrent sends cannot corrupt it; they cost order, because entries land in submit-completion order rather than call order.
  A test that asserts on order sends from one thread.
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

    def __init__(self, message: str, /, *, backend: Backend | None = None) -> None: ...


class RejectedError(EpistoleError): ...


class SenderRefusedError(EpistoleError): ...


class RecipientsRefusedError(EpistoleError):
    refused: Mapping[str, Refusal]

    def __init__(
        self,
        message: str,
        /,
        *,
        refused: Mapping[str, Refusal],
        backend: Backend | None = None,
    ) -> None: ...


class AuthenticationError(EpistoleError): ...


class ThrottledError(EpistoleError):
    retry_after: float | None

    def __init__(
        self,
        message: str,
        /,
        *,
        retry_after: float | None = None,
        backend: Backend | None = None,
    ) -> None: ...


class TransportError(EpistoleError): ...


class ProviderError(EpistoleError): ...
```

**Send result (ADR-0004, ADR-0015).**

- `message_id` and `date` are what the submission carried; `message_id` is never `None`.
- `refused` is filled only by SMTP and by `MemoryBackend(refuse=)`; empty on Gmail and Graph by contract.
- `refused` is keyed by the caller's recipient string, not by addr-spec.
  A transport answers with addr-spec keys, and `Connection.send` re-keys each to the matching entry of `message.recipients`, so `result.refused` compares directly against what the caller wrote.
  Two recipients sharing an addr-spec resolve to the first in `recipients` order.
- `Refusal.reason` is text, never bytes: `smtplib` answers in `bytes`, decoded as UTF-8 with `errors="replace"`.
- A returned send result means the service accepted the submission, never that anyone received it.

**Errors (ADR-0004).**

- Flat: seven leaves, no transient base.
  The transient set is `(ThrottledError, TransportError, ProviderError)`.
- A leaf takes its message positionally and its extras keyword-only, so `raise RejectedError("...")` keeps the shape every Python exception has.
- The raise site does not fill `backend`.
  A transport raises the leaf without one, and `Connection.send` and `Backend.connect()` each catch `EpistoleError`, set `backend` to their own, and re-raise (ADR-0005).
  So `backend` is the configured backend on every error that reaches a caller, and `None` only on a leaf inspected before it has propagated.
- The native exception is `__cause__`, raised with `from`.
  `__cause__` is `None` on any check Epistole ran itself, before the wire or after it: a backend pre-check, and the every-recipient-refused check in `Connection.send`.
- `retry_after` is seconds, parsed from both RFC 9110 `Retry-After` forms whenever the response carries the header, and `None` otherwise, on both HTTP backends.
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

**Mapping precedence (ADR-0004).**
One rule over all three tables.

- A code- or reason-qualified row beats a bare status row, which beats a class row.
- An unmatched status or reason is `ProviderError`, on every table.
  The mapper never raises on its own.
- On SMTP, a reply code of `421` in any native exception is `TransportError` before any other row is read, because `smtplib` closes the socket on `421` at MAIL FROM, at RCPT, and at DATA.
- A client-side timeout is the `httpx2.TransportError` subclass and so `TransportError`; a `504` is a status the service returned and so `ProviderError`.

**SMTP mapping (ADR-0004, ADR-0014, ADR-0017).**
Everything below `421` classifies on `smtp_code // 100`.

| Native | Epistole |
| --- | --- |
| any exception carrying `421` | `TransportError` |
| `SMTPSenderRefused` `552` | `RejectedError` |
| `SMTPSenderRefused`, any other code | `SenderRefusedError` |
| `SMTPAuthenticationError`; `SMTPNotSupportedError` from `login` or `auth` | `AuthenticationError` |
| `SMTPNotSupportedError` from `send_message` (non-ASCII address, no `SMTPUTF8`) | `RejectedError` |
| `SMTPConnectError`, `SMTPHeloError`, `SMTPServerDisconnected`, `OSError`, `ssl` errors, STARTTLS not offered | `TransportError` |
| `SMTPDataError` `5yz` | `RejectedError` |
| `SMTPDataError` `4yz` | `ProviderError` |
| any other `SMTPResponseException` | `RejectedError` on `5yz`, `ProviderError` otherwise |
| a bare `SMTPException` | `ProviderError` |

`SMTPRecipientsRefused` has no row: `SMTPTransport` catches it and returns its `.recipients` as refusal data, and `Connection.send` decides whether that is a full refusal (ADR-0015).
The `421` rule runs first, so a `SMTPRecipientsRefused` carrying `421` becomes `TransportError` and is never returned as data.
That is the case where `smtplib` reports one refused recipient, never tries the rest, and closes the socket.
`552` on MAIL FROM is the server refusing the message against its advertised `SIZE`, which is a fact about the message and not about the from address.
SMTP never raises `ThrottledError`.

**Gmail mapping (ADR-0004, ADR-0009).**
`__cause__` is `httpx2.HTTPStatusError` on a non-2xx, the `httpx2.TransportError` subclass on a network failure, `google.auth.exceptions.RefreshError` on a failed refresh.

| Status and `errors[].reason` | Epistole |
| --- | --- |
| `400`, `404`, `403 domainPolicy` | `RejectedError` |
| `401`, `403 authError`, `403 insufficientPermissions`, any other `403`, refresh failed, second `401` | `AuthenticationError` |
| `403 rateLimitExceeded`, `403 userRateLimitExceeded`, `403 dailyLimitExceeded`, `429` | `ThrottledError` |
| `5xx` | `ProviderError` |
| network failure, including one inside a `RefreshError` | `TransportError` |

A `RefreshError` is read one level down: a network failure inside it is `TransportError`, and a refresh that failed on its own terms is `AuthenticationError`.
The qualified row wins, per the precedence rule (ADR-0009).

**Graph mapping (ADR-0004, ADR-0009, ADR-0012).**
`__cause__` is `httpx2.HTTPStatusError` on a non-2xx, the `httpx2.TransportError` subclass on a network failure, `None` when `msal` returned an error dict.

| Status and `error.code` | Epistole |
| --- | --- |
| `400` (including `ErrorMimeContentInvalidBase64String`), `404`, `413`, `415` | `RejectedError` |
| `401`, any other `403` (including `403` on draft creation), msal error dict, second `401` | `AuthenticationError` |
| `403 ErrorSendAsDenied` | `SenderRefusedError` |
| `429` | `ThrottledError` |
| `409`, `500`, `503`, `504`, `509` | `ProviderError` |
| network failure | `TransportError` |

## `html_to_text`

```python
def html_to_text(html: str, /) -> str: ...
```

- The default plain-text extractor, stdlib `html.parser`, no dependency (ADR-0008).
- Keeps links as `label <url>`, marks list items, one table row per line, drops `<head>`, `<style>`, `<script>`, `<title>`, and comments, prints image alt text in brackets, decodes entities, never raises on malformed HTML (ADR-0008).
- Returns `""` for HTML holding no text, such as an image-only body or one whose only text sits in `<style>`.
  That is not an error, and `Message` ships it (ADR-0008).
- Output is best effort and pinned by fixtures, not a contract; it may change in a minor version (ADR-0008).

## Verify in implementation

Facts the ADRs took from documentation or set conservatively. [#23](https://github.com/ozanozbeker/epistole/issues/23) ruled them out of the paper spec.

**Facts.**
None moves a signature above; each changes a docstring, a private constant, or a mapping row.

1. Gmail: does `messages.send` keep the stamped `Message-ID` on the wire (ADR-0004, ADR-0011).
2. Gmail: what happens when `From` names neither the account nor a verified alias, and which leaf it maps to; it lands on `AuthenticationError` through the catch-all `403` until a reason string is observed (ADR-0001, ADR-0004).
3. Gmail: does `users/me` resolve to `ServiceAccount.subject` on the send endpoint (ADR-0011).
4. Graph: does `/users/{addr-spec}` serve a delegated `TokenCredential` reaching its own mailbox, as the app-only path does (ADR-0012).
5. Graph: does `internetMessageId` survive to the wire on both paths (ADR-0012).
6. Graph: the exact `sendMail` request cap, and whether any mail endpoint sits below 4 MB (ADR-0012, #22).
7. Graph: the exact `POST /attachments` ceiling and upload-session minimum (ADR-0012).
8. Graph: the shared-mailbox large-attachment `403` and its mapping to `AuthenticationError` (ADR-0012).
9. Graph: `internetMessageHeaders` on create, against the property table's Read-only mark; and whether Exchange caps header count or size (ADR-0016).

**Reopeners.**
Each of these changes behaviour if the answer is yes, so each needs an ADR before anything moves.

1. Graph: whether a MIME-built draft accepts attachments afterwards; if yes, the way to close every Graph fidelity gap (ADR-0012).
2. Graph: whether `singleValueExtendedProperties` with `PS_INTERNET_HEADERS` carries non-`x-` headers; the named reopener for ADR-0016.

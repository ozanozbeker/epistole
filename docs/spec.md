# Epistole v1 API specification

This spec states the public surface, the backend protocol, and the error model of `epistole` v1 once, in the order an implementer encounters them.
Decided on [#29](https://github.com/ozanozbeker/epistole/issues/29), closing [#2](https://github.com/ozanozbeker/epistole/issues/2).

## Reading this spec

- This file is authoritative for the surface.
  Every rule here cites its ADR.
  A rule with no ADR is a defect in this file.
  Where this file and an ADR disagree, build this file and fix the ADR, or overturn it with a new one.
- ADRs hold the why and the rejected alternatives.
  An ADR is in force unless its opening paragraph names what reversed it.
  An `Amended on` line narrows or extends an ADR in force rather than retiring it.
  The amended text is the ADR.
  There is no status field.
- `CONTEXT.md` is the glossary.
  A name here means what the glossary says it means.
- Signatures are the contract.
  This file leaves docstrings out.
  Rule bullets under a block state what a signature cannot express.
- `docs/research/*.md` holds the measurements the ADRs cite.

## Modules and exports

```python
# epistole
__all__ = [
    "AccessToken",
    "Address",
    "Attachment",
    "Backend",
    "Connection",
    "ConsoleBackend",
    "GmailBackend",
    "GraphBackend",
    "MemoryBackend",
    "Message",
    "Refusal",
    "SMTPBackend",
    "SendResult",
    "Submission",
    "TokenCredential",
    "Transport",
    "exceptions",
    "html_to_text",
]


# epistole.exceptions
__all__ = [
    "AuthenticationError",
    "EpistoleError",
    "ProviderError",
    "RecipientsRefusedError",
    "RejectedError",
    "SenderRefusedError",
    "ThrottledError",
    "TransportError",
]
```

- Every error class is defined in `epistole.exceptions`.
  None is re-exported from `epistole`.
  A caller writes `from epistole.exceptions import ThrottledError`, or `from epistole import exceptions` and then `exceptions.ThrottledError`.
  The module is named for `Exception` rather than for `Error` because `Warning` is an `Exception` too.
  So a warning Epistole raises later can be defined in the same module, and the module name stays accurate.
  `polars.exceptions`, `numpy.exceptions`, and `sqlalchemy.exc` each hold both kinds.
  `pandas.errors` is the counterexample.
  `epistole` lists the submodule itself in `__all__`, so `import epistole` gives access to `epistole.exceptions` without a second import line.
- Credential values are defined in the module of the backend that issues their tokens: `epistole.smtp`, `epistole.gmail`, `epistole.graph` (ADR-0011).
  The backend classes are defined there too and re-exported from `epistole`.
- Each backend module defines its own `__all__`.
  `epistole.smtp` exports `SMTPBackend`, `Password`, and `OAuth`.
  `epistole.gmail` exports `GmailBackend`, `ServiceAccount`, and `AuthorizedUser`.
  `epistole.graph` exports `GraphBackend`, `ClientSecret`, `Certificate`, and `ManagedIdentity`.
- `SMTPTransport`, `GmailTransport`, `GraphTransport`, and the doubles' transports are not exported (ADR-0006).
  Each is the `Transport` its backend's `_open()` returns, and no other code names it.
- One private RFC 5322 builder turns a `Submission` into an `email.message.EmailMessage`.
  `SMTPTransport` writes it, and `GmailTransport` sends it as base64url `raw` (ADR-0009).
  `GraphTransport` never calls it, because every Graph request is JSON (ADR-0012).
  It is defined in the core and takes no dependency.
  It writes `Bcc`, because Gmail sends to the addresses in `To`, `Cc`, and `Bcc` (ADR-0016).
  `SMTPTransport` writes it through `smtplib`'s `send_message`, which deletes `Bcc` first.
- `from epistole import GmailBackend` and `GraphBackend` always succeed.
  The constructor runs the vendor imports (ADR-0009).
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

    # attributes
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

- A message is frozen, compares equal by content, and is hashable.
  Every builder method returns a new message.
  The receiver is unchanged.
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

- The constructor takes exactly one of `html=` or `markdown=`, or neither with `text=` alone.
  Both, or none of the three, is a `TypeError`.
- `text=` may be passed with `html=` or `markdown=`, or alone.
  Epistole sends it verbatim and never merges it.
  It overrides anything Epistole would have derived.
  `text=""` sends empty plain text, for a caller who puts the whole message in the subject.
- HTML with no `text=`: `text` is `text_renderer(rewritten_html)` when given, else `html_to_text(rewritten_html)`.
  The renderer runs once at construction, on the HTML after the `data:` rewrite.
  The message does not store it.
  Its exceptions propagate unwrapped.
  A return value that is not a `str` is a `ValueError`.
- Derived text may be `""`, and that is not an error.
  An image-only body and a body whose only text is inside `<style>` both derive to nothing.
  So the invariant is that `text` is always a `str`, not that it always holds characters.
  The rule applies to `text_renderer` too, because the renderer replaces `html_to_text`.
- `text_renderer=` with `text=` or with `markdown=` is a `TypeError`.
- `markdown=` renders through `markdown-it-py` with the `commonmark` preset and no options.
  The plain text is the Markdown source verbatim, unless `text=` supplied one.
  Rendering without the extra raises `ImportError` naming `epistole[markdown]`.
- With `text=` alone, Epistole sends `text/plain` alone.
  `html` is `None`.

**The `data:` rewrite (ADR-0003).**

- Every `<img>` whose `src` is a `data:` URI with an `image/*` media type, base64 or percent-encoded, becomes an inline image at construction.
  There is no flag.
- The HTML is byte-identical except the rewritten `src` values.
  `<img>` inside comments, `data:` in CSS `url()`, `srcset`, and non-image media types stay as written.
- The rewrite makes one inline image per distinct (media type, bytes).
  The content id is the first 16 hex characters of the SHA-256 of the media type, a `NUL` byte, and the payload, plus `mimetypes.guess_extension`'s extension.
  It has no `@domain`.
  The same string is the filename.
  The extension is absent when `guess_extension` returns `None`, so an unregistered `image/*` subtype leaves the bare digest.
  The media type is in the digest so the id is unique per dedupe key.
  Without it, `image/jpeg` and `image/pjpeg` over identical bytes collide.
- A payload that does not decode is a `ValueError` at construction.
- The rewrite runs before the plain-text renderer.

**Attachments and inline images (ADR-0018, ADR-0003).**

- `source` is `Path`, `bytes`, or a binary file object with `.read()`.
  `str` is a `TypeError` that says to wrap it in `Path()`.
  `bytearray`, `memoryview`, and a text-mode file raise `TypeError`.
- A `Path` supplies its own filename.
  Every other source needs `filename=`, and its absence is a `TypeError`.
  Epistole does not read `.name` on a file object.
- `content_type` is inferred from the filename and falls back to `application/octet-stream`.
  A compressed filename such as `weekly.csv.gz` falls back too, because its bytes are gzip and not `text/csv`.
  It is always explicit in the sent message.
  `content_type=` overrides it.
  Epistole never sniffs the bytes.
  A media type with parameters is a `ValueError`, as is any other `content_type=` that is not a bare `type/subtype` in RFC 6838's grammar.
- `.embed()`: `filename` and `cid` default to each other, so `.embed(Path("logo.png"))` resolves `<img src="cid:logo.png">`.
  Supplying neither, with a source that is not a `Path`, is a `TypeError`.
  The content type must be `image/*` after inference or override, else `ValueError`.
- A filename or a content id that holds a line break is a `ValueError`, including a `Path`'s own name.
  The check runs before the source is read.
- A content id that is not ASCII is a `ValueError`, because SMTP and Gmail would write it as an RFC 2047 encoded-word.
  A filename may still be non-ASCII.
- A content id the message already holds is a `ValueError` naming it, including one the `data:` rewrite generated at construction.
  `.embed()` still appends.
  It raises only on the append the HTML could not resolve (ADR-0002).
- `attachments` holds what `.attach()` added.
  `inline_images` holds what `.embed()` added and what the rewrite made.
  Each is in insertion order.
  `content_id` is `None` on an attachment and set on an inline image.
  Neither name takes ADR-0007's underscore, because no method has that name (#29).

**Addresses (ADR-0014).**

- An address is checked where it is supplied: in the four address methods and in `from_address`.
  A failed check is a `ValueError`.
  A string passes when it holds no line break, `email.utils.getaddresses` returns exactly one pair, the addr-spec is non-empty, and both halves of its last `@` are non-empty.
  Epistole inspects nothing else: no character set, no DNS, no punycode.
- `recipients` is `to_ + cc_ + bcc_` in that order, duplicates kept (ADR-0007).
- SMTP and Gmail write a message that holds a non-ASCII addr-spec with UTF-8 headers, because RFC 2047 allows no encoded-word in an addr-spec (ADR-0014).

**Subject (ADR-0016).**

- A subject that holds a line break is a `ValueError`, checked in `.subject()`.
  The rule is the one a custom header value follows.

**Custom headers (ADR-0016).**

- `.headers(mapping)` replaces the whole set with a copy.
  `headers_` reads it back in the given order, as a read-only mapping that holds the caller's headers alone.
- The set is stored as `tuple[tuple[str, str], ...]`.
  `headers_` is a `MappingProxyType` built once at construction and returned by reference.
  `__hash__` reads the tuple, because no read-only mapping in the stdlib is hashable.
  `headers_ == {"X-Campaign-Id": "autumn"}` holds, so a test reads it as a dict.
- A legal name is one or more characters in printable ASCII 33 to 126 excluding `:`.
  A legal value is a `str` with no character that `str.splitlines()` splits on, such as `\r`, `\n`, or `\u2028`.
  `EmailMessage` raises on a value that `str.splitlines()` splits, so the check covers every value it raises on.
  Anything else is a `ValueError`, checked in `Message`.
- A name Epistole owns is a `ValueError`, matched case-insensitively on the exact name: `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject`, `Message-ID`, `Date`, `MIME-Version`, `Content-Type`, `Content-Transfer-Encoding`, `Content-ID`, `Content-Disposition`.
- Two names that differ only in case are a `ValueError`, because a `dict` holds both and RFC 5322 names are case-insensitive.
- SMTP and Gmail write an ASCII value as the caller wrote it, on one line (ADR-0016).
  `EmailMessage` would write a word longer than 77 characters, such as a `List-Unsubscribe` URL, as RFC 2047 encoded-words.

**Attributes (ADR-0007).**

- A builder method's value is an attribute named for the method plus a trailing underscore.
  `recipients`, `html`, `text`, `attachments`, and `inline_images` have no underscore because no method has those names (ADR-0007, ADR-0008, #29).

**What Epistole never does to HTML (ADR-0013).**

- Epistole never rewrites CSS, never warns about size, and has no `html_renderer=`.
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

- A backend is immutable configuration, safe to share across threads.
  It is not a context manager: `with backend:` is a `TypeError`.
- `from_address` is checked at construction on every backend per ADR-0014.
  There is no per-send override.
  `SMTPBackend`, `GmailBackend`, and `GraphBackend` require it.
  The two doubles default it to `epistole@example.invalid`, because a double has no mail service to authorize one (ADR-0015).
- `Backend.send(message)` is `with self.connect() as c: return c.send(message)`, written once on the base.
- `connect()` is `Connection(self, self._open())`, written once on the base.
  It catches any `EpistoleError` from `_open()`, sets `backend` to `self`, and re-raises (ADR-0005).
- `_open()` is the only abstract method.
  Nothing else will become abstract.

**Connection (ADR-0005, ADR-0006, ADR-0015).**

- `connect()` takes no arguments.
  It opens eagerly: socket, TLS, and AUTH on SMTP; one `httpx2.Client` and a token on Gmail and Graph; nothing on the doubles.
  `AuthenticationError` and `TransportError` are raised on the `connect()` line.
- Only `Backend.connect()` builds a connection.
  A connection holds its transport privately.
  It belongs to one thread and cannot be reopened.
  `send` or `__enter__` after `close()` is a `ValueError`.
  Before that, it accepts as many sends as the caller makes.
  `__enter__` returns `self` and does nothing else.
- `close()` is idempotent and never raises.
  `__exit__` calls it and never suppresses.
- The connection closes on a `TransportError`.
  It stays open on every other `EpistoleError`.
- `Connection.send` runs these steps in order:
  1. Raise `ValueError` if closed.
  2. Check completeness (at least one recipient; every `cid:` the HTML names matched by an inline image) and raise `ValueError` if not.
  3. Build a `Submission`, setting `message_id` and `date`.
  4. Call `transport.submit`.
  5. Re-key the returned refusals from addr-spec to the matching entry of `message.recipients`.
  6. Raise `RecipientsRefusedError` if every recipient was refused.
  7. Return `SendResult(message_id, date, refused)`.
- Only `Connection.send` raises `RecipientsRefusedError`, on every backend including the doubles (ADR-0015).
  A transport returns refusals and never raises it.
- `send` sets `backend` to `self.backend` on any `EpistoleError` before the error propagates (ADR-0005).
- A connection has no lock, no pool, no `begin()`, and no `dispose()`.

**Transport (ADR-0006, ADR-0015).**

- A third-party backend writes a transport and nothing else.
  `submit` returns the refusals the service gave, empty when there are none.
  It never constructs a `SendResult`.
- A transport that cannot carry part of a message raises `RejectedError` with `__cause__` `None` before writing (ADR-0010).
- `submit` maps the native failure onto one `EpistoleError` subclass per the tables below, raised with `from`.
  It raises that error with `backend` unset.
  A transport receives a `Submission` and nothing else, so it has no backend to name.

**Submission (ADR-0015).**

- Only `Connection.send` builds a submission.
  Sending one message twice makes two submissions with two ids.
- `message_id` is `email.utils.make_msgid(domain=...)`, and it keeps its angle brackets.
  The domain is taken from the addr-spec of the backend's `from_address`.
  It is never `make_msgid()` bare.
  That call resolves the domain through `socket.getfqdn()` and would leak the sending machine's hostname.
- A non-ASCII domain is IDNA-encoded before it is written into the `Message-ID`, so a send from `用户@例子.广告` writes `@xn--fsqu00a.xn--4rr70v` (ADR-0015).
  RFC 5322 specifies a `msg-id` in ASCII.
  `EmailMessage.as_bytes()` raises `UnicodeEncodeError` on anything else.
  That error is not an `EpistoleError` and is in no mapping table.
  A `Message-ID` is an identifier and not a route, so nothing resolves the encoded domain.
  The stdlib codec's IDNA 2003 folding is therefore harmless here.
  `Connection.send` raises `ValueError` for a domain the codec cannot encode: one with an empty label, or with a label longer than 63 characters once encoded.
  ADR-0014 is still in force.
  The encoding covers what Epistole sets, not what it checks.
  Epistole still accepts a non-ASCII address.
- `date` is `email.utils.localtime()`: timezone-aware, with the sending machine's offset.

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
`TokenCredential` is any object with `get_token(*scopes: str) -> AccessToken`.
`AccessToken` has `token: str` and `expires_on: int`.
Both are the shape `azure.core.credentials` defines, so an `azure-identity` object satisfies them with no dependency on `azure-core`.

**Every backend (ADR-0001, ADR-0009, ADR-0010, ADR-0011, ADR-0014).**

- `from_address` is keyword-only on every constructor and takes the ADR-0014 check.
- A provider-only setting is a typed keyword argument on that backend's constructor.
  A message never carries one.
  `send` takes the message alone (ADR-0010).
  There is no such keyword in v1.
- Credential values are frozen dataclasses of inputs and import no vendor library.
  The backend constructor raises `ImportError` naming the extra its credential value needs, whichever module the value came from.
  So `SMTPBackend(credential=OAuth(credential=graph.ClientSecret(...)))` names `epistole[graph]`.
  `connect()` builds the vendor object (ADR-0009, ADR-0011).
  A backend accepts no bare token, no callable, and no vendor client.
- Pre-checks a backend can make from bytes it holds raise `RejectedError` with `__cause__` `None` before writing (ADR-0004, ADR-0019).
  A gate measures the bytes it will send and never estimates from a raw size.
  SMTP and Gmail build the RFC 5322 message first, and Graph serializes its JSON body first.
  A limit with no vendor source gets no pre-check.
  Epistole maps the service's reply under ADR-0004 instead (ADR-0019).

**SMTP (ADR-0011, ADR-0014, ADR-0016, ADR-0017, ADR-0019).**

- `security="starttls"` requires the upgrade after EHLO and raises `TransportError` when the server does not offer it.
  `"tls"` is implicit TLS on connect.
  `"none"` is plaintext.
  There is no opportunistic mode.
- `credential=None` is anonymous submission.
  `Password` uses `login`.
  `OAuth` uses XOAUTH2 through `smtplib.SMTP.auth` with `user={username}\x01auth=Bearer {token}\x01\x01`.
- `OAuth.scope` is derived from the issuer: `https://outlook.office365.com/.default` for a Graph value, `https://mail.google.com/` for a Gmail value.
  It is required for a `TokenCredential`.
  Supplying it alongside a Graph or a Gmail value is a `TypeError`.
  A `graph.ManagedIdentity` inside an `OAuth` requests the resource `https://outlook.office365.com` rather than the scope, per the rule under Graph below.
- SMTP has no pre-check (ADR-0019).
  `smtplib.sendmail` already appends `size=` when the server advertises the `SIZE` extension.
  The server's `552` maps to `RejectedError` (ADR-0004).
- SMTP writes the RFC 5322 message Epistole built.
  Custom headers follow Epistole's own, in the caller's order.
- SMTP asks the server for `SMTPUTF8` whenever the built message has UTF-8 headers, including when `Reply-To` holds the only non-ASCII address (ADR-0014).
- The timeout is 60 s, and no setting changes it.

**Gmail (ADR-0009, ADR-0011, ADR-0016, ADR-0019).**

- Gmail uses REST on `httpx2`, with `google-auth` for tokens.
  `ServiceAccount` is domain-wide delegation acting as `subject`.
  `AuthorizedUser` is a saved user consent.
  Epistole does not offer Application Default Credentials.
- The scope is `https://www.googleapis.com/auth/gmail.send`, which is narrower than the `https://mail.google.com/` that SMTP XOAUTH2 requires (ADR-0011).
- Gmail sends `POST users/me/messages/send` with the RFC 5322 bytes as base64url `raw`.
- Pre-checks raise on an encoded message over 36,700,160 bytes and on more than 500 recipients (ADR-0019).
  Both figures are Google's.
  The byte count comes from the v1 discovery document.
  The recipient cap comes from the API usage limits page, taken as the safe reading against a Workspace page that says 2,000 total with 500 external.
- Gmail writes every custom header after Epistole's own, in the caller's order.

**Graph (ADR-0009, ADR-0011, ADR-0012, ADR-0016, ADR-0019).**

- Graph uses REST on `httpx2`, with `msal` for tokens and the audience `https://graph.microsoft.com`.
  `ClientSecret` and `Certificate` request the scope `https://graph.microsoft.com/.default`.
  `ManagedIdentity` requests the resource `https://graph.microsoft.com`, because `msal.ManagedIdentityClient` takes a resource and accepts no scope (ADR-0011).
  Neither spelling appears in a signature.
  The private token-source adapter selects one by the credential's type.
- `Certificate` takes exactly one complete form: `pfx` with an optional `passphrase`, or `private_key` and `thumbprint` together.
  Neither form, both forms, either half of the second form alone, and `passphrase` without `pfx` are each a `TypeError`.
- Every request names the mailbox as `/users/{addr-spec}`.
  The addr-spec of `from_address` is percent-encoded into the path.
  There is no `/me` request.
  `/me` resolves against a signed-in user, and an app-only token has none (ADR-0012).
- Every request is JSON.
  Serialize the `sendMail` body.
  Under 4,000,000 bytes, `POST /users/{addr-spec}/sendMail`.
  Otherwise, `POST /users/{addr-spec}/messages` without attachments.
  Then, per attachment in message order, `POST /users/{addr-spec}/messages/{id}/attachments` under 3,000,000 raw bytes, or `createUploadSession` plus sequential 3,000,000-byte `PUT`s with `Content-Range` and no bearer.
  Then `POST /users/{addr-spec}/messages/{id}/send`.
  Path selection is automatic, and there is no flag.
- On a failure after the draft exists, `DELETE` the upload session if open, then the draft, each best effort.
  Then raise the original error.
- Pre-checks raise on an attachment over 150,000,000 raw bytes, on more than 500 recipients, and on a custom header whose name does not start with `x-` (case-insensitive), naming the header (ADR-0012, ADR-0016).
- `internetMessageId` is set to the `Message-ID` Epistole generated.
  Inline images are `fileAttachment` with `isInline: true` and a bare `contentId`.
- With HTML present, the body carries `contentType: "html"` alone.
  Exchange derives its own plain text, so the recipient does not receive the caller's plain text.
  A `text=`-only message carries `contentType: "text"` with the caller's text (ADR-0008).
  This is documented, not rejected.
- Size constants are private to `GraphTransport`.
- Epistole does not expose `saveToSentItems`.

**HTTP backends, both (ADR-0009).**

- `connect()` builds one `httpx2.Client`, acquires a token, and makes no request to the mail endpoint.
- Before every request, Epistole gets the header from the credential.
  Every request is sent on the connection's client.
  On `401`, Epistole refreshes once and retries that one request once.
  A second `401` on it is `AuthenticationError`.
  The budget is per request, not per send, because Graph's draft path makes `2 + N` requests and a token can expire partway through one send.
  A retry re-sends only a request the service did not accept, so a draft sequence cannot double-submit.
  The Graph upload `PUT`s carry no bearer and are outside this rule.
  Their statuses map under the tables below.
- The timeout is 60 s on connect, read, write, and pool, and no setting changes it.
  There is no caller-supplied client.
  Proxy and CA settings come from the environment and the OS trust store.
- Epistole writes both auth adapters over `httpx2`.

**Doubles (ADR-0015).**

- Neither takes a credential.
  Both default `from_address` to `epistole@example.invalid`.
- `MemoryBackend.submissions` is a live list on the backend.
  It persists across every connection, and there is no reset method.
  `refuse` maps an address to a `Refusal`, matched against each recipient's addr-spec and applied at submit.
  Nothing else is injectable.
- `MemoryBackend` appends a submission only when at least one recipient accepted it.
  So a fully refused send records nothing, and `RecipientsRefusedError`'s "nothing submitted" stays true on the double.
- `submissions` is the one mutable thing a backend holds.
  `list.append` is atomic under both the GIL and a free-threaded build, so concurrent sends cannot corrupt it.
  Concurrent sends do lose call order, because entries are appended in submit-completion order.
  A test that asserts on order sends from one thread.
- `ConsoleBackend` writes a rendering, never the bytes a backend sends.
  It writes the from address, the addressing, custom headers (ADR-0016), `Message-ID`, `Date`, subject, and the plain text in full.
  It writes one line per attachment and inline image, with name, content type, and size.
  It writes HTML as a size line.
  It flushes the stream after each rendering, so a pipe or a file holds the rendering when the send returns.
  `stream=None` binds `sys.stdout` at write time.

## SendResult, Refusal, exceptions

`SendResult` and `Refusal` are in `epistole`.
Every class below them is in `epistole.exceptions`.

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


# epistole.exceptions
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

- `message_id` and `date` are copied from the submission.
  `message_id` is never `None`.
- Only SMTP and `MemoryBackend(refuse=)` fill `refused`.
  It is empty on Gmail and Graph by contract.
- `refused` is keyed by the caller's recipient string, not by addr-spec.
  A transport returns addr-spec keys.
  `Connection.send` re-keys each to the matching entry of `message.recipients`, so `result.refused` compares directly against what the caller wrote.
  Two recipients sharing an addr-spec resolve to the first in `recipients` order.
- `Refusal.reason` is text, never bytes.
  `smtplib` returns `bytes`, and Epistole decodes them as UTF-8 with `errors="replace"`.
- A returned send result means the service accepted the submission, never that anyone received it.

**Errors (ADR-0004).**

- The hierarchy is flat: seven error classes under `EpistoleError`, with no transient base.
  The transient set is `(ThrottledError, TransportError, ProviderError)`.
- Each takes its message positionally and its extras keyword-only, so `raise RejectedError("...")` keeps the shape every Python exception has.
- The raise site does not fill `backend`.
  A transport raises the error without one.
  `Connection.send` and `Backend.connect()` each catch `EpistoleError`, set `backend` to their own, and re-raise (ADR-0005).
  So `backend` is the configured backend on every error a caller receives.
  It is `None` only on an error inspected before it has propagated.
- The native exception is `__cause__`, raised with `from`.
  `__cause__` is `None` on any check Epistole ran itself, before any network call or after one: a backend pre-check, and the every-recipient-refused check in `Connection.send`.
- On both HTTP backends, `retry_after` is seconds, parsed from both RFC 9110 `Retry-After` forms whenever the response carries the header.
  It is `None` otherwise.
  Epistole never sleeps and never retries.
- The source of the failure sets the class.
  A caller mistake found before any network call is `TypeError` or `ValueError`, never an `EpistoleError`.
  A knowable backend limit is `RejectedError`.
  Anything the service returned maps under the tables below.

| Class | Meaning |
| --- | --- |
| `RejectedError` | the service rejected the message or request as invalid, or a backend pre-check rejected it; permanent |
| `SenderRefusedError` | the service will not send as `from_address` |
| `RecipientsRefusedError` | every recipient refused, nothing submitted; carries `refused` |
| `AuthenticationError` | credential rejected or permission insufficient |
| `ThrottledError` | the provider rate-limited the request; carries `retry_after` |
| `TransportError` | connect, TLS, disconnect, timeout; closes the connection (ADR-0005) |
| `ProviderError` | the provider's own `5xx`, or a reply the mapper has no row for |

**Mapping precedence (ADR-0004).**
One rule applies to all three tables.

- A code- or reason-qualified row takes precedence over a bare status row, which takes precedence over a class row.
- An unmatched status or reason is `ProviderError`, on every table.
  The mapper never raises on its own.
- On SMTP, a reply code of `421` in any native exception is `TransportError` before any other row is read, because `smtplib` closes the socket on `421` at MAIL FROM, at RCPT, and at DATA.
- A client-side timeout is the `httpx2.TransportError` subclass and so `TransportError`.
  A `504` is a status the service returned and so `ProviderError`.

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

`SMTPRecipientsRefused` has no row.
`SMTPTransport` catches it and returns its `.recipients` as refusal data.
`Connection.send` checks whether that is a full refusal (ADR-0015).
The `421` rule runs first, so a `SMTPRecipientsRefused` carrying `421` becomes `TransportError` and is never returned as data.
In that case `smtplib` reports one refused recipient, never tries the rest, and closes the socket.
`552` on MAIL FROM is the server rejecting the message against its advertised `SIZE`.
That is a fact about the message, not about the from address.
SMTP never raises `ThrottledError`.

**Gmail mapping (ADR-0004, ADR-0009).**
`__cause__` is `httpx2.HTTPStatusError` on a non-2xx, the `httpx2.TransportError` subclass on a network failure, and `google.auth.exceptions.RefreshError` on a failed refresh.

| Status and `errors[].reason` | Epistole |
| --- | --- |
| `400`, `404`, `403 domainPolicy` | `RejectedError` |
| `401`, `403 authError`, `403 insufficientPermissions`, any other `403`, refresh failed, second `401` | `AuthenticationError` |
| `403 rateLimitExceeded`, `403 userRateLimitExceeded`, `403 dailyLimitExceeded`, `429` | `ThrottledError` |
| `5xx` | `ProviderError` |
| network failure, including one inside a `RefreshError` | `TransportError` |

A `RefreshError` is read one level down.
A network failure inside it is `TransportError`, and any other failed refresh is `AuthenticationError`.
The qualified row applies first, per the precedence rule (ADR-0009).

**Graph mapping (ADR-0004, ADR-0009, ADR-0012).**
`__cause__` is `httpx2.HTTPStatusError` on a non-2xx, the `httpx2.TransportError` subclass on a network failure, and `None` when `msal` returned an error dict.

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

- It is the default plain-text extractor, built on stdlib `html.parser` with no dependency (ADR-0008).
- It keeps links as `label <url>`, marks list items, and writes one table row per line.
  It drops `<head>`, `<style>`, `<script>`, `<title>`, and comments.
  It prints image alt text in brackets and decodes entities.
  It never raises on malformed HTML (ADR-0008).
- It returns `""` for HTML holding no text, such as an image-only body or one whose only text is inside `<style>`.
  That is not an error, and `Message` keeps it (ADR-0008).
- Output is best effort and pinned by fixtures, not a contract.
  It may change in a minor version (ADR-0008).

## Verify in implementation

These are facts the ADRs took from documentation or set conservatively.
The decision on [#23](https://github.com/ozanozbeker/epistole/issues/23) left them out of the written spec.

**Facts.**
None changes a signature above.
Each changes a docstring, a private constant, or a mapping row.

1. Gmail: does `messages.send` keep the `Message-ID` Epistole set in the sent message (ADR-0004, ADR-0011).
2. Gmail: what happens when `From` names neither the account nor a verified alias, and which class it maps to.
   Until a reason string is observed, it maps to `AuthenticationError` through the catch-all `403` (ADR-0001, ADR-0004).
3. Gmail: does `users/me` resolve to `ServiceAccount.subject` on the send endpoint (ADR-0011).
4. Graph: does `/users/{addr-spec}` accept a delegated `TokenCredential` accessing its own mailbox, as the app-only path does (ADR-0012).
5. Graph: is `internetMessageId` kept in the sent message on both paths (ADR-0012).
6. Graph: what the exact `sendMail` request cap is, and whether any mail endpoint caps requests below 4 MB (ADR-0012, #22).
7. Graph: what the exact `POST /attachments` limit and upload-session minimum are (ADR-0012).
8. Graph: whether the shared-mailbox large-attachment `403` occurs, and whether it maps to `AuthenticationError` (ADR-0012).
9. Graph: whether create accepts `internetMessageHeaders` despite the property table's Read-only mark, and whether Exchange caps header count or size (ADR-0016).

**Reopeners.**
Each of these changes behaviour if the answer is yes.
So each needs an ADR before anything changes.

1. Graph: whether a MIME-built draft accepts attachments afterwards.
   If yes, it is the way to close every Graph fidelity gap (ADR-0012).
2. Graph: whether `singleValueExtendedProperties` with `PS_INTERNET_HEADERS` carries non-`x-` headers.
   It is the named reopener for ADR-0016.

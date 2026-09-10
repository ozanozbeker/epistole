# A send returns a send result, and refusals do not raise

No backend hands back a message id Epistole can return on all three, so `send` returns the id Epistole wrote.
`send` returns a frozen `SendResult(message_id, date, refused)`, the same shape on every backend.
A recipient the service refused while accepting the rest rides on the send result instead of raising.
Every failure is one of seven flat subclasses of `EpistoleError`, with the native exception as `__cause__`, and only `ThrottledError` carries `retry_after`.
Decided on [#12](https://github.com/ozanozbeker/epistole/issues/12) as `Receipt`, renamed `SendResult` on [#14](https://github.com/ozanozbeker/epistole/issues/14) because the owner read "receipt" as a delivery receipt, and grounded by the send-boundary research in `docs/research/send-boundary-semantics.md`.
Amended on [#26](https://github.com/ozanozbeker/epistole/issues/26) with the `SMTPUTF8` row of the SMTP mapping, which ADR-0014 left unmapped by deciding not to check an address's character set.
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): `Connection.send` builds every send result, from the submission it stamped plus the refusals `Transport.submit` returns, so no transport constructs one (ADR-0015).
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): the mapping tables gain a precedence rule and a fallback row each, and `421` overrides every SMTP class row.
The same issue moved `SMTPRecipientsRefused` off the table as refusal data, mapped `552` on MAIL FROM to `RejectedError`, gave the leaves constructors, and made `retry_after` conditional on the header rather than hard-coded per backend.

## Why

**The send result.**
Graph answers `202` with no body, Gmail returns a mailbox-local id that is not an RFC 5322 `Message-ID`, and `smtplib` discards the SMTP queue id.
The only identifier that exists on all three is the `Message-ID` that `send` stamps on each submission (ADR-0002), so the send result carries that and nothing provider-specific.
It is never `None`, because Epistole wrote it.
Whether Gmail and Graph preserve it on the wire is still the live-test question on #2, and the answer does not change the send result: the id names the submission Epistole made either way.
The prototype's `accepted`, `backend`, and `retry_after` fields are gone.
A returned send result means accepted, the caller called `send` on the backend or connection and knows which, and a retry hint only means something on a failure.

**Refusals ride on the send result.**
`smtplib.sendmail` raises only when every recipient is refused.
One refused out of three returns normally with a one-entry dict, and the message has already gone to the other two.
Raising after that side effect would force every caller to catch in order to learn who received the mail.
A warning is invisible in production logs.
So a partial refusal is a fact about an accepted submission, and the send result is where it lives.
Every recipient refused is a different case: nothing was submitted, and that raises.

**Only what SMTP reports, not a per-recipient status.**
Anymail gives every recipient one of six states because its ESPs report per-recipient outcomes richly.
Epistole's backends do not: Gmail and Graph report nothing per recipient, and SMTP reports refusals only.
A six-state enum where two backends emit one constant and the third emits two promises information Epistole does not have, and its `sent` versus `queued` split is the "success is not delivery" trap with a name.
`refused` maps an address to a `Refusal(code, reason)`, is always empty on the two APIs, and the docstring says so.
A Graph recipient typo arrives later as a non-delivery report in the sender's inbox, and Epistole never sees it.

**One root, not `OSError`.**
`smtplib.SMTPException` subclasses `OSError`.
Copying that would let an `except OSError` around unrelated file code swallow a mail failure.
`EpistoleError` subclasses `Exception` and carries `backend`, the backend object the failure came from.
A transport has no backend to name, because it receives a `Submission` and nothing else (ADR-0015), so the leaf is raised without one and the caller stamps it on the way out.
The native exception is reachable as `__cause__`, raised with `from`, and there is no duplicate `original` attribute.
For the HTTP backends the cause is whatever the transport layer raised, so the status and body stay reachable through it; #16 owns that layer.

**Flat, no transient layer.**
The transient set is exactly `ThrottledError | TransportError | ProviderError`, and a retry loop writes that tuple.
A `TransientError` base would add a second axis to remember, and Gmail's `403` shows the two axes do not nest: the same status is permanent under `domainPolicy` and transient under `rateLimitExceeded`.
A `transient` property on the base is additive if it is ever wanted.

**`retry_after` on one class.**
Graph documents `Retry-After` on `429`, `503`, and `409`.
Gmail promises "a time to retry" without naming a header and then prescribes backoff.
SMTP has nothing.
Putting the hint on the base would make it `None` almost everywhere.
It lives on `ThrottledError` alone, as `float | None` seconds, so retry code is `except ThrottledError as e: sleep(e.retry_after or backoff)`.
The cost is one dropped hint on a Graph `503`, which maps to `ProviderError` without it.
Gmail's `dailyLimitExceeded` is a quota, not the message, so it is `ThrottledError` rather than an eighth class.
Naming no header is a reason to read one when it arrives, not a reason to discard it, so `retry_after` follows the response on both HTTP backends rather than being fixed per backend.
Epistole never sleeps and never retries.

## Rules

- **`SendResult` is frozen and has three fields.**
  `message_id` and `date`, the `Message-ID` and `Date` `send` stamped, and `refused`, a mapping of address to `Refusal(code, reason)`.
  `Connection.send` is the only place one is constructed, and `Refusal` is public because `MemoryBackend(refuse=...)` takes one (ADR-0015).
- **`refused` is keyed by the caller's recipient string.**
  A transport answers with addr-spec keys, because that is what the service named and what `smtplib` hands back.
  `Connection.send` re-keys each one to the matching entry of `submission.message.recipients` before it builds the send result, so `refused` compares directly against what the caller wrote and a display-name address is not silently missed.
  Two recipients sharing an addr-spec resolve to the first in `recipients` order.
  `reason` is text, never bytes: `smtplib` answers in `bytes`, decoded as UTF-8 with `errors="replace"`.
- **Seven leaves under `EpistoleError`.**

  | Class | Meaning |
  | --- | --- |
  | `RejectedError` | the service refused the message or request as invalid; permanent |
  | `SenderRefusedError` | the service will not send as the backend's from address |
  | `RecipientsRefusedError` | every recipient refused, nothing submitted; carries `refused` |
  | `AuthenticationError` | credential rejected or permission insufficient |
  | `ThrottledError` | the provider asked for a slower rate; carries `retry_after` |
  | `TransportError` | connect, TLS, disconnect, timeout |
  | `ProviderError` | the provider's own `5xx`, or a reply the mapper does not know |

  Sender and recipients refused stay apart from `RejectedError` because the fix is different: an administrator's grant or the address list, not the message content.
- **A leaf takes a message positionally and its extras keyword-only.**
  `EpistoleError(message, /, *, backend=None)`, `RecipientsRefusedError(message, /, *, refused, backend=None)`, and `ThrottledError(message, /, *, retry_after=None, backend=None)`; the other four inherit the base.
  `raise SomeLeaf("text")` stays the shape every Python exception has.
- **The raise site does not fill `backend`; the caller stamps it.**
  A transport raises the mapped leaf with `backend` unset, and `Connection.send` and `Backend.connect()` each catch `EpistoleError`, set `backend` to their own, and re-raise (ADR-0005).
  So `backend` is set on every error that reaches a caller, and `None` only on a leaf inspected before it has propagated.
  `backend` is therefore a plain mutable attribute rather than a constructor-only field.
- **Who said no decides the class.**
  A mistake Epistole finds before touching the wire, such as no recipients, `send` on a closed connection, or a `cid:` with no inline image behind it, is a `TypeError` or `ValueError`, never a `EpistoleError`.
  A backend-local limit checked before writing, such as Graph's 150 MB attachment ceiling or its 500-recipient limit, is `RejectedError` with `__cause__` `None`, because the same message succeeds on SMTP and the caller should see one class whether Epistole or the service noticed first.
- **`__cause__` is `None` on any check Epistole ran itself**, before the wire or after it.
  A backend pre-check and the every-recipient-refused check in `Connection.send` both raise with no native exception behind them.
- **Precedence, and a fallback on every table.**
  A code- or reason-qualified row beats a bare status row, which beats a class row.
  An unmatched status or reason is `ProviderError`, on all three tables and not Graph's alone, and the mapper never raises on its own.
- **`421` overrides every SMTP row.**
  A reply code of `421` in any native exception is `TransportError`, whatever class carried it, because `smtplib` closes the socket on `421` at MAIL FROM, at RCPT, and at DATA, raising `SMTPSenderRefused`, `SMTPRecipientsRefused`, and `SMTPDataError` respectively.
  Reporting any of those as something that leaves the connection open would hand the caller a live connection over a dead socket.
- **Mapping.**
  Everything else on SMTP classifies on `smtp_code // 100`, per RFC 5321.

  | SMTP native | Epistole |
  | --- | --- |
  | any exception carrying `421` | `TransportError` |
  | `SMTPSenderRefused` `552` | `RejectedError` |
  | `SMTPSenderRefused`, any other code | `SenderRefusedError` |
  | `SMTPAuthenticationError`, `SMTPNotSupportedError` from `login` or `auth` | `AuthenticationError` |
  | `SMTPNotSupportedError` from `send_message`, meaning a non-ASCII address and no `SMTPUTF8` | `RejectedError` (ADR-0014) |
  | `SMTPConnectError`, `SMTPHeloError`, `SMTPServerDisconnected`, `OSError`, `ssl` errors | `TransportError` |
  | `SMTPDataError` `5yz` | `RejectedError` |
  | `SMTPDataError` `4yz` | `ProviderError` |
  | any other `SMTPResponseException` | `RejectedError` on `5yz`, `ProviderError` otherwise |
  | a bare `SMTPException` | `ProviderError` |

  `SMTPRecipientsRefused` has no row.
  `SMTPTransport` catches it and answers with its `.recipients` as ordinary refusal data, and `Connection.send` raises `RecipientsRefusedError` when every recipient was refused, so the rule holds on every backend including the doubles (ADR-0015).
  `552` on MAIL FROM is the server refusing the message against its advertised `SIZE`, which is a fact about the message and not about the from address, so it cannot share a row with a genuine sender refusal.
  SMTP never raises `ThrottledError`: the protocol cannot tell a throttle from a hiccup, and `421` or `45x` is a blind back-off.

  | Gmail status and `errors[].reason` | Epistole |
  | --- | --- |
  | `400`, `404`, `403 domainPolicy` | `RejectedError` |
  | `401`, `403 authError`, `403 insufficientPermissions`, any other `403` | `AuthenticationError` |
  | `403 rateLimitExceeded`, `403 userRateLimitExceeded`, `403 dailyLimitExceeded`, `429` | `ThrottledError` |
  | `5xx` | `ProviderError` |
  | network failure | `TransportError` |

  Gmail's catch-all `403` mirrors Graph's, because a `403` is permanent and permission-shaped, which is what `AuthenticationError` means.
  Letting it fall to the table's `ProviderError` fallback would put a permanent failure in the transient set and spin a retry loop on it.

  | Graph status and `error.code` | Epistole |
  | --- | --- |
  | `400` (including `ErrorMimeContentInvalidBase64String`), `404`, `413`, `415` | `RejectedError` |
  | `401`, any other `403` | `AuthenticationError` |
  | `403 ErrorSendAsDenied` | `SenderRefusedError` |
  | `429` | `ThrottledError` |
  | `409`, `500`, `503`, `504`, `509` | `ProviderError` |
  | network failure | `TransportError` |

  A client-side timeout is the `httpx2.TransportError` subclass and so `TransportError`; a `504` is a status the service returned and so `ProviderError`.
  The two are different failures that read alike in prose.
- **`Retry-After` parses both RFC 9110 forms.**
  `delta-seconds` as given, and an HTTP-date as seconds from now.
  `ThrottledError.retry_after` carries the parsed value whenever the response has the header, and is `None` otherwise, on both HTTP backends.

## Considered options

- **Return `None`.**
  Throws away the one identifier that exists on all three backends.
- **Return an optional provider id.**
  Present on Gmail only, and not an RFC 5322 id there either.
  Useless to backend-agnostic code.
- **Raise on any refused recipient.**
  The message already went to the accepted recipients, so the exception has to carry the send result anyway, and every caller has to catch to read it.
- **Per-recipient status, as Anymail.**
  Rejected above: it promises detail two of three backends cannot supply.
- **A `transient` base class or mixin.**
  Rejected above; the axes do not nest on Gmail.
- **`retry_after` on `EpistoleError`.**
  Rejected above; `None` almost everywhere.

## Consequences

- A caller who ignores the send result loses SMTP refusals silently.
  The docstring on `send` and the SMTP backend say so.
  Anymail made the same trade.
- A Graph recipient typo is never an error Epistole can raise.
  The documentation says where to look.
- `RecipientsRefusedError.refused` and `SendResult.refused` share the `Refusal` type, so code that reads one reads the other.
- [#13](https://github.com/ozanozbeker/epistole/issues/13) maps connection-lifecycle failures onto `TransportError` and `AuthenticationError`; no new class is needed.
- [#14](https://github.com/ozanozbeker/epistole/issues/14) settled the spellings: `SendResult`, `Refusal`, and the seven class names as written here.
- [#16](https://github.com/ozanozbeker/epistole/issues/16) decides what `__cause__` is on the HTTP backends; the contract here is only that it is the transport's own exception.
- [#17](https://github.com/ozanozbeker/epistole/issues/17) can add an unsupported-feature leaf; the hierarchy is flat, so nothing here forecloses it.
- What Gmail does when the `From` header names neither the account nor a verified alias needs a real send, so its mapping is unknown until implementation.
  Rewrite, reject, and send-as-given each land on a different leaf above; ADR-0001 carries the same open question from the sender-identity side.

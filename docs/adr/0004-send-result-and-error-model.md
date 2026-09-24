# `send` returns a send result and does not raise for a partial refusal

None of the three backends returns a message id Epistole could return on all three.
So `send` returns the id Epistole wrote.
`send` returns a frozen `SendResult(message_id, date, refused)`, the same shape on every backend.
When the service refuses a recipient and accepts the rest, the send result holds the refusal and nothing raises.
Every failure is one of seven flat subclasses of `EpistoleError`, with the native exception as `__cause__`.
Only `ThrottledError` carries `retry_after`.
Decided on [#12](https://github.com/ozanozbeker/epistole/issues/12) as `Receipt`.
The type became `SendResult` on [#14](https://github.com/ozanozbeker/epistole/issues/14), because the owner read "receipt" as a delivery receipt.
The decision is based on the send-boundary research in `docs/research/send-boundary-semantics.md`.
Amended on [#26](https://github.com/ozanozbeker/epistole/issues/26) with the `SMTPUTF8` row of the SMTP mapping.
ADR-0014 decided not to check an address's character set, which left that case unmapped.
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): `Connection.send` builds every send result from the submission it built plus the refusals `Transport.submit` returns.
No transport constructs one (ADR-0015).
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): the mapping tables gain a precedence rule and a fallback row each.
`421` overrides every SMTP class row.
The same issue moved `SMTPRecipientsRefused` off the table, as refusal data.
It mapped `552` on MAIL FROM to `RejectedError`.
It gave the leaves constructors.
It made `retry_after` conditional on the header rather than hard-coded per backend.
Amended on [#43](https://github.com/ozanozbeker/epistole/issues/43): a bare `SMTPException` from `login` or `auth` is `AuthenticationError`, and SMTP names each addr-spec once in its envelope.

## Why

**The send result carries the id Epistole wrote.**
Graph returns `202` with no body.
Gmail returns a mailbox-local id that is not an RFC 5322 `Message-ID`.
`smtplib` discards the SMTP queue id.
The only identifier that exists on all three is the `Message-ID` that `send` sets on each submission (ADR-0002).
So the send result carries that and nothing provider-specific.
It is never `None`, because Epistole wrote it.
Whether Gmail and Graph keep it in the sent message is still the live-test question on #2.
The answer does not change the send result: the id names the submission Epistole made either way.
The prototype's `accepted`, `backend`, and `retry_after` fields are gone.
A returned send result means accepted.
The caller called `send` on the backend or connection, and knows which.
A retry hint only means something on a failure.

**The send result holds refusals.**
`smtplib.sendmail` raises only when the server refuses every recipient.
With one of three refused, it returns normally with a one-entry dict.
The message has already gone to the other two.
Raising after that side effect would force every caller to catch an exception to read who received the mail.
A warning is invisible in production logs.
So a partial refusal is a fact about an accepted submission.
The send result holds it.
Every recipient refused is a different case: nothing was submitted, so `send` raises.

**The send result holds only what SMTP reports, not a per-recipient status.**
Anymail gives every recipient one of six states because its ESPs report per-recipient outcomes richly.
Epistole's backends do not.
Gmail and Graph report nothing per recipient, and SMTP reports refusals only.
A six-state enum would imply information Epistole does not have: two backends emit one constant, and the third emits two.
Its `sent` versus `queued` split turns the "success is not delivery" hazard into two named states.
`refused` maps an address to a `Refusal(code, reason)`.
It is always empty on the two APIs, and the docstring says so.
On Graph, a recipient typo produces a non-delivery report later, in the inbox of the from address.
Epistole never receives it.

**`EpistoleError` is the one root, not `OSError`.**
`smtplib.SMTPException` subclasses `OSError`.
Copying that would let an `except OSError` around unrelated file code catch a mail failure.
`EpistoleError` subclasses `Exception`.
It carries `backend`, the backend object the failure came from.
A transport has no backend to name, because it receives a `Submission` and nothing else (ADR-0015).
So the transport raises the error without one, and the caller sets it before re-raising.
Epistole raises with `from`, so the native exception is reachable as `__cause__`.
There is no duplicate `original` attribute.
For the HTTP backends, the cause is whatever the transport layer raised, so the status and body stay reachable through it.
#16 owns that layer.

**The hierarchy is flat, with no transient layer.**
The transient set is exactly `ThrottledError | TransportError | ProviderError`.
A retry loop writes that tuple.
A `TransientError` base would add a second axis to remember.
Gmail's `403` shows the two axes do not nest: the same status is permanent under `domainPolicy` and transient under `rateLimitExceeded`.
A `transient` property on the base is additive if it is ever wanted.

**`retry_after` is on one class.**
Graph documents `Retry-After` on `429`, `503`, and `409`.
Gmail's documentation promises "a time to retry" without naming a header.
It then prescribes backoff.
SMTP has nothing.
Putting the hint on the base would make it `None` almost everywhere.
It is defined on `ThrottledError` alone, as `float | None` seconds.
So retry code is `except ThrottledError as e: sleep(e.retry_after or backoff)`.
The cost is one dropped hint on a Graph `503`, which maps to `ProviderError` without it.
Gmail's `dailyLimitExceeded` is a quota, not the message, so it is `ThrottledError` rather than an eighth class.
Naming no header is a reason to read one when a response carries it, not a reason to discard it.
So Epistole reads `retry_after` from the response on both HTTP backends rather than fixing it per backend.
Epistole never sleeps and never retries.

## Rules

- **`SendResult` is frozen and has three fields.**
  `message_id` and `date` hold the `Message-ID` and `Date` `send` set.
  `refused` is a mapping of address to `Refusal(code, reason)`.
  Only `Connection.send` constructs one.
  `Refusal` is public because `MemoryBackend(refuse=...)` takes one (ADR-0015).
- **`refused` is keyed by the caller's recipient string.**
  A transport returns addr-spec keys, because the service named those and `smtplib` returns them.
  `Connection.send` re-keys each one to the matching entry of `submission.message.recipients` before it builds the send result.
  So `refused` compares directly against what the caller wrote, and a display-name address is not silently missed.
  Two recipients sharing an addr-spec resolve to the first in `recipients` order.
  `reason` is text, never bytes.
  `smtplib` returns `bytes`, and Epistole decodes them as UTF-8 with `errors="replace"`.
- **Seven error classes subclass `EpistoleError`.**

  | Class | Meaning |
  | --- | --- |
  | `RejectedError` | the service refused the message or request as invalid; permanent |
  | `SenderRefusedError` | the service will not send as the backend's from address |
  | `RecipientsRefusedError` | every recipient refused, nothing submitted; carries `refused` |
  | `AuthenticationError` | credential rejected or permission insufficient |
  | `ThrottledError` | the provider returned a rate limit; carries `retry_after` |
  | `TransportError` | connect, TLS, disconnect, timeout |
  | `ProviderError` | the provider's own `5xx`, or a reply the mapper has no row for |

  `SenderRefusedError` and `RecipientsRefusedError` stay apart from `RejectedError` because the fix is different: an administrator's grant or the address list, not the message content.
- **Each takes a message positionally and its extras keyword-only.**
  The signatures are `EpistoleError(message, /, *, backend=None)`, `RecipientsRefusedError(message, /, *, refused, backend=None)`, and `ThrottledError(message, /, *, retry_after=None, backend=None)`.
  The other four inherit the base.
  `raise RejectedError("text")` stays the shape every Python exception has.
- **The raise site does not fill `backend`.
  The caller sets it.**
  A transport raises the mapped error with `backend` unset.
  `Connection.send` and `Backend.connect()` each catch `EpistoleError`, set `backend` to their own, and re-raise (ADR-0005).
  So `backend` is set on every error that reaches a caller, and `None` only on an error inspected before it has propagated.
  `backend` is therefore a plain mutable attribute rather than a constructor-only field.
- **The class depends on which party rejected the send.**
  A mistake Epistole finds before it writes to the network is a `TypeError` or `ValueError`, never an `EpistoleError`.
  Examples are no recipients, `send` on a closed connection, or a `cid:` with no matching inline image.
  A backend-local limit checked before writing is `RejectedError` with `__cause__` `None`.
  Examples are Graph's 150 MB attachment limit and its 500-recipient limit.
  The class is `RejectedError` because the same message succeeds on SMTP, and the caller should get one class whether Epistole or the service rejects it first.
- **`__cause__` is `None` on any check Epistole ran itself**, before any network call or after one.
  A backend pre-check and the every-recipient-refused check in `Connection.send` both raise with no native exception as the cause.
- **Every table has a precedence rule and a fallback.**
  A code- or reason-qualified row takes precedence over a bare status row, which takes precedence over a class row.
  An unmatched status or reason is `ProviderError`, on all three tables and not Graph's alone.
  The mapper never raises on its own.
- **`421` overrides every SMTP row.**
  A reply code of `421` in any native exception is `TransportError`, whatever class carried it.
  `smtplib` closes the socket on `421` at MAIL FROM, at RCPT, and at DATA.
  It raises `SMTPSenderRefused`, `SMTPRecipientsRefused`, and `SMTPDataError` there, respectively.
  Reporting any of those as something that leaves the connection open would give the caller an open connection over a closed socket.
- **These tables map native failures to Epistole classes.**
  Epistole classifies everything else on SMTP by `smtp_code // 100`, per RFC 5321.

  | SMTP native | Epistole |
  | --- | --- |
  | any exception carrying `421` | `TransportError` |
  | `SMTPSenderRefused` `552` | `RejectedError` |
  | `SMTPSenderRefused`, any other code | `SenderRefusedError` |
  | `SMTPAuthenticationError`, `SMTPNotSupportedError` or a bare `SMTPException` from `login` or `auth` | `AuthenticationError` |
  | `SMTPNotSupportedError` from `send_message`, meaning a non-ASCII address and no `SMTPUTF8` | `RejectedError` (ADR-0014) |
  | `SMTPConnectError`, `SMTPHeloError`, `SMTPServerDisconnected`, `OSError`, `ssl` errors | `TransportError` |
  | `SMTPDataError` `5yz` | `RejectedError` |
  | `SMTPDataError` `4yz` | `ProviderError` |
  | any other `SMTPResponseException` | `RejectedError` on `5yz`, `ProviderError` otherwise |
  | any other bare `SMTPException` | `ProviderError` |

  `SMTPRecipientsRefused` has no row.
  `SMTPTransport` catches it and returns its `.recipients` as ordinary refusal data.
  `Connection.send` raises `RecipientsRefusedError` when every recipient was refused.
  So the rule holds on every backend, including the doubles (ADR-0015).
  `smtplib` raises `SMTPRecipientsRefused` only when its refusals number as many as the envelope's recipients.
  A repeated addr-spec breaks that count, so `smtplib` sends `DATA` anyway and raises on the server's reply.
  So `SMTPTransport` names each addr-spec once.
  `login` raises a bare `SMTPException` when `smtplib` supports none of the server's mechanisms, such as a server that offers only NTLM.
  No retry changes that, so it is `AuthenticationError`, as the catch-all Gmail `403` below is.
  As a `ProviderError` it would be in the transient set.
  A retry loop would then repeat it.
  `552` on MAIL FROM is the server refusing the message against its advertised `SIZE`.
  That is a fact about the message and not about the from address.
  So it cannot share a row with a genuine refusal of the from address.
  On SMTP, Epistole never raises `ThrottledError`.
  The protocol does not distinguish a throttle from a transient fault.
  `421` or `45x` means back off, with no delay given.

  | Gmail status and `errors[].reason` | Epistole |
  | --- | --- |
  | `400`, `404`, `403 domainPolicy` | `RejectedError` |
  | `401`, `403 authError`, `403 insufficientPermissions`, any other `403` | `AuthenticationError` |
  | `403 rateLimitExceeded`, `403 userRateLimitExceeded`, `403 dailyLimitExceeded`, `429` | `ThrottledError` |
  | `5xx` | `ProviderError` |
  | network failure | `TransportError` |

  Gmail's catch-all `403` row matches Graph's.
  A `403` is permanent and permission-shaped, and `AuthenticationError` means exactly that.
  Leaving it to the table's `ProviderError` fallback would put a permanent failure in the transient set.
  A retry loop would then keep retrying it.

  | Graph status and `error.code` | Epistole |
  | --- | --- |
  | `400` (including `ErrorMimeContentInvalidBase64String`), `404`, `413`, `415` | `RejectedError` |
  | `401`, any other `403` | `AuthenticationError` |
  | `403 ErrorSendAsDenied` | `SenderRefusedError` |
  | `429` | `ThrottledError` |
  | `409`, `500`, `503`, `504`, `509` | `ProviderError` |
  | network failure | `TransportError` |

  A client-side timeout is the `httpx2.TransportError` subclass, so it is `TransportError`.
  A `504` is a status the service returned, so it is `ProviderError`.
  The two are different failures that read alike in prose.
- **Epistole parses both RFC 9110 forms of `Retry-After`.**
  It takes `delta-seconds` as given, and converts an HTTP-date to seconds from now.
  On both HTTP backends, `ThrottledError.retry_after` carries the parsed value whenever the response has the header.
  It is `None` otherwise.

## Considered options

- **Return `None`.**
  It discards the one identifier that exists on all three backends.
- **Return an optional provider id.**
  The id exists on Gmail only, and is not an RFC 5322 id there either.
  Backend-agnostic code cannot use it.
- **Raise on any refused recipient.**
  The message already went to the accepted recipients, so the exception has to carry the send result anyway.
  Every caller has to catch the exception to read it.
- **Report a per-recipient status, as Anymail does.**
  Rejected above: it implies detail that two of three backends cannot supply.
- **Add a `transient` base class or mixin.**
  Rejected above: the axes do not nest on Gmail.
- **Put `retry_after` on `EpistoleError`.**
  Rejected above: it would be `None` almost everywhere.

## Consequences

- A caller who ignores the send result loses SMTP refusals silently.
  The docstring on `send` and the SMTP backend say so.
  Anymail made the same trade.
- A Graph recipient typo is never an error Epistole can raise.
  The documentation says where to look.
- `RecipientsRefusedError.refused` and `SendResult.refused` share the `Refusal` type, so code that reads one reads the other.
- [#13](https://github.com/ozanozbeker/epistole/issues/13) maps connection-lifecycle failures onto `TransportError` and `AuthenticationError`.
  No new class is needed.
- [#14](https://github.com/ozanozbeker/epistole/issues/14) settled the spellings: `SendResult`, `Refusal`, and the seven class names as written here.
- [#16](https://github.com/ozanozbeker/epistole/issues/16) decides what `__cause__` is on the HTTP backends.
  The contract here is only that it is the transport's own exception.
- [#17](https://github.com/ozanozbeker/epistole/issues/17) can add an unsupported-feature class.
  The hierarchy is flat, so nothing here prevents it.
- Only a real send shows what Gmail does when the `From` header names neither the account nor a verified alias.
  So its mapping is unknown until implementation.
  Rewrite, reject, and send-as-given each map to a different class above.
  ADR-0001 records the same open question for the from address.

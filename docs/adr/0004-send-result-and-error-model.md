# A send returns a send result, and refusals do not raise

No backend hands back a message id Herma can return on all three, so `send` returns the id Herma wrote.
`send` returns a frozen `SendResult(message_id, date, refused)`, the same shape on every backend.
A recipient the service refused while accepting the rest rides on the send result instead of raising.
Every failure is one of seven flat subclasses of `HermaError`, with the native exception as `__cause__`, and only `ThrottledError` carries `retry_after`.
Decided on [#12](https://github.com/ozanozbeker/herma/issues/12) as `Receipt`, renamed `SendResult` on [#14](https://github.com/ozanozbeker/herma/issues/14) because the owner read "receipt" as a delivery receipt, and grounded by the send-boundary research in `docs/research/send-boundary-semantics.md`.

## Why

**The send result.**
Graph answers `202` with no body, Gmail returns a mailbox-local id that is not an RFC 5322 `Message-ID`, and `smtplib` discards the SMTP queue id.
The only identifier that exists on all three is the `Message-ID` that `send` stamps on each submission (ADR-0002), so the send result carries that and nothing provider-specific.
It is never `None`, because Herma wrote it.
Whether Gmail and Graph preserve it on the wire is still the live-test question on #2, and the answer does not change the send result: the id names the submission Herma made either way.
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
Herma's backends do not: Gmail and Graph report nothing per recipient, and SMTP reports refusals only.
A six-state enum where two backends emit one constant and the third emits two promises information Herma does not have, and its `sent` versus `queued` split is the "success is not delivery" trap with a name.
`refused` maps an address to a `Refusal(code, reason)`, is always empty on the two APIs, and the docstring says so.
A Graph recipient typo arrives later as a non-delivery report in the sender's inbox, and Herma never sees it.

**One root, not `OSError`.**
`smtplib.SMTPException` subclasses `OSError`.
Copying that would let an `except OSError` around unrelated file code swallow a mail failure.
`HermaError` subclasses `Exception` and carries `backend`, the backend object the failure came from, or `None` when `send` raised before the transport's `submit`.
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
Gmail's `dailyLimitExceeded` is a quota, not the message, so it is `ThrottledError` with `retry_after=None` rather than an eighth class.
Herma never sleeps and never retries.

## Rules

- **`SendResult` is frozen and has three fields.**
  `message_id` and `date`, the `Message-ID` and `Date` `send` stamped, and `refused`, a mapping of address to `Refusal(code, reason)`.
  `reason` is text, never bytes.
- **Seven leaves under `HermaError`.**

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
- **Who said no decides the class.**
  A mistake Herma finds before touching the wire, such as no recipients, `send` on a closed connection, or a `cid:` with no inline image behind it, is a `TypeError` or `ValueError`, never a `HermaError`.
  A backend-local limit checked before writing, such as Graph's 4 MB body or 500 recipients, is `RejectedError` with `__cause__` `None`, because the same message succeeds on SMTP and the caller should see one class whether Herma or the service noticed first.
- **Mapping.**
  SMTP classifies on `smtp_code // 100`, per RFC 5321.

  | SMTP native | Herma |
  | --- | --- |
  | `SMTPRecipientsRefused` | `RecipientsRefusedError`, `refused` from `.recipients` |
  | `SMTPSenderRefused` | `SenderRefusedError` |
  | `SMTPAuthenticationError`, `SMTPNotSupportedError` from `login` or `auth` | `AuthenticationError` |
  | `SMTPConnectError`, `SMTPHeloError`, `SMTPServerDisconnected`, `421`, `OSError`, `ssl` errors | `TransportError` |
  | `SMTPDataError` `5yz` | `RejectedError` |
  | `SMTPDataError` `4yz` | `ProviderError` |

  SMTP never raises `ThrottledError`: the protocol cannot tell a throttle from a hiccup, and `421` or `45x` is a blind back-off.

  | Gmail status and `errors[].reason` | Herma |
  | --- | --- |
  | `400`, `404`, `403 domainPolicy` | `RejectedError` |
  | `401`, `403 authError`, `403 insufficientPermissions` | `AuthenticationError` |
  | `403 rateLimitExceeded`, `403 userRateLimitExceeded`, `403 dailyLimitExceeded`, `429` | `ThrottledError`, `retry_after=None` |
  | `5xx` | `ProviderError` |
  | network failure | `TransportError` |

  | Graph status and `error.code` | Herma |
  | --- | --- |
  | `400` (including `ErrorMimeContentInvalidBase64String`), `404`, `413`, `415` | `RejectedError` |
  | `401`, other `403` | `AuthenticationError` |
  | `403 ErrorSendAsDenied` | `SenderRefusedError` |
  | `429` | `ThrottledError`, `retry_after` from `Retry-After` |
  | `409`, `500`, `503`, `504`, `509` | `ProviderError` |
  | network failure | `TransportError` |

  An unmapped status or reason is `ProviderError`; the mapper never raises on its own.
- **`Retry-After` parses both RFC 9110 forms.**
  `delta-seconds` as given, and an HTTP-date as seconds from now.

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
- **`retry_after` on `HermaError`.**
  Rejected above; `None` almost everywhere.

## Consequences

- A caller who ignores the send result loses SMTP refusals silently.
  The docstring on `send` and the SMTP backend say so.
  Anymail made the same trade.
- A Graph recipient typo is never an error Herma can raise.
  The documentation says where to look.
- `RecipientsRefusedError.refused` and `SendResult.refused` share the `Refusal` type, so code that reads one reads the other.
- [#13](https://github.com/ozanozbeker/herma/issues/13) maps connection-lifecycle failures onto `TransportError` and `AuthenticationError`; no new class is needed.
- [#14](https://github.com/ozanozbeker/herma/issues/14) settled the spellings: `SendResult`, `Refusal`, and the seven class names as written here.
- [#16](https://github.com/ozanozbeker/herma/issues/16) decides what `__cause__` is on the HTTP backends; the contract here is only that it is the transport's own exception.
- [#17](https://github.com/ozanozbeker/herma/issues/17) can add an unsupported-feature leaf; the hierarchy is flat, so nothing here forecloses it.
- What Gmail does when the `From` header names neither the account nor a verified alias stays fog on [#2](https://github.com/ozanozbeker/herma/issues/2), and its mapping is unknown until a live send.

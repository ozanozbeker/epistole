# Send-boundary semantics across SMTP, Gmail, and Graph

Research for [issue #3](https://github.com/ozanozbeker/epistole/issues/3), checked 2026-09-07.
Every claim cites a primary source: Microsoft Learn, Google's developer documentation, the Python documentation, the CPython 3.13 source, or a published RFC.
Where a source is silent or two sources disagree, the text says so instead of guessing.

**Amended 2026-09-09 under [#22](https://github.com/ozanozbeker/epistole/issues/22).**
Four claims were wrong and are corrected in place: three about Graph's 4 MB cap, which this file recorded as S/MIME-specific and undocumented, and one about SMTP AUTH's authorization model, which this file recorded as absent.
One addition: `Mail.ReadWrite` has a second, independent trigger above 3 MB of attachment.
The corrections were first raised on [this comment on #3](https://github.com/ozanozbeker/epistole/issues/3#issuecomment-5589707723) and re-verified against the sources on 2026-09-09.
Amended passages are marked **Corrected 2026-09-09**.

## What this means for epistole

**`send()` cannot return a provider message id.**
Graph answers `202 Accepted` with an empty body, and the claim in the issue is correct.
`smtplib` throws away the server's `DATA` response text on success.
Only Gmail returns an id, and it is a Gmail-mailbox-local string, not an RFC 5322 `Message-ID`.
Two of three backends have nothing to return.

**The only identifier available on all three is the one epistole generates.**
RFC 5322 makes the message author responsible for `Message-ID` uniqueness.
If epistole sets `Message-ID` before serializing, it can return that value on every backend without asking the provider for anything.
This is unverified in one respect: neither Gmail nor Graph documents whether it preserves a client-supplied `Message-ID`, and Graph's JSON path almost certainly does not.
Test this before committing to it.

**Success means "accepted for submission", never "delivered".**
All three sources say so explicitly, and Gmail says it loudest: "You can't assume that a 200 response means the email was successfully sent."
Name the return type for what it is.
A `SendReceipt` or `Accepted` reads honestly; a `SentMessage` does not.

**SMTP has a fourth outcome the two APIs do not: partial acceptance.**
`SMTP.sendmail` returns a dict of refused recipients and does not raise when at least one recipient was accepted.
Neither Gmail nor Graph can express this.
Whatever `send()` returns needs a slot for per-recipient refusals that is empty on the API backends.

**`retry_after` must be optional.**
Graph documents a `Retry-After` header on `429` and `503` and tells you to obey it.
Gmail's error guide never mentions the header; it prescribes exponential backoff starting at one second.
Model `retry_after` as `float | None` and fall back to backoff when it is absent.

**Permanent versus transient is derivable everywhere, by three different rules.**
Graph: HTTP status plus the machine-readable `error.code`.
Gmail: HTTP status plus `error.errors[].reason`.
SMTP: the first digit of the reply code, per RFC 5321.
The exception hierarchy should carry a `transient: bool` that each backend computes, rather than making callers match on backend-specific codes.

**Sender identity is pinned to the authenticated mailbox on all three.**
Overriding it is a server-side grant that an administrator makes, not a request field epistole can simply fill in.
Graph returns `403 ErrorSendAsDenied` when the grant is missing.
An honest API exposes `from_` and lets the backend fail, rather than promising it works.

**The tightest sending quotas sit below the API and do not surface as errors.**
Exchange Online enforces 30 messages per minute and 10,000 recipients per day at the transport layer, after the `202`.
Failures there arrive as a non-delivery report in the sender's Inbox, not as an HTTP status. epistole cannot report them, and the documentation should say that plainly.

## Comparison

| Aspect | SMTP (`smtplib`) | Gmail API | Microsoft Graph |
| --- | --- | --- | --- |
| Send call | `SMTP.send_message(msg)` over `MAIL`/`RCPT`/`DATA` | `POST /gmail/v1/users/{userId}/messages/send` | `POST /me/sendMail` or `POST /users/{id}/sendMail` |
| Payload | RFC 5322 bytes, `\r\n` line endings | JSON `Message` with `raw` = base64url RFC 5322 | JSON `{message, saveToSentItems}` or base64 MIME as `text/plain` |
| Max size | Server `SIZE` extension | 36,700,160 bytes (35 MiB) via the upload endpoint | 4 MB per write request, with `message.body.content` inside it |
| Success | Reply `250` after `DATA` | `200 OK` | `202 Accepted` |
| Success body | Reply text, discarded by `smtplib` | `Message` with `id`, `threadId`, `labelIds` | Empty |
| Message id | None reachable | `id`, immutable, mailbox-scoped | None |
| Error shape | Exception subclass with `smtp_code` and `smtp_error` | `error.code`, `error.message`, `error.errors[].reason` | `error.code`, `error.message`, `error.innererror` |
| Transient signal | Reply code `4yz` | `429`, `5xx`, and `403` with a rate-limit reason | `429`, `503`, `509`, `5xx` |
| Retry hint | None in the protocol | Not documented | `Retry-After` header |
| Partial failure | Yes, dict of refused recipients | No | No |
| From address | Envelope and header set independently; server policy decides | Pinned to the account; aliases need verification | Pinned to the mailbox; `from` override needs a Send As or Send on Behalf grant |
| Least-privilege credential | none in `smtplib`; Exchange Online scopes it with the `Application SMTP.SendAsApp` RBAC role | `https://www.googleapis.com/auth/gmail.send` | `Mail.Send`, plus `Mail.ReadWrite` above 3 MB of attachment |

Each row is cited in the per-backend sections below.

## SMTP via `smtplib` and `email`

### SMTP request shape

`SMTP.send_message(msg, from_addr=None, to_addrs=None, mail_options=(), rcpt_options=())` takes an `email.message.Message` and does four things before it hits the wire ([docs](https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.send_message), [CPython 3.13 `Lib/smtplib.py`](https://github.com/python/cpython/blob/3.13/Lib/smtplib.py)).

It derives the envelope sender from the `Sender` header if present, otherwise from `From`.
It derives the envelope recipients by combining `To`, `Cc`, and `Bcc`.
If exactly one set of `Resent-*` headers appears, those replace the regular headers; more than one set raises `ValueError`.
It copies the message, deletes `Bcc` and `Resent-Bcc` from the copy, and serializes with `email.generator.BytesGenerator` using `linesep='\r\n'`.
The `Bcc` addresses stay in the envelope and leave the transmitted headers.

Non-ASCII addresses trigger a check.
If the server does not advertise `SMTPUTF8`, `send_message` raises `SMTPNotSupportedError`.
If it does, the policy is cloned with `utf8=True` and `SMTPUTF8` plus `BODY=8BITMIME` are appended to `mail_options`.
`email.policy.SMTP` exists for exactly this serialization: it is `default` with `linesep` set to `\r\n` ([docs](https://docs.python.org/3/library/email.policy.html#email.policy.SMTP)).

`SMTP.sendmail` is the layer underneath and "does not modify the message headers in any way" ([docs](https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.sendmail)).
The envelope and the headers are separate concerns, and only the envelope decides routing.

### What an SMTP send returns

`sendmail` returns a dict with one entry per refused recipient, and an empty dict when every recipient was accepted ([docs](https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.sendmail)).
`send_message` returns whatever `sendmail` returns.

No id comes back.
`SMTP.data()` does return `(code, resp)` where `resp` is the server's reply text, which on most MTAs carries a queue id ([CPython 3.13 `Lib/smtplib.py`](https://github.com/python/cpython/blob/3.13/Lib/smtplib.py)).
`sendmail` binds that response, checks the code, and discards the text.
Reaching a queue id means driving `mail()`, `rcpt()`, and `data()` directly instead of calling `send_message`.

Even then the value is not portable.
RFC 5321 section 4.2 states that reply codes are for programs and the text is for humans, and that clients must not depend on the exact text of responses ([RFC 5321](https://www.rfc-editor.org/rfc/rfc5321.html)).
Queue id formats are an MTA convention, not a standard.

The `250` after `DATA` carries real meaning: RFC 5321 section 4.1.1.4 makes it a formal handoff, after which the server must either deliver the message or properly report the failure ([RFC 5321](https://www.rfc-editor.org/rfc/rfc5321.html)).
That report arrives as a bounce message, hours later, out of band.

The one durable identifier is the `Message-ID` header.
RFC 5322 section 3.6.4 says the generator of the identifier must guarantee uniqueness, and that every message should have the field ([RFC 5322](https://www.rfc-editor.org/rfc/rfc5322.html)). epistole generates it, so epistole can return it.

### SMTP failure surface

`smtplib` defines these exceptions ([docs](https://docs.python.org/3/library/smtplib.html#smtplib.SMTPException), [CPython 3.13 `Lib/smtplib.py`](https://github.com/python/cpython/blob/3.13/Lib/smtplib.py)):

- `SMTPException`, the base, which subclasses `OSError`.
- `SMTPServerDisconnected`, raised on unexpected disconnect or on use before connecting.
- `SMTPResponseException`, the base for anything carrying a code, with `smtp_code` and `smtp_error` attributes.
- `SMTPSenderRefused`, adding `sender`.
- `SMTPRecipientsRefused`, adding `recipients`.
  Note it subclasses `SMTPException` directly, not `SMTPResponseException`, so it has no `smtp_code`.
- `SMTPDataError`, `SMTPConnectError`, `SMTPHeloError`, `SMTPNotSupportedError`, and `SMTPAuthenticationError`.

`sendmail` raises `SMTPRecipientsRefused` only when every recipient is refused.
One refused recipient out of three returns normally with a one-entry dict.
Connections stay open after an exception unless the reply code was `421`, in which case `sendmail` closes the socket ([CPython 3.13 `Lib/smtplib.py`](https://github.com/python/cpython/blob/3.13/Lib/smtplib.py)).

`smtplib` does not classify failures.
RFC 5321 section 4.2.1 does: `4yz` is a Transient Negative Completion reply where "the error condition is temporary and the action may be requested again", and `5yz` is a Permanent Negative Completion reply where "the SMTP client SHOULD NOT repeat the same request" ([RFC 5321](https://www.rfc-editor.org/rfc/rfc5321.html)).
Reading `smtp_code // 100` is the whole classification rule.

Transient codes epistole will see: `421` service not available, `450` mailbox unavailable, `451` local error in processing, `452` insufficient system storage.
Permanent codes: `550` mailbox unavailable, `552` exceeded storage allocation, `553` mailbox name not allowed, `554` transaction failed ([RFC 5321](https://www.rfc-editor.org/rfc/rfc5321.html)).

Servers that implement RFC 3463 add an enhanced status code with the same split: class 4 is a persistent transient failure where "sending in the future may be successful", class 5 is a permanent failure "not likely to be resolved by resending the message in the current form" ([RFC 3463](https://www.rfc-editor.org/rfc/rfc3463.html)).
`smtplib` does not parse these; they arrive inside `smtp_error`.

### SMTP throttling

SMTP has no rate-limit signal and no `Retry-After` equivalent.
A throttled server answers `421` or `45x` and the client backs off blind.

The limits are provider policy.
Exchange Online caps outbound at 30 messages per minute, and states that "if a user submits messages at a rate that exceeds the limit via SMTP client submission, the messages will be rejected and the client will need to retry" ([Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits)).
Gmail's SMTP server caps at 2,000 messages per day ([Workspace admin help](https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app)).

### SMTP sender identity

There is no pinning at the library level.
`sendmail` builds the envelope from the arguments and leaves the headers alone ([docs](https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.sendmail)), so the envelope sender and the header `From` can differ freely.

The server decides.
A submission server that rejects the `MAIL FROM` address produces `SMTPSenderRefused` with the code and the refused address.
RFC 5322 section 3.6.2 governs the header side: `Sender` must appear when `From` lists more than one mailbox, and should not appear when the author and the transmitter are the same ([RFC 5322](https://www.rfc-editor.org/rfc/rfc5322.html)).
`send_message` follows that rule when picking the envelope sender.

### SMTP credentials

**Corrected 2026-09-09.**
This section previously opened "There is no scope model", which is true of `smtplib` and false of Exchange Online.

The Python library has no such model.
`SMTP.login(user, password)` negotiates AUTH and raises `SMTPAuthenticationError` on rejection, `SMTPNotSupportedError` when the server does not advertise AUTH, and `SMTPException` when no mutually supported mechanism exists ([docs](https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.login)).

`login` only tries CRAM-MD5, PLAIN, and LOGIN, in that order, and drops CRAM-MD5 when `hmac.digest` rejects MD5 under a FIPS build ([CPython 3.13 `Lib/smtplib.py`](https://github.com/python/cpython/blob/3.13/Lib/smtplib.py)).
XOAUTH2 is not implemented.
Reaching it means calling `SMTP.auth("XOAUTH2", authobject)` with a callable epistole supplies ([docs](https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.auth)).
This matters because both Gmail and Exchange Online now steer SMTP clients toward OAuth.

The server side is a different story, and the absence is in the library rather than in the protocol as Microsoft implements it.
Exchange Online authorizes SMTP client submission through Exchange RBAC for Applications, and the role is scopable to a subset of mailboxes: `New-ManagementRoleAssignment -Name RBAC -Role 'Application SMTP.SendAsApp' -App {App ID} -CustomResourceScope 'RBAC Scope'` ([Configure SMTP onboarding to App RBAC](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/smtp-app-rbac-onboarding)).
The role itself is documented as "Allows the app to use SMTP Client Submission to submit mails to user outbox folder" ([Application RBAC](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac)).
So least privilege for SMTP against Exchange Online is a role assignment against a resource scope, not an OAuth scope on the token.

Two caveats, because the correction that prompted this edit overstated the case.

The onboarding page names no delegated `SMTP.Send` scope.
It asks for the opposite: "Refrain from adding any permissions to your application, as this process does not require any claims.
Including the SMTP.SendAsApp claim would trigger an unnecessary check for mailbox permissions."
The token scope it names is `https://outlook.office365.com/.default`.
Whether a delegated equivalent exists is undetermined, and is carried below.

The Application RBAC page contradicts itself on protocol.
It lists `Application SMTP.SendAsApp` with a Protocol column reading "MS Graph", while its own Supported Protocols section names only MS Graph and EWS.
SMTP is not in that list, on the page that documents the SMTP role.

## Gmail API

### Gmail request shape

Two endpoints exist for the same method ([`users.messages.send`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)):

```text
POST https://gmail.googleapis.com/gmail/v1/users/{userId}/messages/send
POST https://gmail.googleapis.com/upload/gmail/v1/users/{userId}/messages/send
```

`userId` accepts an email address, and the special value `me` means the authenticated user.

The request body is a `Message` resource.
The sending guide gives three steps: encode the email content as a base64url string, set the `raw` property to it, and call `messages.send` ([sending guide](https://developers.google.com/workspace/gmail/api/guides/sending)).
The `Message` resource defines `raw` as "The entire email message in an RFC 2822 formatted and base64url encoded string" ([Message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages)).

The upload endpoint carries hard numbers that the reference page does not show.
The [Gmail API discovery document](https://gmail.googleapis.com/$discovery/rest?version=v1) (revision `20260903`) declares `mediaUpload.maxSize` of `36700160` bytes, which is exactly 35 MiB, and `accept` of `message/*`.
It lists a simple path at `/upload/gmail/v1/users/{userId}/messages/send` and a resumable path at `/resumable/upload/gmail/v1/users/{userId}/messages/send`, both marked `multipart: true`.
`uploadType` takes `media`, `multipart`, or `resumable` ([upload guide](https://developers.google.com/workspace/gmail/api/guides/uploads)).

Practical consequence for epistole: send small messages to the plain endpoint and route anything with attachments through `/upload`.
The discovery document is the citable source for the threshold; the human-facing docs do not state it.

### What a Gmail send returns

`200 OK` with a `Message` resource containing `id`, `threadId`, and `labelIds` ([`users.messages.send`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)).

The `id` is "The immutable ID of the message" ([Message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages)).
It is useful: it addresses `users.messages.get` for that mailbox.
It is not an RFC 5322 `Message-ID`, and it means nothing to the recipient or to any other system.

Stability has one documented edge.
The drafts guide explains that the `drafts` resource exists "to provide a stable ID because the underlying message IDs change every time the message is replaced", and that "when the draft is sent, the draft is automatically deleted and a new message with an updated ID is created with the `SENT` system label" ([drafts guide](https://developers.google.com/workspace/gmail/api/guides/drafts)).
The id returned by `messages.send` is the id of the sent message and is stable from that point.

The `200` does not mean delivered, and Gmail says this in unusually blunt terms: "The mail sending pipeline is complex: once the user exceeds their quota, there can be a delay of several minutes before the API begins returning 429 error responses.
You can't assume that a 200 response means the email was successfully sent." ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)).

### Gmail failure surface

Status codes and their meanings ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)):

| Status | Reason strings | Class |
| --- | --- | --- |
| `400` | `badRequest` | Permanent |
| `401` | `authError` | Permanent unless a token refresh succeeds |
| `403` | `dailyLimitExceeded`, `domainPolicy` | Permanent, needs administrator action |
| `403` | `rateLimitExceeded`, `userRateLimitExceeded` | Transient |
| `404` | | Permanent |
| `429` | | Transient |
| `500`, `502`, `503`, `504` | `backendError` | Transient |

The error body follows Google's standard shape ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)):

```json
{
  "error": {
    "code": 400,
    "message": "Error description",
    "errors": [{
      "domain": "global|usageLimits",
      "reason": "badRequest|authError|rateLimitExceeded",
      "message": "Specific error message",
      "location": "parameter|header",
      "locationType": "parameter|header"
    }]
  }
}
```

`errors[].reason` carries the classification, not the HTTP status alone.
A `403` is permanent or transient depending entirely on which reason string it holds.

### Gmail throttling

Gmail runs two independent quota systems, and epistole will hit both.

The API quota is measured in units ([usage limits](https://developers.google.com/workspace/gmail/api/reference/quota)).
`messages.send` costs 100 units.
The ceilings are 6,000 units per minute per user per project, 1,200,000 units per minute per project, and 80,000,000 units per day per project.
Sixty sends per minute per user exhausts the per-user allowance on its own.

The mail sending quota is a separate, lower limit that the API inherits from Gmail ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)): "These limits are per-user and are shared by all of the user's clients, whether API clients, built-in or web clients, or SMTP MSA."
For Workspace accounts that is 2,000 messages per day, 2,000 recipients per message, 500 external recipients per message, and 3,000 external recipients per day, dropping to 500 messages per day on trial accounts ([Workspace sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace)).
"After reaching one of these limits, users can't send new messages for up to 24 hours."

Three distinct `429` messages exist ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)):

- `"Too many requests: User-rate limit exceeded (Mail sending)"` for the sending quota.
- `"Too many requests: User-rate limit exceeded"` for the per-user bandwidth limit.
- `"Too many requests: Too many concurrent requests for user"` for the concurrency limit.

Per-user limits "cannot be increased for any reason".

On `Retry-After`, the documentation is ambiguous and I could not resolve it from a primary source.
The error guide says a `429` "is returned with a time to retry" but never names a header, and its own remediation section prescribes exponential backoff instead: "Start retry periods at least one second after the error" ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)).
Treat Gmail's `retry_after` as absent until a live response proves otherwise.

### Gmail sender identity

The `userId` path parameter identifies the mailbox, and `me` is the authenticated user ([`users.messages.send`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)).
There is no cross-account send.

Within the account, send-as aliases widen the set of usable `From` addresses.
`SendAs.sendAsEmail` is "The email address that appears in the 'From:' header for mail sent using this alias", and `verificationStatus` "indicates whether ownership of an address has been verified for its use as a send-as alias" ([`users.settings.sendAs`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs)).
An alias needing verification is returned with `verificationStatus` of `pending` and must be verified before use ([alias guide](https://developers.google.com/workspace/gmail/api/guides/alias_and_signature_settings)).

What I could not verify: no Gmail API page states what `messages.send` does when the `From` header names an address that is neither the account nor a verified alias.
The plausible behaviours are rejection with `400` and silent rewriting to the default send-as address, and the documentation supports neither.
This needs a live test before epistole promises anything about `from_` on Gmail.

### Gmail scopes

`users.messages.send` accepts any one of ([`users.messages.send`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)):

- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/gmail.compose`
- `https://www.googleapis.com/auth/gmail.modify`
- `https://mail.google.com/`

The [discovery document](https://gmail.googleapis.com/$discovery/rest?version=v1) lists a fifth that the reference page omits: `https://www.googleapis.com/auth/gmail.addons.current.action.compose`.

For send only, take `gmail.send`.
Google classifies it as Sensitive, described as "Send email on your behalf", while `gmail.compose`, `gmail.modify`, and `https://mail.google.com/` are all Restricted and carry a heavier verification burden ([OAuth scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)).
Listing send-as aliases needs `gmail.settings.basic`, which is Restricted, so alias discovery costs more than sending does.

## Microsoft Graph

### Graph request shape

Two endpoint variants ([`user: sendMail`](https://learn.microsoft.com/en-us/graph/api/user-sendmail)):

```http
POST /me/sendMail
POST /users/{id | userPrincipalName}/sendMail
```

`Content-Type` selects the payload format: "Use `application/json` for a JSON object and `text/plain` for MIME content."

The JSON body takes `message`, a [`message`](https://learn.microsoft.com/en-us/graph/api/resources/message) resource, and the optional `saveToSentItems` boolean, which defaults to `true`.
The MIME body is the base64-encoded RFC 5322 message as the entire request body, with no JSON wrapper.

Both paths accept the same message.
The JSON path uses `subject`, `body` with a `contentType` of `Text` or `HTML`, `toRecipients` and friends as `recipient` objects, `attachments` as `fileAttachment` with base64 `contentBytes`, and `internetMessageHeaders` for custom headers.
Custom headers carry a naming rule: "Add custom headers only when creating a message, and name them starting with 'x-'.
After the message is sent, you cannot modify the headers." ([`message` resource](https://learn.microsoft.com/en-us/graph/api/resources/message)).

The MIME path matters for epistole.
It accepts the exact bytes the SMTP backend would send, so one serializer can feed both.
It preserves headers the JSON model cannot express.

Recipients cap at 500 across `toRecipients`, `ccRecipients`, and `bccRecipients` for a single message from an Exchange Online mailbox ([`message` resource](https://learn.microsoft.com/en-us/graph/api/resources/message)).

**Corrected 2026-09-09.**
This section previously read the 4 MB figure as an S/MIME footnote and said no overall size limit was documented for `sendMail`.
Both were wrong.
It is the platform-wide write-request cap: "Write requests in the Microsoft Graph API have a size limit of 4 MB.
Requests exceeding the size limit fail with the status code HTTP 413, and the error message 'Request entity too large' or 'Payload too large'" ([Use the Microsoft Graph API](https://learn.microsoft.com/en-us/graph/use-the-api)).
The statement sits under the general HTTP-methods heading, so it covers `POST /me/sendMail`, `POST /me/messages` and `PATCH /me/messages/{id}` alike, and `message.body.content` rides inside the request.
The S/MIME note on [create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages) restates the same number for one path rather than being its source.

Read 4 MB as a ceiling rather than a promise.
The same passage adds that "in some cases, the actual write request size limit is lower than 4 MB" and names 3 MB for `POST /me/events/{id}/attachments`.
No lower figure is documented for the mail endpoints.

There is no path past it for a body.
The `uploadSession` resource covers OneDrive, SharePoint document libraries, and "Outlook event and message items as attachments" ([uploadSession](https://learn.microsoft.com/en-us/graph/api/resources/uploadsession)); the word "body" does not appear on that page.
`PATCH` on a draft replaces `body` rather than appending to it, and is itself a 4 MB write request, so a body cannot be assembled across calls.
The MIME path is tighter still rather than looser: a file is base64-encoded inside the MIME part and the whole message base64-encoded again for the request body, which fits roughly 2.1 MB of original bytes inside a 4 MB request.

The 150 MB figure that this section previously offered as the nearest hard number is a throttling window, not a per-message cap: 150 MB of upload across `PATCH`, `POST`, and `PUT` in a 5-minute period per app and mailbox ([Outlook throttling limits](https://learn.microsoft.com/en-us/graph/throttling-limits)).

The consequences for an HTML body are worked through in [`html-bodies-in-email.md`](html-bodies-in-email.md), and the two send paths this forces on the Graph backend are settled in [#20](https://github.com/ozanozbeker/epistole/issues/20).

### What a Graph send returns

Verified, and the issue's claim is correct.
The reference page states: "If successful, this method returns `202 Accepted` response code.
It doesn't return anything in the response body." ([`user: sendMail`](https://learn.microsoft.com/en-us/graph/api/user-sendmail)).
All five worked examples on that page show `HTTP/1.1 202 Accepted` and nothing else.

The same page qualifies what `202` means: "A `202 Accepted` response code indicates that the request has been accepted; however, it doesn't indicate that the request processing has completed."

The [send mail process overview](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail) walks the rest.
Step 1 creates a draft in the sender's mailbox and returns the `202`.
"When step 1 is complete, your app's direct interaction with Microsoft Graph is over."
Steps 2 through 7 are transport pickup, policy evaluation, routing, and delivery, all after the response.
Failures there produce a non-delivery report placed in the sender's Inbox: "If step 3 fails, the transport process constructs a non-delivery report message and places it in the sender's Inbox."
Transport also detects invalid recipient addresses at step 5 and mails NDRs back.

So a Graph recipient typo is not an API error.
It is an email that arrives in the sender's mailbox later. epistole cannot see it.

**Getting an id costs a second call and a wider permission.**
`POST /me/messages` creates a draft, returns `201 Created`, and includes a full `message` object with `id` and an Exchange-assigned `internetMessageId` such as `<MWHPR1301MB@MWHPR1301MB.namprd13.prod.outlook.com>` ([create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages)).
`POST /me/messages/{id}/send` then sends it and returns `202 Accepted` with no body ([`message: send`](https://learn.microsoft.com/en-us/graph/api/message-send)).

Two caveats on that workaround.
The draft path needs `Mail.ReadWrite`, not `Mail.Send` ([create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages)).
And the `id` is not stable by default: "By default, this value changes when the item is moved from one container (such as a folder or calendar) to another.
To change this behavior, use the `Prefer: IdType=\"ImmutableId\"` header." ([`message` resource](https://learn.microsoft.com/en-us/graph/api/resources/message)).
Sending moves the item from Drafts to Sent Items, so the id from the create call is exactly the kind that changes.
`internetMessageId` is the more portable value of the two, because it is an RFC 2822 message id that the recipient also sees.

### Graph failure surface

Graph returns standard HTTP status codes with a JSON error object ([error responses](https://learn.microsoft.com/en-us/graph/errors)):

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "innererror": { "code": "string" },
    "details": []
  }
}
```

Two rules from that page shape epistole's error model.
"The **code** property contains a machine-readable value that you can take a dependency on in your code."
"Don't take any dependency on the content of this value [`message`] in your code."
Also: "The **innererror** object can recursively contain more **innererror** objects with more specific error **codes** properties.
When handling an error, apps should loop through all the nested error codes that are available and use the most detailed one that they understand."

Statuses relevant to sending ([error responses](https://learn.microsoft.com/en-us/graph/errors)):

| Status | Meaning | Class |
| --- | --- | --- |
| `400` | Malformed or incorrect request | Permanent |
| `401` | Missing or invalid authentication | Permanent |
| `403` | Access denied, insufficient permission or license | Permanent |
| `404` | Resource does not exist | Permanent |
| `409` | Conflict; "If a Retry-After header is present, that value can be used for the delay between retries" | Transient |
| `413` | Request size exceeds the maximum | Permanent |
| `415` | Unsupported content type | Permanent |
| `429` | Throttled | Transient, `Retry-After` |
| `500`, `504` | Server or gateway error | Transient |
| `503` | "You can repeat the request after a delay, the length of which can be specified in a Retry-After header" | Transient, `Retry-After` |
| `509` | Bandwidth limit exceeded; "Your app can retry the request again after more time has elapsed" | Transient |

Two error codes are documented specifically for the send path:

- `ErrorMimeContentInvalidBase64String` on `400`, with message "Invalid base64 string for MIME content." ([`user: sendMail`](https://learn.microsoft.com/en-us/graph/api/user-sendmail)).
- `ErrorSendAsDenied` on `403`, with message "The user account which was used to submit this request does not have the right to send mail on behalf of the specified sending account.
  Cannot submit message." ([send from another user](https://learn.microsoft.com/en-us/graph/outlook-send-mail-from-other-user)).

### Graph throttling

Graph is the only backend of the three with a documented machine-readable retry hint.

On exceeding a threshold Graph "Returns HTTP status code **429 Too Many Requests**" and "Returns a suggested wait time in the response header of the failed request" ([throttling guidance](https://learn.microsoft.com/en-us/graph/throttling)).
The sample response on that page:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 10

{
  "error": {
    "code": "TooManyRequests",
    "innerError": {
      "code": "429",
      "date": "2020-08-18T12:51:51",
      "message": "Please retry after",
      "request-id": "94fb3b52-452a-4535-a601-69e0a90e3aa2",
      "status": "429"
    },
    "message": "Please retry again later."
  }
}
```

The header is near-guaranteed but not absolute: "All the resources and APIs described in the Service-specific limits provide a `Retry-After` header except where indicated", and "If no `Retry-After` header is provided by the response, we recommend implementing an exponential backoff retry policy" ([throttling guidance](https://learn.microsoft.com/en-us/graph/throttling)).
The [Outlook service limits](https://learn.microsoft.com/en-us/graph/throttling-limits) section does not indicate an exception, so mail sending should always carry the header. epistole should still fall back to backoff when it is missing.

Three limit tiers apply, and the first one reached triggers throttling ([throttling limits](https://learn.microsoft.com/en-us/graph/throttling-limits)):

- Global, per app across all tenants: 130,000 requests per 10 seconds.
- Outlook, per app and mailbox pair: 10,000 API requests per 10 minutes, four concurrent requests, 150 MB upload per 5 minutes.
  "Exceeding the limit for one mailbox doesn't affect the ability of the application to access another mailbox."
- Exchange Online transport, per mailbox: 30 messages per minute and 10,000 recipients per day ([Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits)).

The third tier is the one that will bite epistole, and it does not produce a `429`.
"When outbound message volumes surpass the message rate limit, any excess in message submission will be throttled and successively carried over to the following minutes."
The recipient rate limit is harder: "After the recipient rate limit is reached, messages can't be sent from the mailbox until the number of recipients that were sent messages in the past 24 hours drops below the limit."
There is also a tenant-wide external recipient cap, and mail from a default `onmicrosoft.com` domain is capped at 100 external recipients per organization per 24 hours, with senders receiving "NDRs with the code 550 5.7.236" past that point ([Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits)).

Four concurrent requests per app and mailbox is the number that constrains epistole's design most directly.
Any concurrency epistole offers for a single Graph mailbox should default to four or fewer.

### Graph sender identity

The `from` property is "The owner of the mailbox from which the message is sent", and "The value must correspond to the actual mailbox used".
`sender` is "The account that is used to generate the message" ([`message` resource](https://learn.microsoft.com/en-us/graph/api/resources/message)).

Delegated tokens can override `from`, but only with two grants stacked ([send from another user](https://learn.microsoft.com/en-us/graph/outlook-send-mail-from-other-user)).
The application needs the `Mail.Send.Shared` Graph permission.
The signed-in user needs Exchange **Send As** or **Send on Behalf** on the target mailbox.
Without both, Graph answers `403 ErrorSendAsDenied`.

The two Exchange grants differ in what the recipient sees.
Send on Behalf shows the delegation: `sender` is the signed-in user and `from` is the mailbox.
Send As hides it: `sender` and `from` hold the same value.
Only an administrator can grant Send As; a user can grant Send on Behalf for their own mailbox.

Set `from` and leave `sender` alone: "You don't need to set the `sender` property - Microsoft Graph sets it appropriately, based on the mailbox permissions granted to the user who has signed in."

One gap worth knowing before designing an alias-listing feature: "It's not currently possible to use Microsoft Graph to query which mailboxes the authenticated user has permissions for." epistole cannot enumerate valid `from` values on Graph, only attempt and catch `ErrorSendAsDenied`.

**The application-permission case is the dangerous one.**
`Mail.Send` as an application permission means "Send mail as any user" and "Allows the app to send mail as users in the organization without a signed-in user" ([permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)).
The scoping note on `user: sendMail` says the same thing in operational terms: an app with application-permission `Mail.Send` "can send mail as any user in the organization by sending the mail normally through the user's mailbox" ([send from another user](https://learn.microsoft.com/en-us/graph/outlook-send-mail-from-other-user)).
Every mailbox in the tenant is reachable through `POST /users/{id}/sendMail` by default.

Narrowing it is an Exchange Online concern, not a Graph one.
RBAC for Applications assigns the `Application Mail.Send` role to a service principal with a management scope or administrative unit, and "replaces Application Access Policies" ([Application RBAC in Exchange Online](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac)).
The trap is additive consent: "the assigned permissions are a union operation on the permissions from Microsoft Entra ID and the permissions assigned in Exchange Online RBAC."
Leaving the unscoped Microsoft Entra grant in place while adding a scoped RBAC assignment "results in no effective resource scoping".
Permission changes also cache for 30 minutes to 2 hours.

None of this is epistole's code, but epistole's documentation should tell operators that application-permission `Mail.Send` is tenant-wide until Exchange scopes it.

### Graph permissions

`sendMail` and `message: send` both take the same set, with `Mail.Send` as least privileged for all three token types ([`user: sendMail`](https://learn.microsoft.com/en-us/graph/api/user-sendmail), [`message: send`](https://learn.microsoft.com/en-us/graph/api/message-send)):

| Permission | Type | Display text | Admin consent |
| --- | --- | --- | --- |
| `Mail.Send` | Delegated | Send mail as the signed-in user | Yes |
| `Mail.Send` | Application | Send mail as any user | Yes |
| `Mail.Send.Shared` | Delegated | Send mail from shared mailboxes and delegated mailboxes | Yes |

Admin consent is required for every one of them ([permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)).
Graph has no consumer-consentable send permission, which makes the Graph onboarding story heavier than Gmail's.

Creating a draft needs `Mail.ReadWrite` on top ([create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages)), so the id-returning workaround widens epistole's permission ask from send-only to read-write.

**Added 2026-09-09.**
`Mail.ReadWrite` has a second, independent trigger, and it is a likelier one than wanting an id.
Any attachment over 3 MB forces the draft plus upload-session flow: "if the file size is between 3 MB and 150 MB, create an upload session", and "make sure to request `Mail.ReadWrite` permission to create the uploadSession for a message" ([Attach large files](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)).

That makes 3 MB a privacy boundary rather than a size one.
`Mail.ReadWrite` "Allows the app to create, read, update, and delete email in all mailboxes without a signed-in user.
Doesn't include permission to send mail" ([Application RBAC](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac)), so it is additional to `Mail.Send` rather than a substitute.
One large attachment moves an application from "can send" to "can send and can read every message in scope", which is a change a security reviewer will notice.

## Things that make a uniform interface hard

Ranked by how much design they force.

1. **No id on two of three backends.**
   Graph returns none.
   `smtplib` reaches none through `send_message`.
   Any uniform `send()` return type either omits the id or makes it optional, and an optional id that is present only on Gmail is close to useless to a caller writing backend-agnostic code.
2. **Partial acceptance exists only on SMTP.**
   `sendmail` returning a non-empty dict without raising has no analogue in either API.
   Either epistole raises on any refusal and discards the distinction, or it carries a per-recipient result list that is always empty on Gmail and Graph.
3. **`retry_after` exists only on Graph.**
   Optional field, documented as such.
4. **The message model differs at the boundary.**
   SMTP and Gmail take RFC 5322 bytes.
   Graph takes either bytes or a JSON object.
   Feeding Graph the same bytes keeps one serializer, but it costs the JSON-only features and it fits less: base64 inside the MIME part and base64 again for the request body puts roughly 2.1 MB of original bytes inside the same 4 MB cap.
5. **Transport-layer quotas are invisible to the API.**
   Exchange Online's 30 messages per minute and Gmail's 2,000 messages per day both live below the send call.
   Gmail surfaces its as a delayed `429`; Exchange surfaces its as an NDR that epistole never sees.
6. **Success is asynchronous everywhere, and each backend admits it differently.**
   Graph says `202` does not mean processed.
   Gmail says a `200` does not mean sent.
   RFC 5321 says `250` is a handoff of responsibility.
   All three mean the same thing, and none of them means delivered.
7. **Backend-specific concurrency ceilings.**
   Graph allows four concurrent requests per app and mailbox.
   Gmail has an undocumented per-user concurrency limit that surfaces as a distinct `429` message.
   SMTP has whatever the server allows.
   A shared concurrency default will be wrong for at least one backend.

## Unverified and conflicting

- **Gmail recipient limit disagrees between two Google pages.**
  The API [usage limits](https://developers.google.com/workspace/gmail/api/reference/quota) page states "a limit of 500 recipients per email message".
  The [Workspace sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace) page states 2,000 total addresses per message with a maximum of 500 external recipients.
  The 500 figures probably describe the same external-recipient cap, but neither page says so.
  Assume 500 as the safe ceiling.
- **Gmail `Retry-After` is undetermined.**
  The error guide says `429` comes back "with a time to retry" but never names a header, and its own remediation section prescribes exponential backoff.
  I could not find a Google page that states whether Gmail sets `Retry-After`.
  Only a live response settles it.
- **Gmail `From` enforcement is undocumented.**
  No page states what `messages.send` does with a `From` header naming an unverified, non-alias address.
  Needs a live test.
- **`Message-ID` preservation is undocumented on both APIs.**
  Whether Gmail keeps a client-supplied `Message-ID` on the `raw` payload, and whether Graph's MIME path keeps one while its JSON path assigns its own `internetMessageId`, is stated nowhere I could find.
  The Graph draft examples all show an Exchange-generated `internetMessageId`, which suggests the JSON path assigns one.
  This is load-bearing if epistole plans to return its own `Message-ID` as the uniform identifier, so test it first.
- ~~**No overall `sendMail` size limit is published for Graph.**~~ **Resolved 2026-09-09.**
  It is 4 MB, the platform-wide write-request cap.
  See the corrected [Graph request shape](#graph-request-shape).
- **Whether Graph's "4 MB" means 4,000,000 or 4,194,304 bytes.**
  Microsoft writes "4 MB" and never disambiguates. [#20](https://github.com/ozanozbeker/epistole/issues/20) picked `4_000_000` as the conservative reading, which is a choice rather than a citation.
- **Whether Graph applies a write cap below 4 MB to the mail endpoints.**
  Microsoft says the limit is "in some cases" lower and names only a calendar endpoint.
  Nothing states that `sendMail` is or is not one of those cases.
- **Whether Exchange Online exposes a delegated OAuth scope for SMTP AUTH.**
  The application side is documented and resource-scopable.
  No Microsoft page found names an `SMTP.Send` delegated scope, and the onboarding page tells you to add no claims at all.
  Only a live token settles it.

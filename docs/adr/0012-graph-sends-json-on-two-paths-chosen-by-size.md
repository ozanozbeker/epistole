# The Graph backend sends JSON on every request and picks one of two paths by encoded size

`GraphTransport` sends JSON to Microsoft Graph on every request and never uses the `text/plain` MIME form.
Under 4 MB of encoded request, it calls `POST /users/{addr-spec}/sendMail`.
Over that, it creates a JSON draft, adds each attachment by its own call, sends the draft, and deletes the draft if anything fails in between.
The switch is automatic and has no constructor argument.
The tenant's permission grant is the only check on the draft path.
A draft path without `Mail.ReadWrite` fails as `AuthenticationError`.
Decided on [#20](https://github.com/ozanozbeker/epistole/issues/20), based on `docs/research/attachment-and-inline-rules.md` and `docs/research/send-boundary-semantics.md`.
Amended on [#27](https://github.com/ozanozbeker/epistole/issues/27): the custom-header pre-check now has the surface it lacked, and `singleValueExtendedProperties` is named as its reopener (ADR-0016).
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): every request addresses the mailbox as `/users/{addr-spec}`, because `/me` resolves against a signed-in user and no credential this ADR offers has one.

## Why

**`/me` cannot work, and `/users/{addr-spec}` works everywhere.**
`/me` resolves against a signed-in user.
An app-only token has none, so Graph returns `400 BadRequest: /me request is only valid with delegated authentication flow`.
Every credential `GraphBackend` accepts under `https://graph.microsoft.com/.default` is app-only.
Routing through `/me` would make the first request of every documented `GraphBackend` configuration fail.
`POST /users/{id | userPrincipalName}/sendMail` is the app-only form.
A delegated token can also use it for its own mailbox.
So one path works for both, and Epistole never needs to detect whether a foreign `get_token` object is delegated.
The addr-spec is the one `email.utils.getaddresses` already produced when the backend checked `from_address`.
ADR-0014 names that call as the same mechanism that splits recipients for `toRecipients`.
It is percent-encoded into the path, because a local part may legally hold characters a URL path may not.

**Epistole uses two paths, because Graph has two.**
Graph caps every write request at 4 MB after encoding, and `sendMail` is one write request.
The only way to exceed that cap is the draft sequence.
It starts with `POST /users/{addr-spec}/messages`.
Each attachment then takes `POST /users/{addr-spec}/messages/{id}/attachments` if it is under 3 MB, or `createUploadSession` and ranged `PUT` from 3 MB to 150 MB.
The sequence ends with `POST /users/{addr-spec}/messages/{id}/send`.
Neither path covers the other.
An upload session for an attachment under 3 MB fails with `ErrorAttachmentSizeShouldNotBeLessThanMinimumSize`.
The draft path needs `Mail.ReadWrite` on top of `Mail.Send`.
Shipping the `sendMail` path alone would cap Graph attachments near 2 MB, below one PDF report.
`docs/choosing-a-backend.md` already documents 150 MB.

**The `sendMail` path uses JSON too, not MIME.**
`sendMail` and `POST /users/{addr-spec}/messages` both accept the whole RFC 5322 message base64-encoded under `Content-Type: text/plain`, the bytes the SMTP backend writes.
That form keeps the `Message-ID` Epistole set, any custom header, the caller's own plain text next to the HTML, and Epistole's `multipart/related` layout.
It was the first choice for the `sendMail` path and was rejected.
Whether attachments can be added to a MIME-built draft is undocumented, so the draft path is JSON either way.
A MIME `sendMail` path would make one message send at 3 MB and raise at 5 MB because of a header.
Size-dependent rejection breaks the library's premise that the same code works everywhere.
JSON on both paths gives one serializer, one set of pre-checks, and uniform behaviour at every size.
It also gives about 0.8 MB more headroom before the draft path and its permission are needed, because the MIME form base64-encodes attachments twice.
It gives up edge-case fidelity, listed under Consequences.

**The switch is automatic, with no flag.**
The alternative was a constructor boolean that keeps the draft path off until the caller turns it on.
That would make the `Mail.ReadWrite` grant visible where the backend is built, as the Send As grant is.
Rejected because the tenant already enforces the permission.
An app without `Mail.ReadWrite` gets `403` on `POST /users/{addr-spec}/messages` before any draft exists.
ADR-0004 maps that to `AuthenticationError`.
A flag would duplicate a check the tenant already enforces.
It would also be one more Graph-only setting in a library that has avoided them (ADR-0009's fixed timeout, ADR-0010's no-flag rule).
The docstring names the permission and the size that triggers it.

**Plain text degrades on Graph, and is not rejected.**
A JSON `body` has one `contentType`, so Graph never receives the caller's `text=` next to `html=` or the Markdown source that ADR-0008 makes the plain text of a `markdown=` message.
Exchange derives its own plain text from the HTML.
ADR-0010 makes anything a backend cannot carry a `RejectedError`.
Applying that literally would make two of three content entries unusable on Graph, for a part most recipients never render.
The rule exists to prevent silent loss, and substituted plain text is not loss.
Custom headers follow the literal rule.
A custom header not starting with `x-` is a `RejectedError` pre-check once headers are specified.

**Each attachment takes its own call.**
The draft creation request could include small attachments while the total fits under 4 MB.
Packing saves two or three round trips on a path that already makes several.
It also needs a bin-packing rule to specify and test.
The draft holds the body, recipients, and headers.
Each attachment is then added by its own call, in message order.

**Cleanup is best effort.**
A failure after draft creation leaves a draft in the mailbox.
A failing nightly job would accumulate drafts.
Server-side drafts are out of scope under #2, so Epistole must delete any draft it made.
The delete is best effort.
Its own failure is suppressed, so the original error is never masked (ADR-0005).

**`saveToSentItems` stays unexposed.**
`sendMail` takes it.
`POST /users/{addr-spec}/messages/{id}/send` does not, and Graph always saves a sent draft in Sent Items.
Exposing it would make behaviour depend on size again.
It can be added later if a use appears.

## Rules

- **Every request names the mailbox.**
  This covers `POST /users/{addr-spec}/sendMail`, `POST /users/{addr-spec}/messages`, and the attachment and send calls under it.
  The addr-spec is the from address's, percent-encoded.
  There is no `/me` request on any path.
- **Path selection measures and never estimates.**
  Serialize the `sendMail` JSON body first.
  If it is under `4_000_000` bytes, send it.
  Otherwise take the draft path.
  Every size check in this ADR reads bytes that already exist, so no expansion factor is applied anywhere.
- **The draft path creates a draft, adds attachments, and sends it.**
  It first calls `POST /users/{addr-spec}/messages` with the message minus attachments.
  Then each attachment, in message order, takes one `POST /users/{addr-spec}/messages/{id}/attachments` if its raw size is under `3_000_000` bytes.
  Otherwise it takes `createUploadSession` and sequential `PUT`s of `3_000_000` bytes each.
  Each upload request sends `Content-Range: bytes {start}-{end}/{total}` and no bearer, through the connection's client (ADR-0009).
  Then it calls `POST /users/{addr-spec}/messages/{id}/send`.
- **Any failure after the draft exists triggers cleanup.**
  Cleanup sends `DELETE {uploadUrl}` if a session is open, then `DELETE /users/{addr-spec}/messages/{id}`.
  Each is best effort, and its failure is suppressed.
  Then the original error is raised.
  A `TransportError` closes the connection after cleanup (ADR-0005).
- **Three pre-checks raise `RejectedError` with `__cause__` `None`** (ADR-0004): an attachment over `150_000_000` raw bytes, more than 500 recipients, and a custom header not starting with `x-`.
  The tenant message limit (1 MB to 150 MB, default 35 MB) is not knowable and has no pre-check.
  A message over it bounces as a non-delivery report Epistole never receives.
- **`internetMessageId`** is set to the `Message-ID` Epistole generated, on both paths.
  Whether Exchange keeps it needs a live test.
  ADR-0004 already defines `SendResult.message_id` as the id of the submission Epistole made, so the result changes documentation, not the contract.
- **Inline images** are `fileAttachment` with `isInline: true` and a bare `contentId`, on both paths and in upload-session `AttachmentItem`s.
- **Every size constant is private** to `GraphTransport`.
  Microsoft writes "4 MB" and "3 MB" without defining the unit.
  3 MiB raw encodes above 4 MiB, so the attachment cut must be decimal.
  The request cap is taken conservatively.
  Moving a number after a live test changes nothing public.
- **Error mapping** is ADR-0004's Graph table, unchanged.
  `403` on draft creation is `AuthenticationError`.
  `413` or `ErrorAttachmentSizeShouldNotBeLessThanMinimumSize` on an attachment call is `RejectedError`.
  It should not occur, because Epistole already cut by size.

## Considered options

- **Ship the `sendMail` path only, with `RejectedError` over 4 MB.**
  Rejected above: it caps attachments near 2 MB and contradicts what the docs already state.
- **Use MIME on the `sendMail` path and JSON on the draft path.**
  Rejected above: behaviour changes with size.
- **Use MIME on both paths.**
  It is undocumented whether a MIME-built draft accepts attachments afterwards.
  If a live test shows it does, this becomes the way to close every fidelity gap below.
  Nothing public would change.
- **Add a constructor flag that enables the draft path.**
  Rejected above: it duplicates the tenant's check.
- **Reject `text=` alongside `html=` and `markdown=` on Graph.**
  Rejected above: it is literal but disproportionate.
- **Pack small attachments into the draft creation.**
  Rejected above: it adds bin-packing to save two round trips.
- **Leave the draft on failure.**
  Rejected above: it leaves drafts in the mailbox.
- **Expose `save_to_sent_items`.**
  Rejected above: its behaviour would depend on size.

## Consequences

- On Graph, the recipient's plain text comes from Exchange, not Epistole.
  The Graph backend docstring and the README say so in one sentence.
- Custom headers on Graph must start with `x-` at every size.
  [#27](https://github.com/ozanozbeker/epistole/issues/27) specified the surface for this inherited rule.
  `.headers(mapping)` sets them on the message.
  `GraphTransport` raises `RejectedError` naming the offending custom header before it writes (ADR-0016).
  `Importance` and read receipts cannot use it, because both are non-`x-`.
  Graph represents those meanings as the `importance` and `isReadReceiptRequested` properties instead.
  Neither gets a v1 surface.
- Graph's `singleValueExtendedProperties` with the `PS_INTERNET_HEADERS` namespace does set arbitrary internet headers, including non-`x-` ones.
  It is undocumented for this use and needs a live tenant to verify.
  So it is the named reopener for the header gap rather than part of v1.
- Microsoft's `message` resource marks `internetMessageHeaders` **Read-only** in its property table while the same page says to add custom headers when creating a message.
  Implementation verifies which is true.
  It also checks whether Exchange caps the header count or total size.
  No documentation found covers that.
- Epistole does not control where Exchange places inline parts relative to the alternative body.
  `cid:` references are guaranteed, but the MIME layout around them is not.
- A large send needs `Mail.ReadWrite` and `2 + N` round trips plus upload chunks.
  It counts against Graph's budget of 150 MB per five minutes per app and mailbox.
- A delegated credential cannot add a large attachment to a message in a shared or delegated mailbox (Graph known issue, `403`).
  Epistole raises that as `AuthenticationError`.
- The glossary's *Message* entry lists "draft" under *Avoid* as the server-side resource v1 excludes.
  The draft here is transient: Epistole creates and removes it inside one send.
  It is never an Epistole concept, so the entry stands.
- ADR-0010 withdraws its claim that Graph's `sendMail` path carries the same bytes as SMTP.
  Its decision is unchanged.
- Three facts here are verifiable only against a real tenant, so implementation settles them.
  They are whether Exchange keeps `internetMessageId` unchanged, the exact request cap and attachment cut, and the shared-mailbox `403`.
  None of the three changes a public surface.
  So each is written above as a private constant or a documentation line, not as a rule that needs evidence first.

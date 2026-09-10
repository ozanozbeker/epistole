# Graph sends JSON on every request, and picks one of two paths by encoded size

`GraphTransport` speaks JSON to Microsoft Graph on every request and never uses the `text/plain` MIME form.
Under 4 MB of encoded request it calls `POST /me/sendMail`.
Over that it creates a JSON draft, adds each attachment by its own call, sends the draft, and deletes the draft if anything fails in between.
The switch is automatic and has no constructor knob: the tenant's permission grant is the gate, and a draft path without `Mail.ReadWrite` fails as `AuthenticationError`.
Decided on [#20](https://github.com/ozanozbeker/epistole/issues/20), grounded by `docs/research/attachment-and-inline-rules.md` and `docs/research/send-boundary-semantics.md`.

## Why

**Two paths, because Graph has two.**
Every Graph write request is capped at 4 MB after encoding, and `sendMail` is one write request.
The only way past it is the draft sequence: `POST /me/messages`, then `POST /me/messages/{id}/attachments` for a file under 3 MB or `createUploadSession` and ranged `PUT` for a file from 3 MB to 150 MB, then `POST /me/messages/{id}/send`.
Neither path covers the other: an upload session on a file under 3 MB fails with `ErrorAttachmentSizeShouldNotBeLessThanMinimumSize`, and the draft path needs `Mail.ReadWrite` on top of `Mail.Send`.
Shipping the small path alone would cap Graph attachments near 2 MB, below one PDF report, and `docs/choosing-a-backend.md` already promises 150 MB.

**JSON everywhere, not MIME on the small path.**
`sendMail` and `POST /me/messages` both accept the whole RFC 5322 message base64-encoded under `Content-Type: text/plain`, the bytes the SMTP backend writes.
That form keeps the stamped `Message-ID`, any custom header, the caller's own plain text next to the HTML, and Epistole's `multipart/related` layout.
It was the first choice for the small path and it lost.
Whether attachments can be added to a MIME-built draft is undocumented, so the large path is JSON either way, and a MIME small path would make one message send at 3 MB and raise at 5 MB because of a header.
Size-dependent rejection is a trap in a library whose premise is that the same code works everywhere.
JSON on both paths gives one serializer, one set of pre-checks, uniform behaviour at every size, and about 0.8 MB more headroom before the draft path and its permission are needed, because the MIME form base64-encodes attachments twice.
What it gives up is edge-case fidelity, listed under Consequences.

**Automatic, with no flag.**
The alternative was a constructor boolean that keeps the draft path off until the caller turns it on, so that the `Mail.ReadWrite` grant is visible where the backend is built, the way the Send As grant is.
Rejected because the tenant already enforces the permission.
An app without `Mail.ReadWrite` gets `403` on `POST /me/messages` before any draft exists, and ADR-0004 maps that to `AuthenticationError`.
A flag would be a second copy of a gate the tenant owns, and one more Graph-only setting for a library that has avoided them (ADR-0009's fixed timeout, ADR-0010's no-flag rule).
The docstring names the permission and the size that triggers it.

**Plain text degrades on Graph, and is not rejected.**
A JSON `body` carries one `contentType`, so Graph never receives the caller's `text=` next to `html=` or the Markdown source that ADR-0008 makes the plain text of a `markdown=` message.
Exchange derives its own text part from the HTML.
ADR-0010 rules that what a backend cannot carry is `RejectedError`, and applying that literally would make two of three content entries unusable on Graph for a part most recipients never render.
The rule guards against silent loss, and a substituted text part is not loss.
Custom headers stay under the literal rule: a header not starting with `x-` is a `RejectedError` pre-check once headers are specified.

**One call per attachment.**
Small attachments could ride inside the draft creation while the total fits under 4 MB.
Packing saves two or three round trips on a path that already costs several, and it costs a bin-packing rule to specify and test.
The draft carries the body, recipients, and headers; every attachment then goes by its own call, in message order.

**Best-effort cleanup.**
A failure after draft creation leaves a draft in the mailbox, and a nightly job that fails would grow a pile.
#2 rules server-side drafts out of scope, so a draft Epistole made is Epistole's mess.
The delete is best effort and its own failure is swallowed, so the original error is never masked (ADR-0005).

**`saveToSentItems` stays unexposed.**
`sendMail` takes it; `POST /me/messages/{id}/send` does not, and a sent draft always lands in Sent Items.
Exposing it would make behaviour depend on size again.
Additive later if a use appears.

## Rules

- **Path selection.**
  Serialize the `sendMail` JSON body first.
  If it is under `4_000_000` bytes, send it.
  Otherwise take the draft path.
- **Draft path.**
  `POST /me/messages` with the message minus attachments.
  Then, per attachment in message order: raw size under `3_000_000` bytes is one `POST /me/messages/{id}/attachments`; otherwise `createUploadSession` and sequential `PUT`s of `3_000_000` bytes each, `Content-Range: bytes {start}-{end}/{total}`, no bearer, through the connection's client (ADR-0009).
  Then `POST /me/messages/{id}/send`.
- **Cleanup.**
  Any failure after the draft exists: `DELETE {uploadUrl}` if a session is open, then `DELETE /me/messages/{id}`, each best effort with the failure swallowed.
  Then the original error is raised; a `TransportError` closes the connection after cleanup (ADR-0005).
- **Pre-checks**, `RejectedError` with `__cause__` `None` (ADR-0004): an attachment over `150_000_000` raw bytes; more than 500 recipients; a custom header not starting with `x-`.
  The tenant message limit (1 MB to 150 MB, default 35 MB) is not knowable and has no pre-check; a message over it bounces as a non-delivery report Epistole never sees.
- **`internetMessageId`** is set to the stamped `Message-ID` on both paths.
  Whether Exchange keeps it is a live test; ADR-0004 already defines `SendResult.message_id` as the submission Epistole made, so the answer changes documentation, not the contract.
- **Inline images** are `fileAttachment` with `isInline: true` and a bare `contentId`, on both paths and in upload-session `AttachmentItem`s.
- **Every size constant is private** to `GraphTransport`.
  Microsoft writes "4 MB" and "3 MB" without units; 3 MiB raw encodes above 4 MiB, so the attachment cut must be decimal, and the request cap is taken conservatively.
  Moving a number after a live test changes nothing public.
- **Error mapping** is ADR-0004's Graph table, unchanged.
  `403` on draft creation is `AuthenticationError`; `413` or `ErrorAttachmentSizeShouldNotBeLessThanMinimumSize` on an attachment call is `RejectedError` and should not occur, because Epistole cut by size.

## Considered options

- **Small path only, `RejectedError` over 4 MB.**
  Rejected above: caps attachments near 2 MB and breaks a promise already written.
- **MIME on the small path, JSON on the large path.**
  Rejected above: behaviour changes with size.
- **MIME on both paths.**
  Undocumented whether a MIME-built draft accepts attachments afterwards.
  If a live test shows it does, this becomes the way to close every fidelity gap below, and nothing public changes.
- **A constructor flag enabling the draft path.**
  Rejected above: duplicates the tenant's gate.
- **Reject `text=` alongside `html=` and `markdown=` on Graph.**
  Rejected above: literal but disproportionate.
- **Pack small attachments into the draft creation.**
  Rejected above: bin-packing for two round trips.
- **Leave the draft on failure.**
  Rejected above: litter.
- **Expose `save_to_sent_items`.**
  Rejected above: size-dependent.

## Consequences

- On Graph the recipient's text part is Exchange's, not Epistole's.
  The Graph backend docstring and the README say so in one sentence.
- Custom headers on Graph must start with `x-` at every size.
  The headers decision on #2 inherits this pre-check.
- Epistole does not control where Exchange places inline parts relative to the alternative body; `cid:` references are guaranteed, the MIME layout around them is not.
- A large send costs `Mail.ReadWrite` and `2 + N` round trips plus upload chunks, and writes against Graph's 150 MB per five minutes per app and mailbox budget.
- A delegated credential cannot add a large attachment to a message in a shared or delegated mailbox (Graph known issue, `403`); it surfaces as `AuthenticationError`.
- The glossary's *Message* entry lists "draft" under *Avoid* as the server-side resource v1 rules out.
  The draft here is transient, created and removed inside one send, and never a Epistole concept; the entry stands.
- ADR-0010's claim that Graph's small path carries the same bytes as SMTP is withdrawn there; its decision is unchanged.
- Three facts here are verifiable only against a real tenant, and implementation settles them: whether `internetMessageId` survives to the wire, the exact request cap and attachment cut, and the shared-mailbox `403`.
  None of the three moves a public surface, which is why each is written above as a private constant or a documentation line rather than a rule waiting on evidence.

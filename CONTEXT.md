# Epistole

Epistole is one API for building an email message and sending it through SMTP, the Gmail API, or Microsoft Graph without changing the calling code.
This glossary defines the terms the spec and the implementation share.

An _Avoid_ list names the words this project does not use for that concept in prose.
A public name may still spell one where the name comes from a vendor, from an RFC, or from a neighbouring concept.
The entry says which.
`TokenCredential`, `.embed(cid=)`, `.headers()`, `SenderRefusedError`, and the auth adapters over `httpx2` are the five that do.

## Language

**Message**: The immutable value a caller builds: its content, its addressing, its attachments, and any custom headers.
It never holds a From address, a backend, or the identity of a submission.
Every method that would change it returns a new message instead.
_Avoid_: email, draft (Epistole exposes none; the Graph draft path creates and deletes one inside a single send, and that is the only use of the word), mail

**Content**: What a message says: HTML together with plain text, or plain text alone.
The caller supplies the HTML, or Epistole renders it from Markdown.
_Avoid_: body (the HTML element, blastula's middle section, and RFC 5322's everything after the headers), payload, copy

**Plain text**: The readable text every message holds: what the caller wrote, the Markdown source, or what Epistole derived from the HTML.
Epistole sends it alongside the HTML or alone, except where a mail service substitutes its own.
A text-only client shows nothing else.
_Avoid_: fallback (it is the whole message when there is no HTML), alternative (the MIME spelling), text part

**Attachment**: Bytes with a filename and a content type that a message carries.
The recipient's client lists it as a file, unless it is an inline image.
_Avoid_: file, part, MIME part

**Inline image**: An attachment that the HTML body references as `cid:` followed by its content id.
The recipient's client displays it in place and never lists it as a file.
A caller embeds one under a name the HTML already uses.
Epistole makes one by rewriting a `data:` image it finds.
_Inline_ names this mechanism alone.
Copying stylesheet rules onto `style` attributes is rewriting CSS.
Epistole never rewrites CSS.
_Avoid_: embedded image, body image, related part

**Content id**: The name that identifies an inline image.
It is unique within one message and deliberately not unique across messages.
It never contains an `@domain`.
_Avoid_: cid (the URL scheme, which `.embed(cid=)` names deliberately because the HTML uses it), Content-ID (the header spelling)

**Custom header**: A `Name: value` line the caller supplies and Epistole passes through unchanged, such as `List-Unsubscribe` or a private `X-` tag.
It is never one of the headers Epistole writes itself, so setting a name Epistole owns raises rather than overriding it.
A message holds at most one value per name.
Graph accepts only names starting with `x-`.
_Avoid_: header on its own (the addressing and MIME lines are headers too, so `.headers()` and `headers_` keep RFC 5322's word and hold only the caller's set), metadata, extra, field (RFC 5322's word for both kinds)

**Backend**: The configuration for sending through one mail service.
The test doubles that substitute for one are backends too.
It owns the credentials, the from address, and every setting specific to its mail service.
The message owns everything else.
A connection owns the live link.
A caller sends through it directly for one message, or opens a connection from it for many.
_Avoid_: transport (the object a backend opens to make the network calls, never the backend), sender, courier, carrier, client, service and provider (the company, not one configured mailbox on it), account (an anonymous relay has none), mailer, engine (the SQLAlchemy analogue, kept as an analogy only)

**Connection**: One live, authenticated link a backend opened.
A caller makes many sends over it before it closes permanently.
A backend can be shared.
A connection belongs to one thread and one `with`.
It holds a transport.
It does the preparation every send needs, then passes the message to the transport.
_Avoid_: session, channel, socket, link (prose only), backend (the configuration that opens one), transport (the object inside it that makes the network calls)

**Address**: One mailbox written as a string, either bare as `ada@example.com` or with a display name as `Ada Lovelace <ada@example.com>`.
Every address Epistole holds is a `str`.
`Address(name, email)` is a `str` subclass that writes the second form, so the caller never has to know the quoting rules.
Epistole checks only that a string holds exactly one address on one line, and that the address has something on both sides of its last `@`.
The mail service determines whether the mailbox exists, accepts mail, or may send.
_Avoid_: email address (the noun is _address_ on its own), addr, recipient (the role an address plays, not the value)

**Recipient**: One address in a message's to, cc, or bcc.
A backend submits to the union of the three, in that order with duplicates kept.
A refusal names one of them.
_Avoid_: addressee, target, destination

**From address**: The mailbox a backend sends from, with an optional display name.
It belongs to the backend, never to the message.
The mail service determines whether the backend may use it.
It is an address like any other, with the same type and the same check.
The check runs when the backend is constructed.
_Avoid_: sender (RFC 5322 `Sender` names the transmitter, a different header; `SenderRefusedError` names the service's refusal of this address and is the one place the word appears), from_, user_id, mailbox

**Credential**: What a backend holds to prove its identity to a mail service.
It is a username and password, or the inputs from which a token credential is built: a client secret, a certificate, a service account file, a user's saved consent, or the machine's own identity.
An anonymous relay takes none.
A caller passes one in as a value from the backend's own module.
A backend never accepts the vendor's API client built from one.
_Avoid_: client (the vendor SDK object), token (one short-lived output of a credential), bearer (the spelling of a token in an HTTP header), auth, login, key (one kind of secret), creds (blastula's spelling)

**Token credential**: The object Epistole builds from a credential at connect time.
It produces a fresh access token on demand, in the shape `get_token` defines.
The name and the shape are `azure-identity`'s, and `TokenCredential` is the exported Protocol that spells it.
A caller who already has one passes it in as a credential, and Epistole uses it unchanged.
_Avoid_: token source, provider, authenticator

**Transport**: The object that makes the network calls, which a backend opens and a connection holds.
It is the only code that uses SMTP, the Gmail API, or Microsoft Graph.
It submits submissions and closes.
It returns the refusals the mail service gave, and nothing more.
A third-party backend supplies one and nothing else.
_Avoid_: driver, dialect, wire, link, adapter (an auth adapter is the separate shim that connects a vendor token library to `httpx2`, never a transport), backend (the configuration that opens one), connection (the object that holds one)

**Send**: The operation a caller runs on a backend or a connection: prepare a message, then have the transport submit it.
A backend sends one message over a connection it opens and closes.
A connection sends many.
_Avoid_: deliver, transmit, execute (the SQLAlchemy analogue)

**Submit**: Pass a submission to the mail service over a transport.
It is the transport's half of a send.
Success means the service accepted the message, not that anyone received it.
_Avoid_: send (the caller's verb, which includes preparation), deliver

**Submission**: One message passed to one transport once, together with the from address it is sent under and the `Message-ID` and `Date` the send set on it.
It is the frozen value a connection builds and a transport receives.
Sending the same message twice makes two submissions with two ids.
`MemoryBackend` keeps every one it accepted, in `submissions`.
_Avoid_: delivery (acceptance never means anyone received it), send (the caller's verb), outbox (a mail client's outbox holds what it has not sent yet, which is the reverse)

**Complete message**: A message that has passed preparation and can be submitted.
It has at least one recipient, plain text, HTML whenever the caller supplied the content as HTML or Markdown, and an inline image for every `cid:` the HTML names.
Building the message guarantees the two content clauses.
The send checks the other two.
A submission holds only a complete message.
_Avoid_: prepared message, rendered message

**Send result**: What a send returns: the record that the service accepted one submission.
It holds the submission's `Message-ID` and `Date` and any refusals.
It never implies that anyone received the message.
A connection builds it from its submission and the refusals the transport returned.
A transport never builds one.
_Avoid_: receipt (reads as a delivery receipt), result (the Rust-style success-or-failure container), response, status, sent message

**Refusal**: A mail service refusing one recipient, with the code and reason it gave.
When some recipients are refused and the rest accepted, the send result holds the refusals.
When every recipient is refused, the send raises instead.
Only an SMTP service, and the double that substitutes for one, can refuse some recipients and accept the rest.
The two APIs accept or refuse the whole message.
_Avoid_: bounce (the non-delivery report the service sends later, which Epistole never receives), rejection (the whole-message case)

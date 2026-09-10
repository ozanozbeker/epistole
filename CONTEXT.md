# Epistole

Epistole is one API for building an email message and sending it through SMTP, the Gmail API, or Microsoft Graph without changing the calling code.
This glossary is the vocabulary the spec and the implementation share.

An _Avoid_ list names the words this project does not use for that concept in prose.
A public name may still spell one, where the name comes from a vendor, from an RFC, or from a neighbouring concept, and the entry says which.
`TokenCredential`, `.embed(cid=)`, `.headers()`, `SenderRefusedError`, and the auth adapters over `httpx2` are the five that do.

## Language

**Message**: The immutable value a caller builds: its content, its addressing, its attachments, and any custom headers.
It never carries a From address, a backend, or the identity of a submission, and every way of changing it hands back a new message.
_Avoid_: email, draft (Epistole exposes none; the Graph large-attachment path creates and deletes one inside a single send, and that is the only use of the word), mail

**Content**: What a message says: HTML the caller supplied or Epistole rendered from Markdown, together with plain text; or plain text alone.
_Avoid_: body (the HTML element, blastula's middle section, and RFC 5322's everything after the headers), payload, copy

**Plain text**: The readable text every message carries: what the caller wrote, the Markdown source, or what Epistole derived from the HTML.
It ships alongside the HTML or alone, except where a mail service substitutes its own, and a text-only client shows nothing else.
_Avoid_: fallback (it is the whole message when there is no HTML), alternative (the MIME spelling), text part

**Attachment**: Bytes with a filename and a content type that travel with a message.
The recipient's client lists it as a file, unless it is an inline image.
_Avoid_: file, part, MIME part

**Inline image**: An attachment the HTML body displays in place by naming its content id after `cid:`, never listed as a file.
A caller embeds one under a name the HTML already uses; Epistole makes one by rewriting a `data:` image it found.
_Inline_ names this mechanism alone; copying stylesheet rules onto `style` attributes is rewriting CSS, which Epistole never does.
_Avoid_: embedded image, body image, related part

**Content id**: The name an inline image answers to, unique within one message and deliberately not unique across messages.
It never carries an `@domain`.
_Avoid_: cid (the URL scheme, which `.embed(cid=)` names deliberately because that is what the HTML writes), Content-ID (the header spelling)

**Custom header**: A `Name: value` line the caller supplies and Epistole passes through untouched, such as `List-Unsubscribe` or a private `X-` tag.
It is never one of the headers Epistole writes itself, so setting a name Epistole owns raises rather than overriding it.
A message holds at most one value per name, and Graph carries only names starting with `x-`.
_Avoid_: header on its own (the addressing and MIME lines are headers too, so `.headers()` and `headers_` are RFC 5322's word and carry the caller's set alone), metadata, extra, field (RFC 5322's word for both kinds)

**Backend**: One configured route to a mail service, including the test doubles that stand in for one.
It owns the credentials, the from address, and every setting only its mail service understands; the message owns everything else, and a connection owns the live link.
A caller sends through it directly for one message, or opens a connection from it for many.
_Avoid_: transport (the wire object a backend opens, never the backend), sender, courier, carrier, client, service and provider (the company, not one configured mailbox on it), account (an anonymous relay has none), mailer, engine (the SQLAlchemy analogue, kept as an analogy only)

**Connection**: One live, authenticated link a backend opened, which carries many sends and then closes for good.
A backend can be shared; a connection belongs to one thread and one `with`.
It holds a transport and does the preparation every send needs before handing the message to it.
_Avoid_: session, channel, socket, link (prose only), backend (the configuration that opens one), transport (the wire object inside it)

**Address**: One mailbox written as a string, either bare as `ada@example.com` or with a display name as `Ada Lovelace <ada@example.com>`.
Every address Epistole holds is a `str`, and `Address(name, email)` is a `str` subclass that writes the second form so the caller never has to know the quoting rules.
Epistole checks only that a string holds exactly one address and that the address has something on both sides of its last `@`; whether the mailbox exists, accepts mail, or may send is the mail service's answer.
_Avoid_: email address (the noun is _address_ on its own), addr, recipient (the role an address plays, not the value)

**Recipient**: One address in a message's to, cc, or bcc.
The union, in that order with duplicates kept, is what a backend submits to, and a refusal names one of them.
_Avoid_: addressee, target, destination

**From address**: The mailbox a backend sends from, with an optional display name.
It belongs to the backend, never to the message, and the mail service decides whether the backend may use it.
It is an address like any other, taking the same type and the same check, run when the backend is constructed.
_Avoid_: sender (RFC 5322 `Sender` names the transmitter, a different header; `SenderRefusedError` names the service's no to this address and is the one place the word appears), from_, user_id, mailbox

**Credential**: What a backend holds to prove who it is to a mail service: a username and password, or the inputs from which a token source is built (a client secret, a certificate, a service account file, a user's saved consent, or the machine's own identity).
An anonymous relay takes none.
A caller hands one in as a value from the backend's own module; a backend never accepts the vendor's API client built on top of one.
_Avoid_: client (the vendor SDK object), token (one short-lived output of a credential), bearer (the wire spelling of a token), auth, login, key (one kind of secret), creds (blastula's spelling)

**Token source**: What Epistole builds from a credential at connect time: the object that produces a fresh access token on demand, in the shape `get_token` defines.
A caller who already has one hands it in as a credential and Epistole uses it unchanged.
_Avoid_: token credential (the vendor's name for the same shape; `TokenCredential` is the exported Protocol spelling it, kept so an `azure-identity` object is recognisable), provider, authenticator

**Transport**: The wire object a backend opens and a connection holds: the only code that speaks SMTP, the Gmail API, or Microsoft Graph.
It submits submissions and closes, answering with the refusals the mail service gave and nothing more; a third-party backend supplies one and nothing else.
_Avoid_: driver, dialect, wire, link, adapter (an auth adapter is the separate shim that makes a vendor token library speak to `httpx2`, never a transport), backend (the configuration that opens one), connection (the object that holds one)

**Send**: What a caller asks a backend or a connection to do with a message: prepare it, then have the transport submit it.
A backend sends one message over a connection it opens and closes; a connection sends many.
_Avoid_: deliver, transmit, execute (the SQLAlchemy analogue)

**Submit**: Hand a submission to the mail service over a transport.
It is the transport's half of a send, and success means the service accepted the message, not that anyone received it.
_Avoid_: send (the caller's verb, which includes preparation), deliver

**Submission**: One message handed to one transport once, together with the from address it goes out under and the `Message-ID` and `Date` the send stamped on it.
It is the frozen value a connection builds and a transport receives, so sending the same message twice makes two submissions with two ids.
`MemoryBackend` keeps every one it accepted, in `submissions`.
_Avoid_: delivery (acceptance never means anyone received it), send (the caller's verb), outbox (a mail client's outbox holds what has not gone yet, which is the reverse)

**Complete message**: A message that has passed preparation and can be submitted: at least one recipient, plain text present, HTML present whenever the content entered as HTML or Markdown, and every `cid:` the HTML names matched by an inline image the message holds.
Building the message guarantees the two content clauses; the send checks the other two.
A submission carries nothing else.
_Avoid_: prepared message, rendered message

**Send result**: What a send hands back: the record that the service accepted one submission.
It carries the submission's `Message-ID` and `Date` and any refusals, and it never implies that anyone received the message.
A connection builds it from the submission it stamped and the refusals the transport answered with; a transport never builds one.
_Avoid_: receipt (reads as a delivery receipt), result (the Rust-style success-or-failure container), response, status, sent message

**Refusal**: A mail service's no to one recipient, with the code and reason it gave.
Some recipients refused with the rest accepted rides on the send result; every recipient refused raises instead.
Only an SMTP service, and the double that stands in for one, can refuse some and accept the rest; the two APIs accept or refuse the whole message.
_Avoid_: bounce (the non-delivery report that arrives later, which Epistole never sees), rejection (the whole-message case)

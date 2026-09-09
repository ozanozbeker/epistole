# Herma

Herma is one API for building an email message and sending it through SMTP, the Gmail API, or Microsoft Graph without changing the calling code.
This glossary is the vocabulary the spec and the implementation share.

## Language

**Message**: The immutable value a caller builds: its content, its addressing, and its attachments.
It never carries a From address, a backend, or the identity of a submission, and every way of changing it hands back a new message.
_Avoid_: email, draft (the server-side resource v1 rules out), mail

**Attachment**: Bytes with a filename and a content type that travel with a message.
The recipient's client lists it as a file, unless it is an inline image.
_Avoid_: file, part, MIME part

**Inline image**: An attachment the HTML body displays in place by naming its content id after `cid:`, never listed as a file.
A caller embeds one under a name the HTML already uses; Herma makes one by rewriting a `data:` image it found.
_Avoid_: embedded image, body image, related part

**Content id**: The name an inline image answers to, unique within one message and deliberately not unique across messages.
It never carries an `@domain`.
_Avoid_: cid (the URL scheme), Content-ID (the header spelling)

**Backend**: One configured route to a mail service, including the test doubles that stand in for one.
It owns the credentials and the from address; the message owns everything else, and a connection owns the live link.
A caller sends through it directly for one message, or opens a connection from it for many.
_Avoid_: transport (the wire object a backend opens, never the backend), sender, courier, carrier, client, service and provider (the company, not one configured mailbox on it), account (an anonymous relay has none), mailer, engine (the SQLAlchemy analogue, kept as an analogy only)

**Connection**: One live, authenticated link a backend opened, which carries many sends and then closes for good.
A backend can be shared; a connection belongs to one thread and one `with`.
It holds a transport and does the preparation every send needs before handing the message to it.
_Avoid_: session, channel, socket, link (prose only), backend (the configuration that opens one), transport (the wire object inside it)

**Recipient**: One address in a message's to, cc, or bcc.
The union, in that order with duplicates kept, is what a backend submits to, and a refusal names one of them.
_Avoid_: addressee, target, destination

**From address**: The mailbox a backend sends from, with an optional display name.
It belongs to the backend, never to the message, and the mail service decides whether the backend may use it.
_Avoid_: sender (RFC 5322 `Sender` names the transmitter, a different header), from_, user_id, mailbox

**Transport**: The wire object a backend opens and a connection holds: the only code that speaks SMTP, the Gmail API, or Microsoft Graph.
It submits complete messages and closes; a third-party backend supplies one and nothing else.
_Avoid_: driver, dialect, wire, link, adapter, backend (the configuration that opens one), connection (the object that holds one)

**Send**: What a caller asks a backend or a connection to do with a message: prepare it, then have the transport submit it.
A backend sends one message over a connection it opens and closes; a connection sends many.
_Avoid_: deliver, transmit, execute (the SQLAlchemy analogue)

**Submit**: Hand a complete message to the mail service over a transport.
It is the transport's half of a send, and success means the service accepted the message, not that anyone received it.
_Avoid_: send (the caller's verb, which includes preparation), deliver

**Submission**: One message handed to one transport once.
It carries its own `Message-ID` and `Date`, so sending the same message twice makes two submissions.
_Avoid_: delivery (acceptance never means anyone received it), send (the caller's verb)

**Complete message**: A message that has passed preparation and can be submitted: at least one recipient, HTML and plain text both present, every `data:` image already an inline image, and every `cid:` the HTML names matched by an inline image the message holds.
A transport receives nothing else.
_Avoid_: prepared message, rendered message

**Send result**: What a send hands back: the record that the service accepted one submission.
It carries the submission's `Message-ID` and `Date` and any refusals, and it never implies that anyone received the message.
_Avoid_: receipt (reads as a delivery receipt), result (the Rust-style success-or-failure container), response, status, sent message

**Refusal**: A mail service's no to one recipient of an accepted submission, with the code and reason it gave.
Only SMTP can refuse some recipients and accept the rest; the two APIs accept or refuse the whole message.
_Avoid_: bounce (the non-delivery report that arrives later, which Herma never sees), rejection (the whole-message case)

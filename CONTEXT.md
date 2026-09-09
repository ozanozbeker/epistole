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
One comes from a caller embedding bytes under a name the HTML already uses, or from Herma rewriting a `data:` image it found.
_Avoid_: embedded image, body image, related part

**Content id**: The name an inline image answers to, unique within one message and deliberately not unique across messages.
It never carries an `@domain`.
_Avoid_: cid (the URL scheme), Content-ID (the header spelling)

**Backend**: One configured route to a mail service, including the test doubles that stand in for one.
It owns the credentials and the from address; the message owns everything else.
_Avoid_: transport, sender, courier, carrier, connection

**From address**: The mailbox a backend sends from, with an optional display name.
It belongs to the backend, never to the message, and the mail service decides whether the backend may use it.
_Avoid_: sender (RFC 5322 `Sender` names the transmitter, a different header), from_, user_id, mailbox

**Send**: What a caller does to a message: prepare it, then submit it over one backend.
_Avoid_: deliver, transmit

**Submit**: Hand a complete message to a backend for transmission.
It is the backend's half of a send, and success means the service accepted the message, not that anyone received it.
_Avoid_: send (the caller's verb, which includes preparation), deliver

**Submission**: One message handed to one backend once.
It carries its own `Message-ID` and `Date`, so sending the same message twice makes two submissions.
_Avoid_: delivery (acceptance never means anyone received it), send (the caller's verb)

**Complete message**: A message that has passed preparation and can be submitted: at least one recipient, HTML and plain text both present, every `data:` image already an inline image, and every `cid:` the HTML names matched by an inline image the message holds.
A backend receives nothing else.
_Avoid_: prepared message, rendered message

**Receipt**: What a send hands back: the record that one backend accepted one submission.
It carries the submission's `Message-ID` and any refusals, and it never implies that anyone received the message.
_Avoid_: result, response, status, sent message

**Refusal**: A mail service's no to one recipient of an accepted submission, with the code and reason it gave.
Only SMTP can refuse some recipients and accept the rest; the two APIs accept or refuse the whole message.
_Avoid_: bounce (the non-delivery report that arrives later, which Herma never sees), rejection (the whole-message case)

# Herma

Herma is one API for building an email message and sending it through SMTP, the Gmail API, or Microsoft Graph without changing the calling code.
This glossary is the vocabulary the spec and the implementation share.

## Language

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

**Complete message**: A message that has passed preparation and can be submitted: at least one recipient, HTML and plain text both present, and every `data:` image already an attachment referenced by `cid:`.
A backend receives nothing else.
_Avoid_: prepared message, rendered message

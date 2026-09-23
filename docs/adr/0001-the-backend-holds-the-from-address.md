# The backend holds the from address, not the message

Every library in `docs/research/prior-art.md` puts the From address on the message.
The send-boundary research recommended the same: expose `from_` and let the backend fail.
We put it on the backend instead.
Each real backend takes a required from address at construction.
The message has no From field at all.
A send cannot override it.
Decided on [#8](https://github.com/ozanozbeker/epistole/issues/8).
The from address became a required field on [#9](https://github.com/ozanozbeker/epistole/issues/9).

## Why

A From field on the message has one spelling on every backend and behaves differently on each.
SMTP writes whatever it receives, and the server accepts or refuses it.
Gmail and Graph restrict it to the authenticated mailbox.
An override is a server-side grant (Send As, a verified alias) that an administrator makes, not a request field.
A message whose From the backend cannot use holds a false address between build and send.

The caller has to supply the address anyway.
Anonymous SMTP has no username, so no credential field can supply the address.
Gmail's `gmail.send` scope does not permit `getProfile`, so under least privilege Epistole cannot read the account address.
Graph could leave `from` empty under a delegated token.
Under application permissions, the request path must name the mailbox regardless.
So requiring the address on every backend adds no requirement on Graph, and gives all three one shape.

Putting it on the backend keeps the Send As grant visible where the backend is constructed.
The alternative is a call site that returns `403` on Graph and succeeds with no warning on SMTP.

## Consequences

- Sending from two mailboxes means two backend objects.
  They can share one credential.
  A backend is cheap.
- `reply_to` stays on the message.
  It covers most reasons people want to set From.
- The caller must still give an anonymous SMTP relay its from address, because RFC 5322 requires the header and nothing else supplies it.
- The mail service accepts or refuses the address.
  Epistole writes it and reports the refusal: `SMTPSenderRefused` on SMTP and `403 ErrorSendAsDenied` on Graph.
  The docs do not state Gmail's behavior, and a live test must settle it.
- Epistole never derives the field from `username`.
  A default that works on one credential shape and not another is the per-backend exception the unified field exists to remove.

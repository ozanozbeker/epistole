# Sender identity lives on the backend, not the message

Every library in `docs/research/prior-art.md` puts the From address on the message, and the send-boundary research recommended the same: expose `from_` and let the backend fail.
We put it on the backend instead.
Each real backend takes a required from address at construction, the message has no From field at all, and there is no per-send override.
Decided on [#8](https://github.com/ozanozbeker/epistole/issues/8), made a required field on [#9](https://github.com/ozanozbeker/epistole/issues/9).

## Why

A From field on the message reads identically on every backend and behaves differently on each.
SMTP writes whatever it is given and the server decides.
Gmail and Graph pin it to the authenticated mailbox, and an override is a server-side grant (Send As, a verified alias) that an administrator makes, not a request field.
A message carrying a From it cannot honor is a document that lies about itself between build and send.

The address has to be caller-supplied anyway.
Anonymous SMTP has no username, so nothing on the credential can stand in for it.
Gmail's `gmail.send` scope cannot call `getProfile`, so Epistole cannot learn the account address under least privilege.
Graph could leave `from` empty under a delegated token, but application permissions need the mailbox in the request path regardless, so requiring it everywhere costs Graph nothing and gives all three one shape.

Putting it on the backend keeps the Send As grant visible where the backend is constructed, instead of at a call site that returns `403` on Graph and quietly succeeds on SMTP.

## Consequences

- Sending from two mailboxes means two backend objects.
  They can share one credential, and a backend is cheap.
- `reply_to` stays on the message and covers most reasons people reach for From.
- An anonymous SMTP relay must still be told its from address, because RFC 5322 requires the header and nothing else supplies it.
- Whether the address is legitimate is the mail service's call.
  Epistole writes it and surfaces the refusal: `SMTPSenderRefused` on SMTP, `403 ErrorSendAsDenied` on Graph, and on Gmail a behavior the docs do not state and a live test must settle.
- The field is never derived from `username`.
  A default that works on one credential shape and not another is the per-backend exception the unified field exists to remove.

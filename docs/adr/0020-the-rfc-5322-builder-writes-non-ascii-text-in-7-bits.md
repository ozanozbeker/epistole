# The RFC 5322 builder writes non-ASCII text in 7 bits

The RFC 5322 builder clones its policy with `cte_type="7bit"`.
`EmailMessage` then writes non-ASCII text as quoted-printable or base64.
So a message whose headers are ASCII is ASCII throughout, and SMTP never needs `BODY=8BITMIME` for it.
Decided on [#43](https://github.com/ozanozbeker/epistole/issues/43), from a finding on [#41](https://github.com/ozanozbeker/epistole/issues/41).

## Why

With the default `cte_type="8bit"`, `EmailMessage` writes a text part as raw UTF-8 labelled `8bit` when every line fits in 78 bytes.
`smtplib.send_message` adds `BODY=8BITMIME` to `MAIL FROM` only together with `SMTPUTF8`, for a non-ASCII envelope.
So SMTP sent content reading "Café" to an ASCII envelope as 8-bit data without `BODY=8BITMIME`.
RFC 6152 forbids that.
Nearly every server advertises `8BITMIME` and accepts such data anyway, so the failure was rare.

With `cte_type="7bit"`, `EmailMessage` encodes non-ASCII text as quoted-printable or base64, whichever its heuristic finds shorter, as it already did for a line longer than 78 bytes.
Measured on Python 3.13.12 and 3.14.7: "Café" becomes quoted-printable, a long CJK line stays base64, and attachments stay base64.

## Considered options

- **Pass `BODY=8BITMIME` when the server advertises `8BITMIME`.**
  Only the SMTP transport would change, and only for an ASCII envelope, because `send_message` adds its own copy for a non-ASCII one.
  Rejected because a server that does not advertise `8BITMIME` would still receive 8-bit data.

## Consequences

- Non-ASCII text is larger on the wire.
  A probe message with "Café" in its subject, plain text, and HTML grew from 578 to 610 bytes.
- Gmail's size pre-check measures the encoded message, so it counts the growth (ADR-0019).
- A message with UTF-8 headers still has 8-bit bytes in its headers.
  SMTP adds `SMTPUTF8` and `BODY=8BITMIME` to `MAIL FROM` for it (ADR-0014).

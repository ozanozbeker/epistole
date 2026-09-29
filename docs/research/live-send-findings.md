# Live-send findings

This file records what real sends returned, for [#23](https://github.com/ozanozbeker/epistole/issues/23).
`tests/test_live_smtp.py` makes the sends, so a rerun checks each answer again.
None of the answers below changes an ADR, a docstring, or a private constant.

## SMTP with a password, on iCloud

Checked on 2026-09-29 for [#66](https://github.com/ozanozbeker/epistole/issues/66).
Every send logged in to `smtp.mail.me.com` with the account's `@icloud.com` address and an app-specific password, and addressed the message to that same account.
IMAP on `imap.mail.me.com` then read the message back from the inbox.

**iCloud keeps the `Message-ID` Epistole sets.**
The message IMAP read back had the `Message-ID` that `SendResult.message_id` reported.
So on iCloud, a recipient sees the id that `send()` returns (ADR-0004).

**iCloud serves implicit TLS on port 465, as well as STARTTLS on port 587.**
Apple's iCloud Mail settings page lists only port 587.
A send with `security="tls"` and `port=465` kept its `Message-ID`, as the `security="starttls"` send on port 587 did.

**iCloud keeps a custom-domain from address and signs the message for that domain.**
`ozanozbeker.com` is an iCloud+ custom domain on the same account.
The message sent from an `ozanozbeker.com` address had that address in `From`, and a DKIM signature with `d=ozanozbeker.com`.
The `@icloud.com` send had a DKIM signature with `d=icloud.com`.

**iCloud refuses a from address the account does not own, in reply to `MAIL FROM`.**
For a send from `nobody@example.com`, iCloud replied `550 5.7.0 From address is not one of your addresses`.
`smtplib` raised `SMTPSenderRefused`, and Epistole raised `SenderRefusedError`, as the spec's SMTP mapping says for any code but `552`.

**A wrong app password raises `AuthenticationError`.**
This confirms what the README says under its first example.

## Anonymous SMTP, on localhost

Checked on 2026-09-29 for [#66](https://github.com/ozanozbeker/epistole/issues/66).
The ticket names Mailpit, but this check used `aiosmtpd`, because `uvx aiosmtpd -n -l localhost:1025` runs it without an install.

**A local SMTP server accepts an anonymous plaintext send.**
The server accepted a send with `credential=None` and `security="none"`, and refused no recipient.

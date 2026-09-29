# Live-send findings

This file records what real sends returned, for [#23](https://github.com/ozanozbeker/epistole/issues/23).
`tests/test_live_smtp.py` makes the sends, so a rerun checks each answer again.
Only one answer below changes Epistole: a wrong Gmail app password raises the wrong class, and [#71](https://github.com/ozanozbeker/epistole/issues/71) tracks the fix.

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

## SMTP with an app password, on Gmail

Checked on 2026-09-29.
Every send logged in to `smtp.gmail.com` with the account's `@gmail.com` address and an app password, and addressed the message to that same account.
IMAP on `imap.gmail.com` then read the message back from `[Gmail]/All Mail`.
An app password needs 2-Step Verification on the Google Account, and the account's [security page](https://myaccount.google.com/security) creates one under App passwords.

**Gmail keeps the `Message-ID` Epistole sets, over STARTTLS on port 587 and implicit TLS on port 465.**
The message IMAP read back had the `Message-ID` that `SendResult.message_id` reported.

**Gmail rewrites a from address the account does not own, and replies with no error.**
A send from `nobody@example.com` returned a `SendResult`.
The message IMAP read back had the account's own address in `From`.
So on Gmail, `send()` succeeds while the recipient sees a different sender than `from_address`.

**A wrong app password can raise `TransportError`, not `AuthenticationError`.**
In two of three attempts, Gmail replied `535 5.7.8 Username and Password not accepted` to `AUTH PLAIN`, then closed the connection.
`smtplib.SMTP.login` moved on to `AUTH LOGIN` on the closed socket and raised `SMTPServerDisconnected`, which Epistole maps to `TransportError`.
In the third, Gmail kept the connection open, as iCloud did in every attempt, and `login` raised `SMTPAuthenticationError`.
Issue [#71](https://github.com/ozanozbeker/epistole/issues/71) tracks the fix.

## Anonymous SMTP, on localhost

Checked on 2026-09-29 for [#66](https://github.com/ozanozbeker/epistole/issues/66).
The ticket names Mailpit, but this check used `aiosmtpd`, because `uvx aiosmtpd -n -l localhost:1025` runs it without an install.

**A local SMTP server accepts an anonymous plaintext send.**
The server accepted a send with `credential=None` and `security="none"`, and refused no recipient.

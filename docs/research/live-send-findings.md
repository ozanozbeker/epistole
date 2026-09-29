# Live-send findings

This file records what real sends returned, for [#23](https://github.com/ozanozbeker/epistole/issues/23).
`tests/test_live_smtp.py` and `tests/test_live_gmail.py` make the sends, so a rerun checks each answer again.
Three answers below changed the repo.
A wrong Gmail app password can raise the wrong class, and [#71](https://github.com/ozanozbeker/epistole/issues/71) tracks the fix.
The Gmail API replaces the `Message-ID` and rewrites a from address the account does not own, and ADR-0001, ADR-0004, ADR-0011 and the docstrings now say so.

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

## The Gmail API, with a saved consent

Checked on 2026-09-29 for [#68](https://github.com/ozanozbeker/epistole/issues/68).
The consent came from the maintainer's own Google Cloud project, whose OAuth client is a Desktop app.
The project stayed in Testing with the account as a test user, because publishing it asked for an app logo and an application domain.
`google-auth-oauthlib`'s `InstalledAppFlow.run_local_server()` ran the consent in a browser once, and it granted `gmail.send` and `https://mail.google.com/`.
Every send went through `GmailBackend` with `gmail.AuthorizedUser` to the account itself, and the Gmail API read the message back by its subject.

**The Gmail API replaces the `Message-ID` Epistole sets.**
Both messages had a `Message-ID` ending in `@mail.gmail.com>`, not the one `SendResult.message_id` reported.
Gmail stored each as one message with the `SENT` and `INBOX` labels, so a recipient sees the replaced id.
Epistole cannot read the replaced id, because `messages.get` needs a scope that reads mail, and Epistole requests only `gmail.send`.

**The Gmail API sends from an address the account does not own, with the account's own address in `From`.**
A send from `nobody@example.com` returned a `SendResult`, and nothing raised.
Gmail over SMTP does the same.

## Anonymous SMTP, on localhost

Checked on 2026-09-29 for [#66](https://github.com/ozanozbeker/epistole/issues/66).
The ticket names Mailpit, but this check used `aiosmtpd`, because `uvx aiosmtpd -n -l localhost:1025` runs it without an install.

**A local SMTP server accepts an anonymous plaintext send.**
The server accepted a send with `credential=None` and `security="none"`, and refused no recipient.

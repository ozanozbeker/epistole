# Epistole

A single Python API for sending email, regardless of the backend.

`epistole` takes an email you have already composed as HTML and sends it through whichever service you have configured, using the same interface each time.
Supported backends are SMTP, Microsoft Graph, and Google, with room for more.
Switching providers means changing configuration, not rewriting your code.

This is an early project and the API is not yet stable.

## User guide

Work in progress.
Written while the API is still being designed, so the names are provisional and none of this runs yet.
The shapes are settled: a `Message` is an immutable value you build by chaining, a backend holds the credentials and the from address, and `backend.send(message)` or `connection.send(message)` sends it.

### One report, one recipient

```python
from pathlib import Path
from epistole import Message, SMTPBackend

smtp = SMTPBackend(host="mail.corp.example", port=587, from_address="reports@corp.example", ...)

smtp.send(Message(html=Path("kpis.html").read_text(encoding="utf-8")).subject("Daily KPIs").to("boss@corp.example"))
```

The backend opens a connection, authenticates, submits, and closes, all inside that one call.
A wrong password raises `AuthenticationError` on that line.
Swap `SMTPBackend` for `GraphBackend` or `GmailBackend` and nothing else changes.

### One report, many recipients

```python
report = (
    Message(html=Path("weekly.html").read_text(encoding="utf-8"))
    .subject("Weekly numbers")
    .attach(Path("weekly.pdf"))
)

with smtp.connect() as connection:
    for subscriber in subscribers:
        connection.send(report.to(subscriber.email))
```

One authentication, then one send per subscriber over the same connection.
`.to()` replaces the recipient list on a copy, so each subscriber sees only their own address and the PDF is encoded once.

If subscriber 140 has a dead mailbox, that send raises `RecipientsRefusedError` and the connection stays open, so wrap the send in `try` and log it.
If the mail server restarts at subscriber 200, that send raises `TransportError`, the loop ends, and the connection closes quietly on the way out.
Nothing is skipped silently.

### Forgot `connect()`

```python
for subscriber in subscribers:
    smtp.send(report.to(subscriber.email))
```

Still correct, only slower: one handshake per subscriber.
A relay with a rate limit may push back partway through, which surfaces as `ProviderError`.
Use `connect()` for loops.

### Kept a connection past its `with`

```python
with smtp.connect() as connection:
    pass

connection.send(report)
```

Raises `ValueError`, because the connection is closed.
This is a mistake in the calling code, not a mail failure, so it is not a `EpistoleError` and `except EpistoleError` does not swallow it.
A connection is one link, used once; to send again, call `connect()` again.

### Notebook, two cells, Graph

Cell one:

```python
connection = graph.connect()
```

The token is acquired here, so a bad tenant id fails here rather than on the first send.

Cell two, an hour later:

```python
connection.send(message)
```

The connection refreshes its token through the credential you gave the backend, so an expired token is not an error.
Only a refresh that itself fails raises `AuthenticationError`, and the connection stays open either way.
Leaving the connection unclosed at the end of a notebook leaks nothing on Graph or Gmail.
On SMTP it leaves a socket open until the server times it out, which is why the loop above uses `with`.

### Threads

A backend is immutable and safe to share.
A connection is not: use one per thread, the same rule as a DB-API connection.
Epistole does not lock a connection for you; two threads on one connection is a bug in the caller.

### Markdown instead of HTML

```python
note = (
    Message(markdown="## Numbers\n\nSee the [dashboard](https://kpi.example).")
    .subject("Numbers")
    .to("boss@corp.example")
)
```

Needs the extra: `pip install "epistole[markdown]"`.
Without it, this line raises `ImportError` naming the extra.
The Markdown renders to HTML for clients that show it, and the source you wrote is the plain text for clients that do not.
Exactly one of `html=` or `markdown=` per message.

### Plain text only

```python
smtp.send(
    Message(text="Pipeline failed at 03:12. See run 4821.")
    .subject("Pipeline failed")
    .to("oncall@corp.example")
)
```

No HTML part is made; the message is `text/plain` and every client renders it.

### A better plain-text part

Every HTML message carries plain text.
Epistole derives it with a small extractor of its own, which keeps links, marks list items, and drops the stylesheet.
To supply your own, pass `text=` and nothing is derived:

```python
Message(html=body, text=Path("weekly.txt").read_text(encoding="utf-8"))
```

To derive it with a library you prefer, pass `text_renderer=`, a callable from HTML to text.
It runs once, after Epistole has moved `data:` images out of the HTML, so no base64 lands in the text.

```python
from inscriptis import get_text
from inscriptis.model.config import ParserConfig

config = ParserConfig(display_links=True)

Message(html=body, text_renderer=lambda h: get_text(h, config))
```

`inscriptis` aligns table columns, which Epistole's extractor does not.
`html2text` works the same way through `HTML2Text().handle`; set `unicode_snob = True` on it or `Café` arrives as `Cafe`, and note its licence is GPL-3.0-or-later.
The default is exported as `epistole.html_to_text` if you want to wrap it.

## Choosing a backend

Epistole sends the same message through any backend, so choosing one is a deployment decision, not a code decision.

Use **SMTP** unless something stops you.
It works with every mail system, it carries the largest messages, and it sends exactly the MIME Epistole built.

Use **Graph** when your tenant has turned SMTP AUTH off, or when you need a retry hint on throttling.
Accept its 4 MB body limit before you choose it.

Use **Gmail** when you are already authenticated against a Google account and would rather not manage an SMTP credential.

| | SMTP | Gmail | Graph |
| --- | --- | --- | --- |
| Mail systems served | any | Google accounts | Exchange Online |
| Largest body | whole-message limit | whole-message limit | **4 MB, no path past it** |
| Largest message | server `SIZE`, 35 MB on a default Exchange Online tenant | 25 MB before encoding | 35 MB default, 1 MB to 150 MB configurable |
| Largest attachment | shares the message limit | shares the message limit | 150 MB, via upload session |
| Per-recipient refusals | visible | not expressible | not expressible |
| Retry hint | none | none documented | `Retry-After` |
| MIME you send | is what arrives | is what arrives | rebuilt by Exchange |
| Recipients per message | server policy | 500 | 500 |
| Credentials | anonymous, password, or OAuth | Google credentials | token credential |

Four things decide it.

**Body size.**
Graph caps the entire write request at 4 MB and has no chunked path for a message body, so a large embedded HTML report cannot be sent through it at all.
SMTP and Gmail measure against the whole message, so a body of several MB is routine on both.
If you send through Graph, attach the report as a file and keep the body small.

**Whether your tenant allows SMTP AUTH.**
On Exchange Online, security defaults and any policy that blocks basic authentication switch SMTP client submission off, and the trend runs one way.
Graph keeps working through all of it.
The per-mailbox SMTP AUTH setting overrides the organization setting, so one enabled mailbox is the documented workaround.

**Fidelity against features.**
SMTP and Gmail take the complete RFC 5322 message Epistole builds, so what you send is what arrives.
Graph takes a flat JSON array and Exchange serializes the MIME later, so Epistole can guarantee your `cid:` references resolve but not the MIME structure around them.
In exchange, Graph is the only backend that tells you how long to wait when it throttles you.

**What the permission costs.**
For a plain send the three are comparable: `SMTP.SendAsApp`, the `gmail.send` scope, `Mail.Send`.
Above 3 MB of attachment Graph needs a draft, which needs `Mail.ReadWrite`, which grants reading every message in scope.
Keep attachments under 3 MB if you send through Graph and a security reviewer will thank you.

`ConsoleBackend` and `MemoryBackend` are backends like any other; swapping one in is the same one-word change.

Limits quoted on 2026-09-08 and they move; re-check before relying on one.
Sources: [Graph request limits](https://learn.microsoft.com/en-us/graph/use-the-api), [Graph large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments), [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits), [Gmail sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace), [Exchange rebuilds MIME](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail), [SMTP `SIZE`, RFC 1870](https://datatracker.ietf.org/doc/html/rfc1870), [SMTP AUTH on Exchange Online](https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/authenticated-client-smtp-submission).
Fuller working is in `docs/research/send-boundary-semantics.md` and `docs/research/attachment-and-inline-rules.md`.

## About the name

An epistole was a stone marker set at crossroads and roadsides in ancient Greece.
Travelers used them to tell which road led where.
The name fits a library whose job is to take one message and direct it down whichever road you have chosen.

## Credit

`epistole` is inspired by [blastula](https://github.com/rstudio/blastula), an R package for composing and sending email.
It is not a port, and the API does not mirror blastula's.

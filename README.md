# Epistole

A single Python API for sending email, regardless of the backend.

`epistole` takes an email you have already composed as HTML and sends it through whichever service you have configured, using the same interface each time.
Supported backends are SMTP, Microsoft Graph, and Google, with room for more.
Switching providers means changing configuration, not rewriting your code.

This is an early project and the API is not yet stable.

> **Epistole** (ἐπιστολή, epistolē) is the Greek word for a letter or written message sent from one person to another.
> The word is also the source of the English epistle.

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

## Writing HTML for email

Epistole never composes HTML.
You supply it finished, and this section is what that costs you.
Every constraint below is recipient-side: it applies to every message Epistole sends over every backend, and no backend choice avoids it.
Paste this section into the prompt when a model writes the HTML for you.

### Choose how the content enters

`html=` is for a rendered report: Quarto, Pandoc, or a self-contained page a model wrote.
The rest of this section is about that case.

`markdown=` is for mail you write by hand.
It renders through `epistole[markdown]` on the CommonMark preset, so tables and footnotes are not available in v1; render those yourself and pass `html=`.
The Markdown source is the plain text, so what you wrote is what a text client shows.

`text=` alone is for alerts.
There is no HTML part and nothing below applies.

An HTML message carries plain text as well.
Epistole derives it with its own extractor, `text=` replaces it outright, and `text_renderer=` swaps the extractor.

### Charts are static images or they are nothing

No email client runs JavaScript.
A plotly figure is an empty `<div>` that `Plotly.newPlot` fills on load, so it arrives empty and stays that way.
So does anything else that draws itself in the browser.

Write the figure to a PNG and reference it from an `<img>`.
`fig.write_image("chart.png")` does that for plotly and needs `kaleido`; matplotlib's `savefig` already works this way.
This is the constraint most often broken by a request for an interactive dashboard in an email.

### Put every image in an `<img>` tag

Gmail renders no `data:` URI image on any of its four surfaces: desktop webmail, mobile webmail, and the iOS and Android apps.
That is community testing rather than a Google statement, and the desktop row was last retested in 2024-05.

So `Message(html=...)` rewrites every `data:` image it finds in an `<img src>` into an inline image: the bytes travel as an attachment and the tag points at them with `cid:`.
Quarto's `embed-resources: true` produces exactly that construct, and you do not have to do anything about it.

The rewrite reaches `<img src>` and nothing else.
A `data:` image inside a CSS `url()`, inside a `srcset`, or inside a conditional comment such as `<!--[if mso]>` stays as written, and Gmail will not show it.
There is nowhere to move those bytes to, because `cid:` inside CSS has no reliable client support.
If an image has to render, give it an `<img>` tag rather than a `background-image`.

An image you already hold as a file skips the round trip:

```python
Message(html=body).embed(Path("logo.png"))
```

The content id defaults to the filename, so the HTML refers to it as `<img src="cid:logo.png">`.

### Style from a `<style>` block in `<head>`

A `<head>` stylesheet reaches further than email folklore says.
Community testing records full or partial support in Apple Mail, Outlook.com, Outlook for macOS, Outlook for Windows 2007 through 2019, Yahoo, Thunderbird, ProtonMail and Gmail desktop webmail.
The one outright hole is Gmail mobile webmail, recorded as no support since 2020-02.

Two caveats come with it.
On Outlook for Windows a rule must be declared before the element it styles.
Gmail desktop webmail keeps the first 16 KB of your `<style>` and drops the rest, a figure from community testing; Google publishes no limit at all, and the 8192 figure repeated elsewhere is a superseded 2017 measurement.

Treat `@media` and `:hover` as decoration.
They fail in the same clients that ignore the stylesheet, and Outlook for Windows supports neither.

Lay out with tables.
Microsoft's only first-party document on this covers Outlook 2007 and lists `position`, `float`, `max-width`, `min-width` and `overflow` as unsupported.
Nothing equivalent has been published since.

### Watch the total size

Gmail clips a message at roughly 102,400 bytes and hides the rest behind a "View entire message" link.

Epistole never warns you about this.
The number is vendor documentation rather than Google's, and [hteumeuleu/email-bugs#41](https://github.com/hteumeuleu/email-bugs/issues/41) collects reports of clipping below it, so there is no threshold Epistole could defend.
Measure your own HTML with `len(html.encode("utf-8"))`.

Clipping is recipient-side.
Every recipient on Gmail meets it whichever backend sent the message, and a Workspace address does not end in `@gmail.com`.
Backend ceilings are the separate problem in the next section, where Graph's 4 MB is the one that stops you.

### Making a large report fit

A Quarto report rendered with `embed-resources: true` runs to about a megabyte before any figure goes in.
Measured on a 1,188,695-byte report: 993,049 characters of CSS and 155,053 of `<script>` wrapped around under 400 characters of prose.

Two edits shrink it, and the first matters more than the advice you usually hear.

| What you send | Bytes |
| --- | --- |
| The report as Quarto rendered it | 1,188,695 |
| Scripts stripped | 996,201 |
| CSS rewritten onto elements | 195,706 |
| Both | 3,212 |

Stripping the scripts is yours to do, and it is safe: none of that JavaScript was going to run.
Rewriting the CSS onto elements is `css-inline`, a package Epistole does not depend on:

```python
import css_inline

Message(html=css_inline.inline(html))
```

Know two things before you run it.

It raises `InlineError` on a Quarto `embed-resources` report.
Pandoc leaves a stylesheet as `<link href="data:text/css,...">` whenever the CSS contains `</`, and `css-inline` resolves that `href` as a filesystem path.
Strip those `<link>` tags first.
Their CSS goes with them, and in the measured report that cost nothing: the output was 195,706 bytes either way.

It also drops every `:hover` rule, and by default every `@media` block.
`keep_at_rules=True` saves the `@media` blocks and does not save the `:hover` rules.
A responsive layout disappears with no signal.

Epistole does none of this for you.
The only edit `Message(html=...)` makes to your HTML is the `<img src>` rewrite above.

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
`MemoryBackend` records what it accepted as `backend.submissions`, so a test reads `submissions[0].message.to_`, and `ConsoleBackend` prints a readable rendering rather than the raw bytes of any one backend's wire form.

Limits quoted on 2026-09-08 and they move; re-check before relying on one.
Sources: [Graph request limits](https://learn.microsoft.com/en-us/graph/use-the-api), [Graph large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments), [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits), [Gmail sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace), [Exchange rebuilds MIME](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail), [SMTP `SIZE`, RFC 1870](https://datatracker.ietf.org/doc/html/rfc1870), [SMTP AUTH on Exchange Online](https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/authenticated-client-smtp-submission).
Fuller working is in `docs/research/send-boundary-semantics.md` and `docs/research/attachment-and-inline-rules.md`.

## Credit

`epistole` is inspired by [blastula](https://github.com/rstudio/blastula), an R package for composing and sending email.
It is not a port, and the API does not mirror blastula's.

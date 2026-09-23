# Epistole

Epistole is a single Python API for sending email, regardless of the backend.

Epistole takes a message you have already composed as HTML and sends it through whichever backend you have configured.
The interface is the same each time.
Supported backends are SMTP, Microsoft Graph, and Google.
The design allows more.
Switching providers means changing configuration, not rewriting your code.

This is an early project and the API is not yet stable.

> **Epistole** (ἐπιστολή, epistolē) is the Greek word for a letter or written message sent from one person to another.
> The word is also the source of the English epistle.

## User guide

This guide is a work in progress.
It describes an API that is still being designed, so the names are provisional.
None of this runs yet.
The shapes are settled.
A `Message` is an immutable value you build by chaining.
A backend holds the credentials and the from address.
`backend.send(message)` or `connection.send(message)` sends the message.

### One report, one recipient

```python
from pathlib import Path
from epistole import Message, SMTPBackend

smtp = SMTPBackend(
    host="mail.corp.example",
    port=587,
    from_address="reports@corp.example",
    credential=...,
)

smtp.send(
    Message(html=Path("kpis.html").read_text(encoding="utf-8"))
    .subject("Daily KPIs")
    .to("boss@corp.example")
)
```

The backend opens a connection, authenticates, submits, and closes, all inside that one call.
With a wrong password, that line raises `AuthenticationError`.

The message you build and the code that sends it are the same on every backend.
Only the constructor differs:

```python
from epistole import GmailBackend, GraphBackend, SMTPBackend
from epistole import gmail, graph, smtp

SMTPBackend(
    host="mail.corp.example",
    port=587,
    security="starttls",
    from_address="reports@corp.example",
    credential=smtp.Password(username="reports", password=...),
)

GraphBackend(
    from_address="reports@corp.example",
    credential=graph.ClientSecret(tenant_id=..., client_id=..., client_secret=...),
)

GmailBackend(
    from_address="reports@corp.example",
    credential=gmail.ServiceAccount(
        path=Path("service-account.json"), subject="reports@corp.example"
    ),
)
```

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

The connection authenticates once, then makes one send per subscriber.
`.to()` replaces the recipient list on a copy, so each subscriber sees only their own address.
`.attach()` reads the PDF from disk once, not once per subscriber.

If subscriber 140's mailbox no longer accepts mail, that send raises `RecipientsRefusedError`.
The connection stays open, so wrap the send in `try` and log the error.
If the mail server restarts at subscriber 200, that send raises `TransportError` and the loop ends.
The connection closes without raising as the `with` block exits.
Nothing is skipped silently.

### Forgot `connect()`

```python
for subscriber in subscribers:
    smtp.send(report.to(subscriber.email))
```

This loop is still correct, only slower.
It makes one handshake per subscriber.
A relay with a rate limit may throttle the loop partway through.
The throttled send raises `ProviderError`.
Use `connect()` for loops.

### Kept a connection past its `with`

```python
with smtp.connect() as connection:
    pass

connection.send(report)
```

The last line raises `ValueError`, because the connection is closed.
It is a mistake in the calling code, not a mail failure, so it is not an `EpistoleError`.
`except EpistoleError` does not catch it.
A connection cannot be reopened.
To send again, call `connect()` again.

### Notebook, two cells, Graph

Cell one opens the connection:

```python
connection = graph.connect()
```

This line acquires the token.
With a bad tenant id, it fails here rather than on the first send.

Cell two runs an hour later:

```python
connection.send(message)
```

The connection refreshes its token through the credential you gave the backend, so an expired token is not an error.
A refresh that fails for a reason other than the network raises `AuthenticationError` and leaves the connection open.
A refresh that fails on the network raises `TransportError`.
Like any transport failure, that closes the connection.
An unclosed connection holds a socket on SMTP and a connection pool on Graph and Gmail until the object is garbage collected.
Use `with backend.connect()` for a loop.
For one message, use `backend.send()`, which closes the connection for you.

### Threads

A backend is immutable and safe to share.
A connection is not.
Use one per thread, the same rule as for a DB-API connection.
Epistole does not lock a connection for you.
Two threads on one connection is a bug in the caller.
The one exception is `MemoryBackend.submissions`, which every send appends to.
Appending is atomic, so the list cannot be corrupted.
But concurrent sends append in completion order.
A test that asserts on order sends from one thread.

### Markdown instead of HTML

```python
note = (
    Message(markdown="## Numbers\n\nSee the [dashboard](https://kpi.example).")
    .subject("Numbers")
    .to("boss@corp.example")
)
```

Markdown needs the extra: `pip install "epistole[markdown]"`.
Without it, this line raises `ImportError` naming the extra.
Epistole renders the Markdown to HTML for clients that show HTML.
The source you wrote is the plain text for clients that do not.
Pass exactly one of `html=` or `markdown=` per message.

### Plain text only

```python
smtp.send(
    Message(text="Pipeline failed at 03:12. See run 4821.")
    .subject("Pipeline failed")
    .to("oncall@corp.example")
)
```

Epistole makes no HTML part.
The message is `text/plain`, which every client renders.

### A better plain-text part

Every HTML message carries plain text.
Epistole derives it with a small extractor of its own.
The extractor keeps links, marks list items, and drops the stylesheet.
To supply your own, pass `text=`, and Epistole derives nothing:

```python
Message(html=body, text=Path("weekly.txt").read_text(encoding="utf-8"))
```

To derive it with a library you prefer, pass `text_renderer=`, a callable from HTML to text.
Epistole calls it once, after moving `data:` images out of the HTML.
So the text holds no base64.

```python
from inscriptis import get_text
from inscriptis.model.config import ParserConfig

config = ParserConfig(display_links=True)

Message(html=body, text_renderer=lambda h: get_text(h, config))
```

`inscriptis` aligns table columns, which Epistole's extractor does not.
`html2text` works the same way through `HTML2Text().handle`.
Set `unicode_snob = True` on it, or it writes `Café` as `Cafe`.
Its licence is GPL-3.0-or-later.
Epistole exports the default as `epistole.html_to_text` if you want to wrap it.

## Writing HTML for email

Epistole never composes HTML.
You supply it finished.
This section covers what you must handle as a result.
Every constraint below is recipient-side.
It applies to every message Epistole sends, over every backend.
No choice of backend avoids it.
Paste this section into the prompt when a model writes the HTML for you.

### Choose how the content enters

`html=` is for a rendered report: Quarto, Pandoc, or a self-contained page a model wrote.
The rest of this section is about that case.

`markdown=` is for a message you write by hand.
Epistole renders it through `epistole[markdown]` on the CommonMark preset, so tables and footnotes are not available in v1.
Render those yourself and pass `html=`.
The Markdown source is the plain text, so a text client shows exactly what you wrote.

`text=` alone is for alerts.
The message has no HTML part.
Nothing below applies.

An HTML message carries plain text as well.
Epistole derives it with its own extractor.
`text=` replaces it outright.
`text_renderer=` swaps the extractor.

### Charts are static images or they are nothing

No email client runs JavaScript.
A plotly figure is an empty `<div>` that `Plotly.newPlot` fills on load.
The recipient receives it empty, and nothing ever fills it.
Anything else that JavaScript draws in the browser is empty too.

Write the figure to a PNG and reference it from an `<img>`.
`fig.write_image("chart.png")` does that for plotly and needs `kaleido`.
For matplotlib, `savefig` already works this way.
This is the constraint most often broken by a request for an interactive dashboard in a message.

### Put every image in an `<img>` tag

Gmail renders no `data:` URI image on any of its four clients: desktop webmail, mobile webmail, and the iOS and Android apps.
The source is community testing, not a statement from Google.
The desktop row was last retested in 2024-05.

So `Message(html=...)` rewrites every `data:` image it finds in an `<img src>` into an inline image.
The bytes become an attachment.
The tag references them with `cid:`.
Quarto's `embed-resources: true` produces exactly that construct.
You do not have to do anything about it.

The rewrite applies to `<img src>` and nothing else.
A `data:` image inside a CSS `url()`, inside a `srcset`, or inside a conditional comment such as `<!--[if mso]>` stays as written.
Gmail will not show it.
There is nowhere to move those bytes to, because `cid:` inside CSS has no reliable client support.
If an image has to render, give it an `<img>` tag rather than a `background-image`.

For an image you already hold as a file, skip the round trip:

```python
Message(html=body).embed(Path("logo.png"))
```

The content id defaults to the filename, so the HTML refers to it as `<img src="cid:logo.png">`.
Two embeds under one content id raise `ValueError`.
Give each image a distinct filename, or pass `cid=`.

### Style from a `<style>` block in `<head>`

A `<head>` stylesheet works in more clients than the usual email advice says.
Community testers record full or partial support in Apple Mail, Outlook.com, Outlook for macOS, Outlook for Windows 2007 through 2019, Yahoo, Thunderbird, ProtonMail and Gmail desktop webmail.
Gmail mobile webmail is the one client with no support at all.
Testers have recorded it that way since 2020-02.

Two caveats apply.
On Outlook for Windows a rule must be declared before the element it styles.
Gmail desktop webmail keeps the first 16 KB of your `<style>` and drops the rest.
That figure comes from community testing.
Google publishes no limit at all.
The 8192 figure repeated elsewhere is a superseded 2017 measurement.

Treat `@media` and `:hover` as decoration.
They fail in the same clients that ignore the stylesheet.
Outlook for Windows supports neither.

Lay out with tables.
Microsoft's only first-party document on this covers Outlook 2007.
It lists `position`, `float`, `max-width`, `min-width` and `overflow` as unsupported.
Microsoft has published nothing equivalent since.

### Watch the total size

Gmail clips a message at roughly 102,400 bytes and hides the rest behind a "View entire message" link.

Epistole never warns you about this.
The number comes from vendor documentation, not from Google's.
The issue [hteumeuleu/email-bugs#41](https://github.com/hteumeuleu/email-bugs/issues/41) holds reports of clipping below it.
So there is no threshold Epistole could justify.
Measure your own HTML with `len(html.encode("utf-8"))`.

Clipping is recipient-side.
Gmail clips the message for every recipient on Gmail, whichever backend sent it.
A Workspace address does not end in `@gmail.com`.
Backend size limits are a separate problem, covered in [Choosing a backend](#choosing-a-backend).
There, Graph's 4 MB is the limit that stops a send.

### Making a large report fit

A Quarto report rendered with `embed-resources: true` is about a megabyte before you add any figure.
One measured report was 1,188,695 bytes.
It held 993,049 characters of CSS and 155,053 of `<script>`.
Its prose was under 400 characters.

Two edits shrink it.
The first matters more than the advice you usually hear.

| What you send | Bytes |
| --- | --- |
| The report as Quarto rendered it | 1,188,695 |
| Scripts stripped | 996,201 |
| CSS rewritten onto elements | 195,706 |
| Both | 3,212 |

You strip the scripts yourself.
That is safe, because none of that JavaScript was going to run.
`css-inline`, a package Epistole does not depend on, rewrites the CSS onto elements:

```python
import css_inline

Message(html=css_inline.inline(html))
```

Know two things before you run it.

It raises `InlineError` on a Quarto `embed-resources` report.
Pandoc leaves a stylesheet as `<link href="data:text/css,...">` whenever the CSS contains `</`.
`css-inline` resolves that `href` as a filesystem path.
Strip those `<link>` tags first.
That removes their CSS too.
In the measured report, the removal made no difference: the output was 195,706 bytes either way.

It also drops every `:hover` rule, and by default every `@media` block.
`keep_at_rules=True` saves the `@media` blocks and does not save the `:hover` rules.
You lose a responsive layout without a warning.

Epistole does none of this for you.
The only edit `Message(html=...)` makes to your HTML is the `<img src>` rewrite above.

## Choosing a backend

Epistole sends the same message through any backend, so choosing one is a deployment decision, not a code decision.

Use **SMTP** unless something stops you.
It works with every mail system.
It carries the largest messages.
It sends exactly the MIME Epistole built.

Use **Graph** when your tenant has turned SMTP AUTH off, or when you need a retry hint on throttling.
Accept its body limit before you choose it.
Epistole treats it as 4 MB, taken conservatively from Microsoft's unitless "4 MB".
That figure is not yet measured against a live tenant.

Use **Gmail** when you are already authenticated against a Google account and would rather not manage an SMTP credential.

| | SMTP | Gmail | Graph |
| --- | --- | --- | --- |
| Mail systems served | any | Google accounts | Exchange Online |
| Largest body | whole-message limit | whole-message limit | **4 MB, no path past it** |
| Largest message | server `SIZE`, 35 MB on a default Exchange Online tenant | 25 MB of attachment, 35 MB of request | 35 MB default, 1 MB to 150 MB configurable |
| Largest attachment | shares the message limit | shares the message limit | 150 MB, via upload session |
| Per-recipient refusals | visible | not expressible | not expressible |
| Retry hint | none | none documented | `Retry-After` |
| MIME you send | unchanged | unchanged | rebuilt by Exchange |
| Recipients per message | server policy | 500 | 500 |
| Credentials | anonymous, `Password`, or `OAuth` | `ServiceAccount` or `AuthorizedUser` | `ClientSecret`, `Certificate`, or `ManagedIdentity` |

Gmail and Graph also take any object with `get_token`, the `TokenCredential` shape `azure-identity` implements.
SMTP takes one inside `OAuth`, with an explicit `scope=`.
Epistole pre-checks only what a vendor documents: Gmail's 35 MiB request and 500 recipients, Graph's 150 MB attachment and 500 recipients.
SMTP gets none, because `smtplib` already negotiates `SIZE` with the server.
Everywhere else, Epistole maps the service's reply onto the same error a pre-check would have raised.

The choice depends on four things.

**Check the body size.**
Graph caps the entire write request at 4 MB, a figure Microsoft publishes without units.
Graph has no chunked path for a message body.
So a large embedded HTML report cannot be sent through Graph at all.
SMTP and Gmail measure against the whole message, so a body of several MB is routine on both.
If you send through Graph, attach the report as a file and keep the body small.

**Check whether your tenant allows SMTP AUTH.**
On Exchange Online, security defaults and any policy that blocks basic authentication switch SMTP client submission off.
The trend is toward switching it off.
Graph works under all of these settings.
The per-mailbox SMTP AUTH setting overrides the organization setting, so one enabled mailbox is the documented workaround.

**Weigh fidelity against features.**
SMTP and Gmail take the complete RFC 5322 message Epistole builds, so the recipient receives exactly what you send.
Graph takes a flat JSON array, and Exchange serializes the MIME later.
So Epistole can guarantee that your `cid:` references resolve, but not the MIME structure around them.
In exchange, Graph is the only backend that returns how long to wait when it throttles you.

**Weigh the access each permission grants.**
For a plain send the three are comparable: an Exchange Online SMTP OAuth grant with no claim added, the `gmail.send` scope, `Mail.Send`.
SMTP through Gmail is the exception.
XOAUTH2 there requires `https://mail.google.com/`, which grants full mailbox access.
So the Gmail backend requests less access than SMTP does.
Once a serialized Graph message exceeds 4 MB, Epistole takes the draft path.
That path needs `Mail.ReadWrite`, which grants reading every message in scope.
If you send through Graph, keep the whole message under 4 MB.
A security reviewer will prefer the narrower grant.
The 3 MB figure you may have seen is a second, internal threshold.
Inside the draft path, Epistole uses it to choose between one call and an upload session for an attachment.
It changes no permission.

`ConsoleBackend` and `MemoryBackend` are backends like any other.
Swapping one in changes the constructor and nothing else.
`MemoryBackend` records what it accepted as `backend.submissions`, so a test reads `submissions[0].message.to_`.
`ConsoleBackend` prints a readable rendering rather than the raw bytes any one backend sends.

These limits were quoted on 2026-09-08, and they change over time.
Re-check one before relying on it.
The sources are [Graph request limits](https://learn.microsoft.com/en-us/graph/use-the-api), [Graph large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments), [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits), [Gmail sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace), [Exchange rebuilds MIME](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail), [SMTP `SIZE`, RFC 1870](https://datatracker.ietf.org/doc/html/rfc1870), and [SMTP AUTH on Exchange Online](https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/authenticated-client-smtp-submission).
Fuller working is in `docs/research/send-boundary-semantics.md` and `docs/research/attachment-and-inline-rules.md`.

## Credit

Epistole is inspired by [blastula](https://github.com/rstudio/blastula), an R package for composing and sending email.
It is not a port.
Its API does not copy blastula's.

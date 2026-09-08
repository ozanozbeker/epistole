# Prototype: target usage code for all three backends

Prototype for [issue #8](https://github.com/ozanozbeker/herma/issues/8).
Throwaway.
None of this runs, none of it is a commitment, and no internal design is settled here.

## The question

What does the code a user writes actually look like, for SMTP, Gmail, and Graph side by side?

Deciding how a backend plugs into an email in the abstract is guesswork.
Reacting to three concrete call sites is not.
So the target usage comes first and the internals answer to it.

## Verdict

Decided 2026-09-08, after reading the call sites.
The spellings below are left exactly as they were written, including the parts this verdict overrules, because a prototype is only useful later if it still shows the alternatives.

**All three backends ship in V1, matching [#2](https://github.com/ozanozbeker/herma/issues/2).**

A protocol designed against one backend is not a protocol, it is that backend's shape with an interface bolted on.
That argument is why all three have to be specified, and shipping is what proves the specification was right.
The scene this whole file is built around, the same message sent through a second backend with the body-building code untouched, is only a demonstration if the second backend exists.
Portability that is specified but not shipped is a claim.

`ConsoleBackend` and `MemoryBackend` ship too, as the test surface the map already calls for.

**herma never composes HTML.
The caller supplies it, finished.**
The happy path is `Message(html=Path("report.html").read_text(encoding="utf-8"))` and there is no wrapper around it.
No `from_html_file`, because that would make herma own an encoding choice and a file-reading failure mode for no gain over one obvious line.
Where the HTML came from is not herma's business: Quarto, a hand-written file, or a model working from a guide are all the same string by the time it arrives.

That guide is now a deliverable rather than an idea.
If callers author HTML for email, and models author it on their behalf, the constraints in the recipient table below have to be written down somewhere a person or a model can read before writing rather than after sending.

**The credential is an object with a `get_token` method, not an `msal` client.**
Structural typing against the shape `azure.core.credentials.TokenCredential` already defines, so anything satisfying it works and herma depends on none of it.
The payoff is managed identity: a job running on Azure presents no secret at all, which removes the 24-month secret expiry that would otherwise be the most likely cause of a silent Monday failure.
`msal` applications do not satisfy that shape, since they expose `acquire_token_for_client` instead, so herma ships a thin adapter for them and keeps `msal` as the documented lightweight option.

Sequencing is a separate question from scope, and only one finding in this file carries a date.
An Exchange Online sender loses its password credential at the end of December 2026, and the fix is an SMTP credential change rather than a backend change.
So SMTP OAuth is the first thing to build inside V1, without narrowing what V1 contains.

**Spelling B, copy on write.**
Polars is the stated influence and it maps cleanly.
Polars never mutates a frame in place, and every method hands back a new one, which is the same trade herma is making: one shallow copy per step against a whole class of aliasing bug that nothing warns you about.

**`.to()`, `.cc()`, `.bcc()`, and `.subject()` replace.
`.attach()` appends.**
Polars draws the same line, since `select` replaces the column set and `with_columns` adds to it, and the English does the rest: `attach` is additive and `to` is a field.
Replacing makes the connection-reuse loop correct, and varargs cover the list case through `.to(*subscribers)`.
`.to()` with no arguments clears the field, which falls out of replace semantics rather than needing its own rule.

**`message.send(over=backend)`, and the same call takes a live connection.**

**The message has no `from_` at all.**
Not a dummy value the backend overwrites, which would make `Message` a document that lies about itself between build and send.
Absent.
Sender identity is transport identity on every backend, and each backend already carries it: `SmtpBackend(username=...)`, `GmailBackend(user_id=...)`, `GraphBackend(mailbox=...)`.
Unifying those three into one named field on the backend removes the worst finding in this file, which was that `from_` reads identically on the message and behaves differently on each backend.
With no `from_` on the message, nothing misleads.

`reply_to` stays on the message, and it is the honest answer to most of what people reach for `from_` to do.
Sending as `reports@example.com` while replies land on `ana@example.com` needs no grant on any backend.

**No per-send sender override either.**
One backend per sending identity, so the Send As grant is visible where the backend is constructed rather than at a call site that will `403` on Graph and quietly succeed on SMTP.
Graph application permissions can send as any mailbox in a tenant, which means one `GraphBackend` per mailbox.
Backends are cheap and several can share one `msal` application, so that costs an object, not a round trip.

**The SMTP backend carries password and OAuth as equals.**
Not a transition where one is legacy, because outside Exchange Online a password is not legacy at all.
Self-hosted Postfix, most hosting providers, and every internal relay authenticate with a password and always will, so herma marking it deprecated would be wrong everywhere except one tenant type.
Deprecation belongs to Exchange Online, not to the mechanism, and the documentation should say which.

That makes three SMTP credential shapes rather than two, because anonymous submission is real: internal relays and Microsoft direct send take no credential at all.
Blastula already names this with `creds_anonymous()`.

**Spelling C is not rejected.**
Its `Body` type names a split the pre-rendered workflow already has, and `harvest_data_uris` returning both halves is still the clearest spelling of the rewrite.
Whether `Body` survives as a separate type or collapses into `Message` is open.

## How to read this

One scene is replayed three times.
The scene is fixed so the spellings can be compared line for line:

- A weekly report to two people, one cc, one bcc.
- An HTML body that already exists, rendered by Quarto with its tables and charts already embedded, plus a PDF attachment.
- The same message sent through a second backend with the body-building code untouched.
- A one-off send, then a loop over many recipients that reuses one connection.

Each spelling answers three questions differently, and those are the axes the next tickets decide:

| | Message shape | Where the backend meets the message | Where credentials enter |
| --- | --- | --- | --- |
| A | Mutable object, mutating methods | `backend.send(email)` | Backend constructor |
| B | Chaining builder, `.to(...).attach(...)` | `message.send(over=backend)` | Backend constructor |
| C | Body value, addressing at the send | `send(body, to=..., over=backend)` | The send call |

A is Django and Anymail.
C is blastula.
B has no Python precedent at all, which is a finding rather than a disqualification, and the section works out why.

Two things are held constant on purpose, because varying everything at once teaches nothing:

- What `send` returns.
  Every spelling returns the same receipt.
- Backend package layout.
  `herma.smtp`, `herma.gmail`, `herma.graph`, matching the optional extras.

## Constraints these spellings have to respect

Carried in from the closed research tickets.
A spelling that breaks one of these is already wrong.

Each one is marked with the backend that forces it, because most of them are one backend's limitation becoming everyone's interface.

- **Graph.**
  An attachment is a flat description, not a MIME part, because Graph builds MIME inside Exchange from a flat JSON array and cannot express nesting ([#4](https://github.com/ozanozbeker/herma/issues/4)).
  A MIME-tree-shaped API is unimplementable on Graph, so the flat shape is not a simplification, it is the only shape that works everywhere.
- **Graph and SMTP.**
  `send` cannot return a provider message id, since Graph returns `202` with an empty body and `smtplib` discards the queue id ([#3](https://github.com/ozanozbeker/herma/issues/3)).
  An optional id present only on Gmail is close to useless to a caller writing backend-agnostic code.
- **SMTP.**
  Only SMTP can refuse some recipients and accept others, so the receipt needs a slot for that which is empty on the two APIs.
  This is the one constraint where SMTP is the awkward backend rather than Graph.
- **Graph.**
  `retry_after` is Graph-only, so it is `float | None`.
- **SMTP and Gmail against Graph.**
  Content-ID is stored bare and gets angle brackets only when a MIME header is written.
  MIME wants the brackets and Graph wants the bare value, so the normalization happens at the boundary or nowhere.
- **Gmail and Graph.**
  Credentials come from the vendor auth library and the vendor client stays out of the tree, `google-auth` for Gmail and `msal` for Graph ([#5](https://github.com/ozanozbeker/herma/issues/5)).
  SMTP meets the same shape, because OAuth on Exchange Online takes an `msal` application too.
- **All three.**
  Plain text is derived unless the caller supplies it, and the seam is a callable ([#7](https://github.com/ozanozbeker/herma/issues/7)).

## Constructing the backends

Identical in all three spellings except C, which moves credentials to the send call.
Shown once here.

```python
import os
from pathlib import Path

import msal
from google.oauth2.credentials import Credentials

from herma.gmail import GmailBackend
from herma.graph import GraphBackend
from herma.smtp import SmtpBackend

smtp = SmtpBackend(
    host="smtp.fastmail.com",
    port=465,
    ssl=True,
    username="reports@example.com",
    password=os.environ["SMTP_PASSWORD"],
)

# The same backend against Exchange Online, where a password stops being an
# option for existing tenants at the end of December 2026.
smtp_oauth = SmtpBackend(
    host="smtp.office365.com",
    port=587,
    starttls=True,
    username="reports@example.com",
    credentials=msal.ConfidentialClientApplication(
        client_id=os.environ["AZURE_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
        client_credential=os.environ["AZURE_CLIENT_SECRET"],
    ),
    scopes=["https://outlook.office365.com/.default"],
)

gmail = GmailBackend(
    credentials=Credentials.from_authorized_user_file(
        "token.json",
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    ),
    user_id="me",
)

graph = GraphBackend(
    credentials=msal.ConfidentialClientApplication(
        client_id=os.environ["AZURE_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
        client_credential=os.environ["AZURE_CLIENT_SECRET"],
    ),
    mailbox="reports@example.com",
)
```

Four notes this raises for [#16](https://github.com/ozanozbeker/herma/issues/16).

The SMTP backend needs an OAuth path from day one, and the first sketch above did not have one.
A password is the only SMTP credential in most prior art, and on Exchange Online it is the credential with a deprecation date.
`smtplib` already reaches the replacement through `SMTP.auth("XOAUTH2", authobject)`, so the work is a token source and an auth string, not a new transport.
That makes `credentials=` cover four shapes rather than three, and it is now the strongest argument for a tagged credential value instead of loose arguments.

`credentials=` is one word for three unrelated shapes.
SMTP has no credential object at all, so its secret arrives as loose arguments while the other two arrive as objects.
Blastula's answer was a tagged `creds()` value with one constructor per source, which would make all three read alike.
That is sketched at the end.

An `msal` application is a client, not a credential.
`docs/research/sdk-versus-rest.md` says to take a credential object, and Microsoft's credential interface is `azure.core.credentials.TokenCredential`.
Accepting that shape structurally, without depending on `azure-core`, is the honest version.
Accepting the `msal` app is the version that works today with the dependency already chosen.

`user_id` and `mailbox` are the same concept spelled two ways because each vendor spells it that way.
Following the vendor is defensible.
Following ourselves is also defensible.
Pick one and apply it everywhere.

## Spelling A: mutable message, Django shaped

```python
from herma import Email

email = Email(
    subject="Weekly numbers, week 36",
    to=["ana@example.com", "bo@example.com"],
    cc=["ops@example.com"],
    bcc=["archive@example.com"],
    from_="reports@example.com",
    html=Path("report.html").read_text(encoding="utf-8"),
)
email.attach(
    Path("report.pdf").read_bytes(),
    filename="report.pdf",
    content_type="application/pdf",
)
```

Note what is missing: any call that builds an inline image.
The HTML arrived finished from Quarto, so the caller never needs a content id for the body, and the ordering problem that mutable builders normally have does not appear.

That problem is worth writing down anyway, because it returns the moment herma composes any part of the body.
`attach_inline` has to hand back the content id, since the caller needs it for the `src` attribute, and that is why Anymail's `attach_inline_image` returns an id rather than the message.
So `html` cannot be complete at construction time and has to arrive by assignment afterwards.
Under the pre-rendered workflow that never happens.
See the Quarto section below, where a different version of the same problem does.

Sending, and what comes back:

```python
receipt = smtp.send(email)

receipt.accepted  # True. Means accepted for submission, never delivered.
receipt.message_id  # The Message-ID herma wrote. Unverified on Gmail and Graph.
receipt.refused  # {"bo@example.com": (550, b"No such user")}. Always {} on the APIs.
receipt.backend  # "smtp"
receipt.retry_after  # None. Graph is the only backend that ever fills this.
```

The second backend, with the body-building code untouched:

```python
graph.send(email)
gmail.send(email)
```

That is the whole premise and it reads well.
One caveat the type system will not catch, and it is what killed `from_` on the message.
SMTP honours it subject to server policy, while Gmail and Graph ignore or reject it unless an administrator granted Send As.
The same three lines mean three things.
The verdict removes the field rather than documenting the trap.

One-off, then the loop that reuses a connection:

```python
smtp.send(email)

with SmtpBackend(
    host=..., port=465, ssl=True, username=..., password=...
) as connection:
    for subscriber in subscribers:
        connection.send(
            Email(
                subject="Weekly numbers, week 36",
                to=[subscriber.email],
                from_="reports@example.com",
                html=shared_html,
            )
        )
```

The attachments are re-encoded once per subscriber here, because each `Email` is built fresh.
Hoisting the attachment list out and passing it in works, and it means two mutable messages share one attachment list.
That is the mutation foot-gun `docs/research/prior-art.md` warns about, arriving from an unexpected direction.

## Spelling B: chaining builder

The syntax, first:

```python
from herma import Message

message = (
    Message(html=Path("report.html").read_text(encoding="utf-8"))
    .subject("Weekly numbers, week 36")
    .to("ana@example.com", "bo@example.com")
    .cc("ops@example.com")
    .bcc("archive@example.com")
    .attach(Path("report.pdf"))
)
```

It reads well, and varargs on `.to()` close a bug the keyword-list spellings have to guard by hand.
Django raises `TypeError('"to" argument must be a list or tuple')` because `to="ana@example.com"` would otherwise iterate into seventeen single-character recipients.
`.to("ana@example.com")` cannot do that, since a bare string is one argument and not one iterable.
That is a real win and it belongs to this spelling alone.

Now the part that is invisible at the call site, and the reason the verdict reads the way it does.

`docs/research/prior-art.md` found no Python email library that chains, and the two that come closest mutate while doing it.
Blastula chains safely only because R copies on modify, so every step is a new value for free.
Python hands you nothing, so the semantics had to be chosen, and the call site above is identical either way.

The chosen shape is on the right.
The one on the left is kept only because it is the counterexample that forced the choice, not because it is still on the table.

```python
# Rejected. Each method sets a field and returns self.
def to(self, *addresses: str) -> Self:
    self._to.extend(addresses)
    return self


# Chosen. Each method returns a new Message, and addresses replace rather than append.
def to(self, *addresses: str) -> Self:
    return replace(self, _to=addresses)
```

Here is the case that separates them.

```python
base = Message(html=html).subject("Weekly numbers, week 36")

for_ana = base.to("ana@example.com")
for_bo = base.to("bo@example.com")
```

Under B1, `base`, `for_ana`, and `for_bo` are one object addressed to both people.
Both sends go to both recipients.
Nothing raises, nothing warns, and the code reads exactly like the version that works.

Under B2 they are three objects and the code means what it looks like.

Sending, with the chain running to the end:

```python
receipt = (
    Message(html=Path("report.html").read_text(encoding="utf-8"))
    .subject("Weekly numbers, week 36")
    .to("ana@example.com", "bo@example.com")
    .attach(Path("report.pdf"))
    .send(over=smtp)
)
```

The second backend, with the body-building code untouched:

```python
message.send(over=graph)
message.send(over=gmail)
```

`.send()` terminating the chain is the one place the chain has to stop being a `Message`, because it returns a receipt.
That is fine and it is worth stating: `.send()` is not chainable and never will be.

One-off, then the loop that reuses a connection:

```python
report = (
    Message(html=Path("report.html").read_text(encoding="utf-8"))
    .subject("Weekly numbers, week 36")
    .attach(Path("report.pdf"))
)

with smtp.connect() as connection:
    for subscriber in subscribers:
        report.to(subscriber.email).send(over=connection)
```

This loop is the whole argument.

Under B2 it is correct, and it costs one shallow copy per subscriber while the encoded PDF is shared across all of them.

Under B1 the recipient list accumulates.
Subscriber 1 gets a message addressed to one person, subscriber 2 gets one addressed to two, and subscriber 200 gets a message listing all 200 addresses in its `To` header.
Every earlier subscriber also received every address ahead of them.
It is a data leak, it is silent, and the loop above is the obvious way to write the code.

So B2, or no chaining.
A `return self` builder that hands out an alias is not a smaller version of B2, it is a different and worse thing wearing the same syntax.

This spelling raised three naming questions that the others do not.
Two are answered in the verdict and are recorded here as answered, because a reader arriving at this section should not think they are still live.

**Answered: `.to()` and its sisters replace.**
`.attach()` obviously appends and `.subject()` obviously replaces, so `.to("ana@example.com").to("bo@example.com")` was the genuinely ambiguous one.
Replace wins because it is what makes the connection-reuse loop correct, and because polars draws the same line between `select`, which replaces the column set, and `with_columns`, which adds to it.
Varargs cover the list case through `.to(*subscribers)`, so nothing is lost by dropping append.

**Answered: `from_` is not on the message.**
`.from_("reports@example.com")` reads like a typo and `.sender()` collides with the From address the way redmail's `EmailSender.sender` does.
That the field has no good spelling here turned out to be the useful signal: it has no good spelling because it does not belong on the message.
The backend owns it.

**Still open: the method eats the attribute.**
If `.to()` is a method, `message.to` is that method and not the recipients, so reading a field back needs a second name.
Django already owns a good one for the union, `recipients()`, and [#14](https://github.com/ozanozbeker/herma/issues/14) has to settle the rest.
This is the only naming question in this section that the verdict does not close.

## Spelling C: body once, audience at the send

```python
from herma import Attachment, Body, creds, send
from herma.smtp import smtp_connection

body = Body(
    html=Path("report.html").read_text(encoding="utf-8"),
    attachments=(Attachment.file(Path("report.pdf")),),
)
```

A `Body` is content and nothing else.
It has no recipients, no subject, and no sender, so it cannot be sent by accident and it is obviously reusable.

Under the pre-rendered workflow this is the spelling that matches the shape of the work.
Quarto produces one artifact and the audience is a separate concern that arrives later, often from a database query.
`Body` names that split instead of leaving it implicit.

Sending, with the audience supplied at the call:

```python
receipt = send(
    body,
    over=smtp,
    subject="Weekly numbers, week 36",
    to=["ana@example.com", "bo@example.com"],
    cc=["ops@example.com"],
    bcc=["archive@example.com"],
    from_="reports@example.com",
)
```

The second backend is one word:

```python
send(body, over=graph, subject="Weekly numbers, week 36", to=["ana@example.com"])
send(body, over=gmail, subject="Weekly numbers, week 36", to=["ana@example.com"])
```

Credentials at the send call, blastula's arrangement, with one tagged value covering all three backends:

```python
send(
    body,
    over=creds.smtp(host="smtp.fastmail.com", port=465, env_password="SMTP_PASSWORD"),
    subject=...,
    to=[...],
)
send(body, over=creds.gmail(token_file="token.json"), subject=..., to=[...])
send(body, over=creds.graph(mailbox="reports@example.com"), subject=..., to=[...])
```

One-off, then the loop:

```python
send(body, over=smtp, subject="Weekly numbers, week 36", to=["ana@example.com"])

with smtp_connection(smtp) as connection:
    for subscriber in subscribers:
        send(
            body,
            over=connection,
            subject="Weekly numbers, week 36",
            to=[subscriber.email],
        )
```

`over=` accepting either a backend or a live connection is the trick that makes the one-off and the loop the same line.
It also means one parameter has two types, and a reader cannot tell from the signature whether a connection is opened.

What this spelling buys is real.
One body, many audiences, no recomposition, and the attachments encode once.
What it costs is that `subject` sits at the send call, which nobody expects, and the signature is long enough that every argument has to be keyword-only.
Blastula gets away with it in R.
`docs/research/prior-art.md` found no Python library that does this, which is evidence, though not proof that it is wrong.

## What any HTML body has to satisfy

The scene above reads `report.html` and hands it over untouched.
Quarto was the worked example, and the decision since taken is that herma does not have to accommodate it.
Keep reading anyway: only one of the four problems below is Quarto's, and the other three constrain any HTML body regardless of what produced it.

That matters because the alternative to Quarto is HTML written on the fly, by a person or by a model, and a model writing "self-contained HTML" reaches for exactly the constructs listed here.
An HTML authoring guide is the natural home for these limits, and it is the shortest useful thing herma can ship next.

Sources were gathered on 2026-09-08 and belong in `docs/research/` rather than a prototype.
They are summarized here because they change what the spellings have to do.

| Problem | Quarto's fault | Where it bites | Fixable by herma |
| --- | --- | --- | --- |
| `data:` URI images do not render in Gmail | no | recipient | yes, by rewriting them to `cid:` |
| `<style>` in `<head>` dies in Outlook's Word engine | no | recipient | no, this needs CSS inlining |
| JavaScript charts render nowhere | yes | recipient | no |
| Graph rejects a body over 4 MB with `413` | no | backend | only by moving bytes into attachments |

That third column is the one worth internalizing, because Gmail and Outlook appear twice in this file wearing different hats.
As **backends** they are things herma talks to, and a caller who picks a different backend never meets their limits.
As **recipients** they are where the mail lands, and no choice of backend avoids them.

Three of these four are recipient-side.
They apply to every message herma sends over every backend it will ever have, including SMTP, and no amount of backend work touches them.
Only the `413` belongs to a backend, and it is the only one a caller can dodge by choosing differently.

That is why the `data:` to `cid:` rewrite is core rather than a Graph concern, which is the opposite of where this section originally put it.

**The images are `data:` URIs.**
`embed-resources: true` "will produce a standalone HTML file with no external dependencies, using `data:` URIs to incorporate the contents of linked scripts, style sheets, images, and videos" ([Quarto HTML Basics](https://quarto.org/docs/output-formats/html-basics.html)).
Quarto hides the flag from its main pandoc call and re-runs pandoc over the finished HTML, so Pandoc's `SelfContained.hs` does the embedding ([`src/core/pandoc/self-contained.ts`](https://github.com/quarto-dev/quarto-cli/blob/main/src/core/pandoc/self-contained.ts)).
Both engines write plots to disk as ordinary PNGs first, so every figure arrives as `data:image/png;base64,`.

**Gmail renders none of them.**
No vendor documents this.
Google's [CSS Support](https://developers.google.com/workspace/gmail/design/css) page never mentions images or URI schemes, and Microsoft's only HTML support reference is an archived 2007 Word rendering article.
The best available source is [Can I Email](https://www.caniemail.com/features/image-base64/), which is community-maintained and must be labelled as such.
Its data has Gmail at "no" on desktop webmail, iOS, Android, and mobile webmail, alongside "yes" for Apple Mail, Outlook.com, Outlook mobile, Thunderbird, and Fastmail.
Gmail being uniformly "no" is the finding that matters, and it is a community test rather than a Google statement.

**Graph rejects the message outright, and this one is fatal.**
"Write requests in the Microsoft Graph API have a size limit of 4 MB.
Requests exceeding the size limit fail with the status code HTTP 413" ([Use the Microsoft Graph API](https://learn.microsoft.com/en-us/graph/use-the-api)), and `message.body.content` is inside that request.
A locally rendered report with one matplotlib figure and one plotly figure came to 7,741,183 bytes of HTML and 7,909,986 bytes of `sendMail` JSON.
The same message is fine on SMTP and Gmail, which advertise 35,882,577 bytes and 36,700,160 bytes respectively.

This one was checked twice, because `docs/research/send-boundary-semantics.md` currently records the opposite and is wrong on three lines.
The 4 MB is the platform-wide write-request cap, not an S/MIME footnote, and it covers `POST /me/sendMail`, `POST /me/messages`, and `PATCH /me/messages/{id}` alike.
The S/MIME note on [create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages) restates the same number for one path rather than being its source.

There is no path past it.
`createUploadSession` exists only for drive items, Outlook attachments, and to-do attachments ([uploadSession](https://learn.microsoft.com/en-us/graph/api/resources/uploadsession)), so there is no chunked body.
`PATCH` on a draft replaces `body` rather than appending to it, and is itself a 4 MB write request, so a body cannot be assembled across several calls.
The MIME path is tighter still rather than looser, because a file is base64-encoded inside the MIME part and the whole MIME message is base64-encoded again for the request body, which fits roughly 2.1 MB of original bytes inside a 4 MB request.
A Microsoft employee asked for a way past this in 2022 and the thread is still unanswered.

So the body is capped at 4 MB, and bytes that need to travel have to become attachments, where an upload session exists and carries up to 150 MB per file.

**The CSS does not survive, and no rewrite fixes it.**
Google's own worked example puts `<style>` in `<head>`, so Gmail supports the construct.
The measured report emits 481,350 characters across three `<style>` blocks plus 650,318 characters of percent-encoded CSS still sitting in `<link href="data:text/css,...">` tags, because Pandoc leaves a stylesheet as a `<link>` when it contains `</`.
Neither Quarto nor Pandoc inlines CSS onto elements the way a premailer would.
Outlook's Word engine will not render it at any size.
This is the [CSS inlining](https://github.com/ozanozbeker/herma/issues/2) fog in the map, and it is bigger than the map currently assumes.

**Plotly figures are JavaScript.**
The plotly output is a `<div class="plotly-graph-div">` driven by `Plotly.newPlot`, not an image.
No email client runs it, and no rewrite herma performs can change that.
This is the one problem that leaves with Quarto, and it comes straight back the moment anyone asks a model for an interactive chart.
Charts in email are static images or they are nothing.

### The one part herma can fix

Walk the HTML, pull each `data:` image out, and rewrite it as a `cid:` reference backed by an inline attachment.
That is blastula's `cid_images()` ([`R/utils-html_manipulation.R:346`](https://github.com/rstudio/blastula/blob/master/R/utils-html_manipulation.R)), called by `render_email()` immediately after rendering, which is exactly this use case.
Quarto solves the same problem earlier in its own pipeline, walking pandoc `Image` nodes before the embed step ([`email.lua`](https://github.com/quarto-dev/quarto-cli/blob/main/src/resources/filters/quarto-post/email.lua)).
No Python library was found that does it.
`python-emails` explicitly declines: `if uri[:5].lower() == 'data:': return uri` ([`emails/transformer.py:245`](https://github.com/lavr/python-emails/blob/master/emails/transformer.py)).

The rewrite is not a bandwidth optimization, and the folklore here is wrong.
Python encodes a base64-heavy HTML body as quoted-printable, not base64, and base64 characters are all quoted-printable-safe.
Measured on a 1 MiB image, the `data:` form costs 1,434,975 bytes on the wire against 1,417,302 for the `cid:` form, a difference of 1.25 percent rather than the 33 percent usually claimed.
So the rewrite buys two things only: images that render in Gmail, and a Graph message that is under 4 MB because the bytes moved into attachments where the upload session exists.

Steal blastula's content id format and its reason.
It writes `img1.png`, with no `@domain` part, and the source says why:

```text
# According to the spec there should be an @domain on this, but it makes
# attachment UI show up for Outlook.com (e.g. AT00001.bin)
```

RFC 2045 asks for a `msg-id`, so a spec-compliant content id is the thing that breaks Outlook.com.
That is an interoperability finding no RFC will give you, and it contradicts the world-uniqueness advice in spelling B above.

Three bugs in blastula's version not to copy: its regex `^data:image/(\w+);(base64,)(.+)` misses `image/svg+xml` because `+` is not `\w`, it only touches `<img src>` and so ignores `url(data:...)` inside CSS, and it runs its regex with `perl = FALSE` to dodge a stack overflow on large input.
The measured report contains `url(data:image/svg+xml,...)` in embedded CSS, so bug one and bug two both fire on it.

### Where the rewrite goes, per spelling

```python
# A. Mutable, so it is a method that rewrites html and appends attachments.
email = Email(
    subject=..., to=[...], html=Path("report.html").read_text(encoding="utf-8")
)
email.inline_data_uris()

# B. Chaining, so it is a constructor that harvests on the way in.
message = Message.from_html_file(Path("report.html")).subject(...).to(...)

# C. Body, so it is a function over HTML that returns both halves.
html, images = harvest_data_uris(Path("report.html").read_text(encoding="utf-8"))
body = Body(html=html, attachments=images)
```

C is the honest one, because the rewrite genuinely produces two values and only C says so.
A and B both hide the attachments the rewrite created, which matters as soon as the caller wants to know why their message grew by 7 MB.

The harder question is whether it runs by default.

Making it automatic means `Message(html=...)` silently rewrites the caller's HTML, and `docs/research/prior-art.md` is firm that herma should not guess what a string means.
Making it opt-in means the default sends broken images to every Gmail recipient and a guaranteed `413` to every Graph recipient.
Neither default is safe, which usually means the framing is wrong.

The defensible third answer: always harvest, and argue it is not guessing.
A `data:` image in an email body is not an ambiguous construct with two reasonable readings.
It is a construct that fails on the largest mail provider in the world and exceeds the hard request limit on another.
Rewriting it is closer to choosing a transfer encoding than to guessing whether a string is a filename. [#11](https://github.com/ozanozbeker/herma/issues/11) should take that argument seriously before reaching for a flag.

## The axis none of the spellings settle

Attachment size on Graph, which leaks through whatever surface we pick.

```python
Attachment.file(Path("400mb-video.mp4"))
```

Under 3 MB, Graph sends it inline in `sendMail` with `Mail.Send`.
Over 3 MB, Graph needs a draft, an upload session, ranged `PUT`s, and the broader `Mail.ReadWrite` scope.
So the same one line either needs one OAuth scope or two, and herma cannot hide which.
No spelling above makes this visible, and pretending it is invisible is how a user gets a `403` in production.

## Orthogonal alternatives worth keeping

These vary independently of the three spellings, so mixing them in above would have confused the comparison.

**The `data:` rewrite now has nowhere obvious to live.**
The earlier sketch put the harvest in `Message.from_html_file`, and that constructor is gone.
What remains is a genuine tension the verdict creates rather than resolves.
The caller supplies finished HTML and expects it sent as written, and a `data:` image in that HTML does not render in Gmail.
Doing the rewrite silently means herma edits HTML it just promised to pass through.
Not doing it means the default is broken images for the largest mail provider there is. [#11](https://github.com/ozanozbeker/herma/issues/11) inherits this, and the argument in the recipient section below is the one to weigh: a `data:` image is not an ambiguous construct with two reasonable readings, it is a construct that fails.

**Credentials as one tagged value.**
Where a secret lives is orthogonal to which backend uses it, so it should not be five backend arguments.
Blastula's `creds()`, `creds_key()`, `creds_file()`, `creds_envvar()`, `creds_anonymous()` is the model.
It also gives SMTP the object shape the other two already have.

The count settles the argument.
There are five credential shapes across three backends: SMTP anonymous, SMTP password, SMTP OAuth, Google credentials, and an msal application.
Five loose argument sets is not a surface anyone remembers, and two of the five arrived after the first draft of this file rather than being visible at the start.

**A `provider` preset.**
`creds.smtp(provider="fastmail", username=..., env_password=...)` fills host, port, and TLS from a table.
The preset is data, not a mutable module-level sender.

**A caller-supplied plain-text renderer.**

```python
import inscriptis

message = Message(..., text_renderer=inscriptis.get_text)
message = Message(..., text="Week 36. Full detail in the attached PDF.")
```

Supplied text wins outright and derivation never runs.
Herma depends on neither `inscriptis` nor `html2text`, so the GPL question stays with the caller who opted in.

**The escape hatch.**

```python
graph.send(email, backend_extra={"saveToSentItems": False})
```

Anymail calls this `esp_extra`.
Naming the concept rather than a vendor is the only change worth making. [#17](https://github.com/ozanozbeker/herma/issues/17) decides what happens when a backend is handed a key it does not know.

## Which backend to use

Extracted to `docs/choosing-a-backend.md`, expanded to cover Gmail, and given its sources.
Not repeated here.

It came out of this prototype rather than out of a ticket, which is worth noting: writing three construction sites side by side is what made the differences between the backends concrete enough to compare, and none of the closed research tickets asked the question that way.

## What this prototype settled, and what it did not

Settled, in the sense that writing the call sites made it obvious:

- A message that holds content and addressing, with the backend holding transport only, survives the second backend in all three spellings.
  The premise holds.
- Chaining has to return a new instance.
  The connection-reuse loop under `return self` accumulates recipients and leaks every earlier subscriber's address to every later one, silently, in the most natural way to write that loop.
  `return self` is not a cheaper version of copy on write, it is a different and worse thing wearing the same syntax.
- Varargs on `.to()` remove a class of bug that the keyword-list spellings have to guard by hand.
- `from_` reads identically and behaves differently on each backend, in all three spellings.
  No message shape fixes it, so the field leaves the message and the backend owns it.
- Harvesting `data:` URIs into `cid:` attachments is not optional for the Quarto workflow.
  Without it Gmail shows broken images and Graph returns `413` on a report of realistic size.
  No Python library does this today.
- The inline content id should have no `@domain` part, against RFC 2045, because a spec-compliant one makes Outlook.com display a spurious attachment.
  This contradicts the world-uniqueness note in spelling B, and blastula's source is the only place it is written down.

Not settled, and deliberately left open for the tickets that follow:

- Whether `subject` belongs on the message or at the send call.
- Whether `.to()` appends or replaces, given `.attach()` obviously appends and `.subject()` obviously replaces.
- What a chained field is called when the method has eaten the attribute name.
- Whether the `data:` rewrite runs always, or behind a flag, given neither default is safe.
- Whether one `credentials=` word covering three shapes is a feature or a lie.

## What this prototype found that needs its own ticket

Four of these are outside the scope of issue #8 and none of them has a home yet.
They are ordered by when they bind, not by size.

**SMTP OAuth, and it is the only item here with a deadline.**
Every prior-art library authenticates SMTP with a password, and on Exchange Online that credential is disabled by default for existing tenants at the end of December 2026 ([Exchange Team blog, 2026-01-27](https://techcommunity.microsoft.com/blog/exchange/updated-exchange-online-smtp-auth-basic-authentication-deprecation-timeline/4489835)).
`smtplib` already reaches the replacement through `SMTP.auth("XOAUTH2", authobject)`, so the work is a token source and an auth string rather than a new transport.
Nothing else in this file has a date, which makes this the first thing to build even though it is not the largest.

**CSS in an HTML body.**
The map lists CSS inlining as fog and leans on `css-inline` as the likely answer.
The measured numbers make it larger than that: 481,350 characters of `<style>` plus 650,318 characters still inside `data:text/css` `<link>` tags, none of it inlined by Quarto or Pandoc, against an Outlook engine that will not render it and a community-reported 16 KB Gmail cap.
Recipient-side, so no backend choice avoids it.

**Graph needs three send strategies, chosen by size.**
The largest implementation finding in the file.
It is a Graph-only branch, but the protocol has to leave room for it before any backend is written.

| Total request after encoding | Largest attachment | Strategy | Permissions |
| --- | --- | --- | --- |
| under 4 MB | any | `POST /me/sendMail` | `Mail.Send` |
| over 4 MB | each under 3 MB | draft, one `POST` per attachment, `POST /send` | `Mail.ReadWrite` and `Mail.Send` |
| over 4 MB | any 3 MB to 150 MB | draft, `createUploadSession`, ranged `PUT`, `POST /send` | `Mail.ReadWrite` and `Mail.Send` |

Two of the three widen the OAuth ask, so herma cannot promise `Mail.Send` alone without also capping size.
That ask is wider than it looks, and 3 MB is a privacy boundary rather than a size one.
`Mail.ReadWrite` is not a larger `Mail.Send`, it is a different permission on a different axis: "Allows the app to create, read, update, and delete email in all mailboxes without a signed-in user.
Doesn't include permission to send mail" ([Application RBAC](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac)).
So a single attachment crossing 3 MB takes an app from "can send" to "can send and can read every message in scope", and a security reviewer will notice.
Keeping attachments under 3 MB is worth designing for, and herma should make the size that triggers it visible rather than discovering it at send time.
The branch is not optional in either direction, because an upload session for a file under 3 MB fails with `ErrorAttachmentSizeShouldNotBeLessThanMinimumSize`.
The large path is an error on small files exactly as the small path is an error on large ones.

Three further limits bind before the API does.
The tenant message size limit defaults to 35 MB for sending and is configurable from 1 MB to 150 MB, so a 150 MB attachment is accepted by the upload session and then bounces in transport.
Graph throttles writes at 150 MB per five minutes per app and mailbox, which a burst of large reports will hit.
Delegated permissions cannot attach large files to a shared or delegated mailbox at all, returning `403` ([known issues](https://learn.microsoft.com/en-us/graph/known-issues)).

**Plotly and any JavaScript figure.**
Nothing renders it in mail.
This is documentation, not code, but it should be documentation herma writes rather than something a user discovers after sending.

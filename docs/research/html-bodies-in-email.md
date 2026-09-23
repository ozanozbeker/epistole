# HTML bodies in email

This file records the research for [issue #22](https://github.com/ozanozbeker/epistole/issues/22).
The substance was gathered on 2026-09-08 while specifying [#8](https://github.com/ozanozbeker/epistole/issues/8) and [#11](https://github.com/ozanozbeker/epistole/issues/11).
Before this file, it existed only in a prototype and in issue comments.
The file uses primary sources only.
Every factual claim below carries a URL.
Where a source says nothing or two sources disagree, the text records that rather than a guess.
Where a claim comes from a local run rather than a document, the text says so.
This file uses community-maintained sources only where no vendor documents the behaviour.
It labels them as such at every use.

Documents were read on 2026-09-08 and re-checked on 2026-09-09.
Local runs are dated where they appear.
See [Figures to recheck](#figures-to-recheck).

## What this means for Epistole's design

**Recipient-side and backend-side limits are different problems, and only one of them is a choice.**
Gmail and Outlook have two roles in this work.
As **backends**, they are mail services that Epistole submits to.
Their limits never apply to a caller who picks a different backend.
As **recipient-side services**, they receive the message.
A caller cannot avoid them by choosing a different backend.
Where a fix belongs depends on that distinction.

A realistic HTML body has four problems.
Only one is Quarto's.
Only one is backend-side.

| Problem | Quarto's fault | Where it applies | Fixable by Epistole |
| --- | --- | --- | --- |
| `data:` URI images do not render in Gmail | no | recipient | yes, by rewriting them to `cid:` |
| A `<head>` stylesheet is unevenly supported | no | recipient | no, and Epistole should leave it alone |
| JavaScript charts render nowhere | yes | recipient | no |
| Graph rejects a request over 4 MB with `413` | no | backend | only by moving bytes into attachments |

Three of the four are recipient-side.
They apply to every message Epistole sends over every backend it will ever have, SMTP included.
Only the `413` belongs to a backend.
It is the only one a caller can avoid by choosing a different backend.

So the `data:` to `cid:` rewrite is core, not a Graph concern.
It was originally scoped as a Graph workaround.
That was the wrong place for it.

**The rewrite is for rendering, not bandwidth.**
The folklore says moving base64 out of an HTML body saves a third of the message.
Measured, it saves about 1.2 percent.
Python encodes a base64-heavy HTML body as quoted-printable rather than base64.
Base64's own output characters are all quoted-printable-safe, so the body is not re-expanded.
Argue the rewrite on rendering and on Graph's 4 MB cap, never on size.

**A spec-compliant content id breaks Outlook.com.**
RFC 2045 specifies a `msg-id`, which has an `@domain` part.
But blastula ships `img1.png` with no domain on purpose, because the compliant form makes Outlook.com display a spurious attachment.
No RFC states this.
The finding also contradicts the world-uniqueness instinct.

**No vendor documents `data:` image support, so the main evidence here is community testing.**
Google's CSS reference never mentions images or URI schemes.
Microsoft's only HTML rendering reference is an archived article about Word 2007.
Apple documents nothing for received messages.
The source is Can I Email, which is community-maintained.
This file labels it as such everywhere it is used.

## Where a `data:` URI comes from

### Quarto's `embed-resources`

Quarto documents the flag plainly.
It says of `embed-resources: true`: "This will produce a standalone HTML file with no external dependencies, using `data:` URIs to incorporate the contents of linked scripts, style sheets, images, and videos" ([Quarto HTML Basics](https://quarto.org/docs/output-formats/html-basics.html)).

This is the natural setting for a report someone intends to email, because the alternative is a folder of sidecar files that no mail client will follow.
So the construct is present by default, not by mistake.

### Pandoc's `SelfContained.hs` does the actual embedding

Quarto does not implement the embedding itself.
It leaves the flag out of its main pandoc call and re-runs pandoc over the finished HTML ([`src/core/pandoc/self-contained.ts`](https://github.com/quarto-dev/quarto-cli/blob/main/src/core/pandoc/self-contained.ts)).

The work happens in [`src/Text/Pandoc/SelfContained.hs`](https://github.com/jgm/pandoc/blob/main/src/Text/Pandoc/SelfContained.hs), whose module header states its purpose: "Functions for converting an HTML file into one that can be viewed offline, by incorporating linked images, CSS, and scripts into the HTML using data URIs."
Pandoc's manual describes `--embed-resources` as "Produce a standalone HTML file with no external dependencies, using `data:` URIs to incorporate the contents of linked scripts, stylesheets, images, and videos", and `--self-contained` as a "Deprecated synonym for `--embed-resources --standalone`" ([Pandoc manual](https://pandoc.org/MANUAL.html)).

As read on 2026-09-09, the module does three things.
Only the first is attribute rewriting.

`isSourceAttribute` covers `src`, `data-src`, `href` on a `link`, `poster` and `data-background-image`.
Each becomes a `makeDataURI` value.
This step turns a figure into `data:image/png;base64,`.

The module replaces a fetched `text/css` `<link>` outright with an inline `<style>` block, rather than rewriting it in place.
[`css-in-an-html-body.md`](css-in-an-html-body.md) covers the conditions for that and the `</` guard that often stops it.
This file does not repeat them.

`cssURLs` and `handleCSSUrl` rewrite `url(...)` references inside CSS too.
They short-circuit on a URI that is already `data:`.
This detail matters most for the rewrite Epistole has to perform: **a `data:` URI can appear inside a stylesheet, not only in an `<img src>`**.
A measured Quarto report contains `url(data:image/svg+xml,...)` in its embedded CSS for exactly this reason.

The module never inlines CSS onto elements as a `style` attribute.

Both Quarto engines write plots to disk as ordinary PNGs before pandoc reads them.
So pandoc turns every static figure into `data:image/png;base64,`.
That is exactly the construct Gmail does not render.

### It is not only a Quarto problem

The alternative to Quarto is HTML written directly, by a person or by a model.
A model asked for "self-contained HTML" uses a `data:` URI image by default, for the same reason Quarto does.
Dropping Quarto does not remove the problem.

## `data:` URI images across email clients

### No vendor documents it

Google's [CSS Support](https://developers.google.com/workspace/gmail/design/css) page is the only first-party Gmail rendering reference.
It covers CSS.
It never mentions images or URI schemes.

Microsoft's only first-party HTML rendering document is [Word 2007 HTML and CSS Rendering Capabilities in Outlook 2007](https://learn.microsoft.com/en-us/previous-versions/office/developer/office-2007/aa338201(v=office.12)), written in August 2006 and archived.
It predates the question.

Apple documents [MailKit](https://developer.apple.com/documentation/mailkit) extensions and archived [Mail Stationery release notes](https://developer.apple.com/library/archive/releasenotes/AppleApplications/MailStationeryRelNote/index.html).
Neither states what Mail renders in a received message.

So there is no vendor statement to cite from anyone.
That gap is the finding.

### Can I Email is the available source, and it is community-maintained

[Can I Email's `image-base64` feature](https://www.caniemail.com/features/image-base64/) is a community-maintained support matrix, not a vendor statement.
This file uses it because nothing else covers the question.
Every use is labelled community-maintained.

The rows below were pulled from `https://www.caniemail.com/api/data.json` on 2026-09-09.
The JSON is authoritative where it and the rendered page disagree.
`y` means supported, `a` partial, and `n` not supported.
The date is when that row was last tested.

| Client | `data:` image | Last tested |
| --- | --- | --- |
| Gmail desktop webmail | `n` | 2024-05 |
| Gmail iOS app | `n` | 2020-02 |
| Gmail Android app | `n` | 2020-02 |
| Gmail mobile webmail | `n` | 2020-02 |
| Apple Mail macOS / iOS | `y` | from 13 |
| Outlook.com | `y` | 2024-01 |
| Outlook iOS / Android | `y` | |
| Outlook Windows 2019 | `a`, "Does not render Base 64 gif format" | |
| Thunderbird | `y` | |
| Fastmail | `y` | 2021-07 |

Most importantly, **Gmail is uniformly "no"** on all four surfaces.
It is not a quirk of one platform that a caller could avoid.
It covers all of Gmail.
The desktop row is also the most recent evidence in the table: retested 2024-05 and still `n`.
So this is not a stale 2020 measurement that Google has since fixed.

The Outlook Windows row is partial rather than supported.
Its failure is narrow: GIF only.

### What the table does not settle

Can I Email carries no row for the new Outlook for Windows.
Across the whole dataset the Outlook platform keys are `windows` (2007 to 2019), `windows-mail`, `macos`, `outlook-com`, `ios` and `android`.
The rewritten client that Microsoft now ships is absent.
So nothing here covers it.

See [Unverified and conflicting](#unverified-and-conflicting) for the rest.

## Gmail and `<style>` in `<head>`

Google documents the construct and uses it.
The [CSS Support](https://developers.google.com/workspace/gmail/design/css) page states: "You can style email sent to Gmail using inline `<style>` blocks and standard CSS."
Both worked examples on that page put the `<style>` element inside `<head>`.
So a `<head>` stylesheet is supported, not tolerated.

Google states **no size limit** for it.
Fetched and searched on 2026-09-09: the words "limit", "KB", "byte", "8192" and "16384" do not appear in the article body.

The widely repeated 8192 character figure has no Google source.
It is a 2017 community measurement.
A 16 KB figure in [hteumeuleu/email-bugs#90](https://github.com/hteumeuleu/email-bugs/issues/90) superseded it.
Later sources have copied the 8192 figure since.
If Epistole quotes a number, it should quote 16 KB and label it community testing.

[`css-in-an-html-body.md`](css-in-an-html-body.md) holds the full treatment of CSS support, the per-client table, and the clipping threshold.
It was written for [#19](https://github.com/ozanozbeker/epistole/issues/19).
That file supersedes the framing used while specifying #8.
That framing assumed Outlook's Word engine ignores a `<head>` stylesheet outright.
It does not.

## Message size arithmetic

### The three limits are measured against different things

| Backend | Limit | Measured against |
| --- | --- | --- |
| Graph | 4 MB per write request | the whole HTTP request, `message.body.content` inside it |
| SMTP | whatever the server advertises via `SIZE` | the whole RFC 5322 message |
| Gmail | 36,700,160 bytes on `users.messages.send` | the whole RFC 5322 message |

Graph is the exception.
It also removes the choice.
"Write requests in the Microsoft Graph API have a size limit of 4 MB.
Requests exceeding the size limit fail with the status code HTTP 413, and the error message 'Request entity too large' or 'Payload too large'" ([Use the Microsoft Graph API](https://learn.microsoft.com/en-us/graph/use-the-api)).
The statement sits under the general HTTP-methods heading rather than on any endpoint, so it covers `POST /me/sendMail`, `POST /me/messages` and `PATCH /me/messages/{id}` alike.

Read 4 MB as a limit, not a guarantee.
The same passage adds that "in some cases, the actual write request size limit is lower than 4 MB", and names 3 MB for `POST /me/events/{id}/attachments`.
Microsoft documents no such lower figure for the mail endpoints, but it has reserved the right to have one.

There is no way to send a body over the cap.
The `uploadSession` resource "provides information about how to upload large files to OneDrive, OneDrive for Business, or SharePoint document libraries, or to Outlook event and message items as attachments" ([uploadSession](https://learn.microsoft.com/en-us/graph/api/resources/uploadsession)).
So it covers files and attachments.
The word "body" does not appear on that page, so there is no chunked body.
`PATCH` on a draft replaces `body` rather than appending to it.
It is itself a 4 MB write request.
So a body cannot be assembled across calls either.

Bytes that need to be sent therefore have to become attachments, where an upload session does exist: "you can attach files up to 150 MB to an Outlook message or event item", and "if the file size is between 3 MB and 150 MB, create an upload session" ([Attach large files](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)).
That page also states the permission cost outright: "Make sure to request `Mail.ReadWrite` permission to create the uploadSession for a message".

### What a real report weighed

The measurement ran on 2026-09-08 with Quarto 1.10.18, pandoc 3.11 and CPython 3.13.
It used a locally rendered report with one matplotlib figure and one plotly figure:

| Quantity | Bytes |
| --- | --- |
| HTML | 7,741,183 |
| `sendMail` JSON around it | 7,909,986 |
| Graph's cap | 4,000,000 |
| SMTP `SIZE` advertised by the test server | 35,882,577 |
| Gmail's `users.messages.send` cap | 36,700,160 |

The same message is routine on SMTP and Gmail and impossible on Graph.

The JSON envelope's own overhead is small and input-dependent.
A measurement on 2026-09-09 used a synthetic body that is almost entirely base64.
The `sendMail` JSON added 175 bytes to a 4,194,379-byte HTML body, because base64 output contains no character JSON has to escape.
The 2.2 percent seen on the real report above is the escaping cost of ordinary prose and markup, not of the embedded images.

### Graph's cap admits about 3 MB of original image

A `data:` body is roughly the raw bytes times 4/3, so a 4,000,000-byte request holds roughly 3,000,000 bytes of original image.
Measured 2026-09-09: a 3,145,728-byte image becomes a 4,194,379-byte HTML body and a 4,194,554-byte `sendMail` request.
That request is already over the cap.

Moving the same bytes into attachments raises the limit from about 3 MB in total to 150 MB per file.
That is the entire size argument for the rewrite.
It applies to one backend.

### The rewrite is not a bandwidth optimisation

This folklore is worth refuting.
The claim is that base64 in an HTML body takes 33 percent more bytes in the sent message than the same bytes as an attachment.
It does not, because the body is not encoded as base64 a second time.

Python encodes a base64-heavy HTML body as **quoted-printable**.
Base64's alphabet is entirely quoted-printable-safe.
So quoted-printable passes it through and only adds a soft line break.

On 2026-09-08, with CPython 3.13, a 1 MiB image took 1,434,975 bytes in the sent message as a `data:` URI and 1,417,302 as the `cid:` equivalent.
The difference is **1.25 percent**.

The re-measurement on 2026-09-09 used CPython 3.14.7 and random incompressible bytes.
The result holds at three sizes:

| Original image | `data:` as sent | `cid:` as sent | Difference |
| --- | --- | --- | --- |
| 1 MiB | 1,453,123 | 1,435,761 | 1.21% |
| 4 MiB | 5,810,840 | 5,740,441 | 1.23% |
| 16 MiB | 23,241,714 | 22,959,163 | 1.23% |

The ratio is stable because it is structural rather than input-dependent.
Quoted-printable emits 77 payload characters per line plus a `=` and a CRLF, so 3 bytes of framing per 77.
Base64 emits 76 payload characters plus a CRLF, so 2 bytes of framing per 76.
The whole difference is that framing.

So the `data:` to `cid:` rewrite has two benefits and no others: images that render in Gmail, and a Graph request that fits under 4 MB because the bytes moved to where an upload session exists.

### Reconciling Microsoft's 33 percent with Google's 37 percent

[`attachment-and-inline-rules.md`](attachment-and-inline-rules.md) records that Microsoft states 33 percent base64 expansion where Google states 37 percent.
It leaves the disagreement open.
They are not in conflict.
They measure different things.

Measuring 1 MiB of random bytes on 2026-09-09 gives:

- base64 alone: 1,398,104 characters, **33.3 percent** expansion, which is 4/3 exactly.
- base64 with the CRLF every 76 characters that MIME requires: 1,434,898 bytes, **36.8 percent**.

Microsoft quotes the encoding.
Google quotes the encoding as it actually appears in a message.
Both are right.
A caller should budget for Google's.

## Prior art for rewriting `data:` to `cid:`

### blastula does it, and it is the closest analogue

blastula's `cid_images()` walks the rendered HTML, pulls each `data:` image out, and rewrites it as a `cid:` reference backed by an inline attachment ([`R/utils-html_manipulation.R`](https://github.com/rstudio/blastula/blob/master/R/utils-html_manipulation.R), line 346, read 2026-09-09).
`render_email()` calls it immediately after rendering.
That is exactly the Epistole use case.

### Copy the content id format, and the reason

blastula writes `img1.png`, with no `@domain` part, against RFC 2045.
The source says why, at lines 357 and 358:

```text
# According to the spec there should be an @domain on this, but it makes
# attachment UI show up for Outlook.com (e.g. AT00001.bin)
```

A spec-compliant `Content-ID` makes Outlook.com display a spurious attachment.
No RFC contains this interoperability finding.
It is the reason to ignore the world-uniqueness advice that comes with a `msg-id`.

### Two bugs in blastula's version not to copy

- Its regex `^data:image/(\w+);(base64,)(.+)` misses `image/svg+xml`, because `+` is not `\w` (line 384).
- It only touches `<img src>`, so `url(data:...)` inside CSS is ignored.
  The string `url(` appears nowhere in the file.
  Every rewrite goes through `replace_attr(..., tag_name = "img", attr_name = "src", ...)`.
  Pandoc emits exactly the construct it misses.

A real input triggers both bugs.
The measured Quarto report contains `url(data:image/svg+xml,...)` inside its embedded CSS.

**Checking shows a third item recorded on [#11](https://github.com/ozanozbeker/epistole/issues/11) to be false.**
That comment says blastula "runs the regex with `perl = FALSE` to dodge a stack overflow on large unicode input", and attributes it to the `data:` regex.
It belongs to a different one.
`stringr::str_match` runs the `data:` regex.
It takes no `perl` argument at all.
The `perl = FALSE` is at line 225, on the `gfsub` call inside `replace_attr` that scans for `<img\s[^>]*>`.
Line 220 carries the comment: "perl needs to be FALSE to prevent stack overflow for very very large input".
The hazard is real and worth knowing about.
It is a property of the tag scan, not of the URI match.

### Quarto solves the same problem earlier in its own pipeline

Quarto's [`email.lua`](https://github.com/quarto-dev/quarto-cli/blob/main/src/resources/filters/quarto-post/email.lua) filter, read 2026-09-09, walks pandoc `Image` nodes twice.
The first pass rewrites each `src` to `cid:<name>` for the email body and records the path.
The second pass walks the same div again and rewrites `src` to a `data:image/<ext>;base64,` string, for a local preview copy.
The bytes are then base64-encoded into the `.output_metadata.json` that Posit Connect consumes.

It shows two things.

It names its content ids `img<N>.<ext>`, the same shape blastula chose.
Quarto's codebase has no connection to blastula.
Two independent implementations chose the same bare, domain-less name.
That is the strongest evidence available that the RFC-compliant form causes trouble.

Quarto also acts at an earlier stage than Epistole can.
Quarto owns the document, so it intervenes before the `data:` URI exists.
Epistole receives finished HTML and has to intervene after.
So a parse-and-rewrite step is unavoidable, not a shortcut.

### No Python library does this

None was found.
`python-emails` explicitly returns the URI untouched ([`emails/transformer.py`](https://github.com/lavr/python-emails/blob/master/emails/transformer.py), line 245, inside `_load_attachment_func`):

```text
if uri[:5].lower() == 'data:':
    return uri
```

So the rewrite has to be Epistole's own code rather than a dependency.

## Unverified and conflicting

These items are carried forward, not resolved.
Do not settle any of these by inference.

- **Whether Gmail's image proxy breaks `data:` URIs.**
  Google documents the proxy and says nothing about URI schemes.
  Checked again on 2026-09-09: the Gmail CSS reference contains no occurrence of `data:`, `cid:` or `http:`.
  The word "image" appears only inside CSS property names such as `background-image`.
  The causal explanation is plausible and unsourced, so this file does not claim it.
- **Whether the 8192 character `<style>` limit for Gmail has any vendor source.**
  Can I Email says 16 KB, community-tested.
  Neither figure is Google's.
  Google publishes no figure at all.
- **Whether new Outlook for Windows renders `data:` URIs.**
  A check on 2026-09-09 confirmed that Can I Email has no row for it.
  So the question is open, not answered badly.
  Only a live test settles it.
- **Whether Apple has ever documented Mail's HTML support.**
  Nothing was found.
  A negative is hard to prove.
  This one is not proven.
- **How current Can I Email's Gmail rows are.**
  This item is made more precise, not carried forward unchanged.
  The iOS, Android and mobile-webmail rows were last tested 2020-02.
  Desktop webmail was retested 2024-05 and is still `n`.
  The claim recorded on #22 that all the Gmail rows date to February 2020 is wrong on the desktop row.
- **Whether Graph's "4 MB" means 4,000,000 or 4,194,304 bytes.**
  Microsoft writes "4 MB" and never disambiguates.
  Issue [#20](https://github.com/ozanozbeker/epistole/issues/20) picked `4_000_000` as the conservative reading.
  That is a choice, not a citation.
- **Whether Graph applies a lower write cap to the mail endpoints.**
  Microsoft says the limit is "in some cases" below 4 MB and names only a calendar endpoint.
  Nothing states that `sendMail` is or is not one of those cases.

## Figures to recheck

Local runs are dated inline above: 2026-09-08 against Quarto 1.10.18, pandoc 3.11 and CPython 3.13, and 2026-09-09 against CPython 3.14.7.
Mail service limits change.
Re-check them before anything in the spec depends on one.

In particular, re-check:

- Graph's 4 MB write-request cap, and whether a chunked body path has appeared.
- Gmail's 36,700,160-byte cap, which comes from the v1 discovery document rather than a prose page.
- Can I Email's `image-base64` rows for Gmail, and whether any row yet covers new Outlook for Windows.
- Whether Google has published anything at all about images or URI schemes in HTML bodies.

Reproduce the size arithmetic with:

```bash
python3 - <<'PY'
import base64, os
from email.message import EmailMessage
from email.policy import SMTP

img = os.urandom(1024 * 1024)
b64 = base64.b64encode(img).decode("ascii")

a = EmailMessage()
a["Subject"], a["From"], a["To"] = "s", "a@example.com", "b@example.com"
a.set_content("hi")
a.add_alternative(f'<html><body><img src="data:image/png;base64,{b64}"></body></html>',
                  subtype="html")

b = EmailMessage()
b["Subject"], b["From"], b["To"] = "s", "a@example.com", "b@example.com"
b.set_content("hi")
b.add_alternative('<html><body><img src="cid:img1.png"></body></html>', subtype="html")
b.get_payload()[1].add_related(img, maintype="image", subtype="png", cid="<img1.png>")

wa, wb = len(a.as_bytes(policy=SMTP)), len(b.as_bytes(policy=SMTP))
print(f"data: {wa:,}  cid: {wb:,}  delta {wa / wb - 1:.2%}")
PY
```

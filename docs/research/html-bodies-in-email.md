# HTML bodies in email

Research for [issue #22](https://github.com/ozanozbeker/epistole/issues/22).
The substance was gathered on 2026-09-08 while specifying [#8](https://github.com/ozanozbeker/epistole/issues/8) and [#11](https://github.com/ozanozbeker/epistole/issues/11), and lived only in a prototype and in issue comments until this file.
Primary sources only.
Every factual claim below carries a URL.
Where a source is silent or two sources disagree, the text says so instead of guessing.
Where a claim comes from a local run rather than a document, the text says so.
Community-maintained sources are used only where no vendor documents the behaviour, and are labelled as such at every use.

Documents were read on 2026-09-08 and re-checked on 2026-09-09.
Local runs are dated where they appear.
See [Figures to recheck](#figures-to-recheck).

## What this means for epistole's design

**Recipient-side and backend-side limits are different problems, and only one of them is a choice.**
Gmail and Outlook appear in this work wearing two hats.
As **backends** they are things epistole talks to, and a caller who picks a different backend never meets their limits.
As **recipients** they are where the mail lands, and no choice of backend avoids them.
That distinction decides where a fix belongs.

Four problems turn up in a realistic HTML body.
Only one is Quarto's, and only one is backend-side.

| Problem | Quarto's fault | Where it bites | Fixable by epistole |
| --- | --- | --- | --- |
| `data:` URI images do not render in Gmail | no | recipient | yes, by rewriting them to `cid:` |
| A `<head>` stylesheet is unevenly supported | no | recipient | no, and it should not try |
| JavaScript charts render nowhere | yes | recipient | no |
| Graph rejects a request over 4 MB with `413` | no | backend | only by moving bytes into attachments |

Three of the four are recipient-side.
They apply to every message epistole sends over every backend it will ever have, SMTP included.
Only the `413` belongs to a backend, and it is the only one a caller can dodge by choosing differently.

That is why the `data:` to `cid:` rewrite is core rather than a Graph concern.
It was originally scoped as a Graph workaround, and that was the wrong place for it.

**The rewrite buys rendering, not bandwidth.**
The folklore says moving base64 out of an HTML body saves a third of the message.
Measured, it saves about 1.2 percent.
Python encodes a base64-heavy HTML body as quoted-printable rather than base64, and base64's own output characters are all quoted-printable-safe, so the body is not re-expanded.
Argue the rewrite on rendering and on Graph's 4 MB cap, never on size.

**A spec-compliant content id is the thing that breaks Outlook.com.**
RFC 2045 asks for a `msg-id`, which has an `@domain` part. blastula ships `img1.png` with no domain, on purpose, because the compliant form makes Outlook.com display a spurious attachment.
No RFC will tell you this, and it contradicts the world-uniqueness instinct.

**No vendor documents `data:` image support, so the load-bearing evidence here is community testing.**
Google's CSS reference never mentions images or URI schemes.
Microsoft's only HTML rendering reference is an archived article about Word 2007.
Apple documents nothing for received mail.
Can I Email is the source, it is community-maintained, and this file labels it as such everywhere it is used.

## Where a `data:` URI comes from

### Quarto's `embed-resources`

Quarto documents the flag plainly.
Of `embed-resources: true`: "This will produce a standalone HTML file with no external dependencies, using `data:` URIs to incorporate the contents of linked scripts, style sheets, images, and videos" ([Quarto HTML Basics](https://quarto.org/docs/output-formats/html-basics.html)).

This is the natural setting for a report someone intends to email, because the alternative is a folder of sidecar files that no mail client will follow.
So the construct arrives by default, not by mistake.

### Pandoc's `SelfContained.hs` does the actual embedding

Quarto does not implement the embedding itself.
It hides the flag from its main pandoc call and re-runs pandoc over the finished HTML ([`src/core/pandoc/self-contained.ts`](https://github.com/quarto-dev/quarto-cli/blob/main/src/core/pandoc/self-contained.ts)).

The work happens in [`src/Text/Pandoc/SelfContained.hs`](https://github.com/jgm/pandoc/blob/main/src/Text/Pandoc/SelfContained.hs), whose module header states its purpose: "Functions for converting an HTML file into one that can be viewed offline, by incorporating linked images, CSS, and scripts into the HTML using data URIs."
Pandoc's manual describes `--embed-resources` as "Produce a standalone HTML file with no external dependencies, using `data:` URIs to incorporate the contents of linked scripts, stylesheets, images, and videos", and `--self-contained` as a "Deprecated synonym for `--embed-resources --standalone`" ([Pandoc manual](https://pandoc.org/MANUAL.html)).

Read on 2026-09-09, the module does three things, and only the first is attribute rewriting.

`isSourceAttribute` covers `src`, `data-src`, `href` on a `link`, `poster` and `data-background-image`, and each becomes a `makeDataURI` value.
That is where a figure becomes `data:image/png;base64,`.

A fetched `text/css` `<link>` is replaced outright by an inline `<style>` block rather than being rewritten in place.
The conditions under which it does that, and the `</` guard that often stops it, are covered in [`css-in-an-html-body.md`](css-in-an-html-body.md) and are not repeated here.

`url(...)` references inside CSS are rewritten too, by `cssURLs` and `handleCSSUrl`, which short-circuit on a URI that is already `data:`.
This is the detail that matters most for the rewrite epistole has to perform: **a `data:` URI can arrive inside a stylesheet, not only in an `<img src>`**.
A measured Quarto report contains `url(data:image/svg+xml,...)` in its embedded CSS for exactly this reason.

What the module never does is inline CSS onto elements as a `style` attribute.

Both Quarto engines write plots to disk as ordinary PNGs before pandoc sees them.
So every static figure arrives as `data:image/png;base64,`, which is exactly the construct Gmail refuses.

### It is not only a Quarto problem

The alternative to Quarto is HTML written on the fly, by a person or by a model.
A model asked for "self-contained HTML" reaches for a `data:` URI image by default, for the same reason Quarto does.
Nothing about this leaves when Quarto leaves.

## `data:` URI images across email clients

### No vendor documents it

Google's [CSS Support](https://developers.google.com/workspace/gmail/design/css) page is the only first-party Gmail rendering reference, and it covers CSS.
It never mentions images or URI schemes.

Microsoft's only first-party HTML rendering document is [Word 2007 HTML and CSS Rendering Capabilities in Outlook 2007](https://learn.microsoft.com/en-us/previous-versions/office/developer/office-2007/aa338201(v=office.12)), written in August 2006 and archived.
It predates the question.

Apple documents [MailKit](https://developer.apple.com/documentation/mailkit) extensions and archived [Mail Stationery release notes](https://developer.apple.com/library/archive/releasenotes/AppleApplications/MailStationeryRelNote/index.html), neither of which states what Mail renders in a received message.

So there is no vendor statement to cite, from anyone, and the gap is the finding.

### Can I Email is the available source, and it is community-maintained

[Can I Email's `image-base64` feature](https://www.caniemail.com/features/image-base64/) is a community-maintained support matrix, not a vendor statement.
It is used here because nothing else covers the question, and it is labelled as community-maintained at every use.

Rows below were pulled from `https://www.caniemail.com/api/data.json` on 2026-09-09, which is authoritative where the rendered page and the JSON disagree.
`y` supported, `a` partial, `n` not supported.
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

The finding that matters is that **Gmail is uniformly "no"** on all four surfaces.
It is not a platform quirk to route around; it is the whole provider.
The desktop row is also the freshest evidence in the table, retested 2024-05 and still `n`, so this is not a stale 2020 measurement that Google has since fixed.

Note the Outlook Windows row is partial rather than supported, and the failure is narrow: GIF only.

### What the table does not settle

Can I Email carries no row for the new Outlook for Windows.
Across the whole dataset the Outlook platform keys are `windows` (2007 to 2019), `windows-mail`, `macos`, `outlook-com`, `ios` and `android`.
The rewritten client that Microsoft now ships is absent, so nothing here speaks to it.

See [Unverified and conflicting](#unverified-and-conflicting) for the rest.

## Gmail and `<style>` in `<head>`

Google documents the construct and uses it.
The [CSS Support](https://developers.google.com/workspace/gmail/design/css) page states: "You can style email sent to Gmail using inline `<style>` blocks and standard CSS."
Both worked examples on that page put the `<style>` element inside `<head>`.
So a `<head>` stylesheet is supported, not tolerated.

Google states **no size limit** for it.
Fetched and searched on 2026-09-09: the words "limit", "KB", "byte", "8192" and "16384" do not appear in the article body.

The widely repeated 8192 character figure has no Google source.
It is a 2017 community measurement, superseded by a 16 KB figure in [hteumeuleu/email-bugs#90](https://github.com/hteumeuleu/email-bugs/issues/90) and copied forward since.
If epistole quotes a number, it should quote 16 KB and label it community testing.

The full treatment of CSS support, the per-client table, and the clipping threshold live in [`css-in-an-html-body.md`](css-in-an-html-body.md), written for [#19](https://github.com/ozanozbeker/epistole/issues/19).
That file supersedes the framing used while specifying #8, which assumed Outlook's Word engine ignores a `<head>` stylesheet outright.
It does not.

## Message size arithmetic

### The three ceilings are measured against different things

| Backend | Ceiling | Measured against |
| --- | --- | --- |
| Graph | 4 MB per write request | the whole HTTP request, `message.body.content` inside it |
| SMTP | whatever the server advertises via `SIZE` | the whole RFC 5322 message |
| Gmail | 36,700,160 bytes on `users.messages.send` | the whole RFC 5322 message |

Graph is the odd one, and it is the one that removes the choice.
"Write requests in the Microsoft Graph API have a size limit of 4 MB.
Requests exceeding the size limit fail with the status code HTTP 413, and the error message 'Request entity too large' or 'Payload too large'" ([Use the Microsoft Graph API](https://learn.microsoft.com/en-us/graph/use-the-api)).
The statement sits under the general HTTP-methods heading rather than on any endpoint, so it covers `POST /me/sendMail`, `POST /me/messages` and `PATCH /me/messages/{id}` alike.

Read 4 MB as a ceiling, not a promise.
The same passage adds that "in some cases, the actual write request size limit is lower than 4 MB", and names 3 MB for `POST /me/events/{id}/attachments`.
Microsoft documents no such lower figure for the mail endpoints, but it has reserved the right to have one.

There is no path past the cap for a body.
The `uploadSession` resource "provides information about how to upload large files to OneDrive, OneDrive for Business, or SharePoint document libraries, or to Outlook event and message items as attachments" ([uploadSession](https://learn.microsoft.com/en-us/graph/api/resources/uploadsession)).
Files and attachments, then.
The word "body" does not appear on that page, so there is no chunked body.
`PATCH` on a draft replaces `body` rather than appending to it, and is itself a 4 MB write request, so a body cannot be assembled across calls either.

Bytes that need to travel therefore have to become attachments, where an upload session does exist: "you can attach files up to 150 MB to an Outlook message or event item", and "if the file size is between 3 MB and 150 MB, create an upload session" ([Attach large files](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)).
That page also states the permission cost outright: "Make sure to request `Mail.ReadWrite` permission to create the uploadSession for a message".

### What a real report weighed

Measured on 2026-09-08, Quarto 1.10.18, pandoc 3.11, CPython 3.13.
A locally rendered report with one matplotlib figure and one plotly figure:

| Quantity | Bytes |
| --- | --- |
| HTML | 7,741,183 |
| `sendMail` JSON around it | 7,909,986 |
| Graph's cap | 4,000,000 |
| SMTP `SIZE` advertised by the test server | 35,882,577 |
| Gmail's `users.messages.send` cap | 36,700,160 |

The same message is routine on SMTP and Gmail and impossible on Graph.

The JSON envelope's own overhead is small and input-dependent.
Measured 2026-09-09 on a synthetic body that is almost entirely base64, the `sendMail` JSON added 175 bytes to a 4,194,379-byte HTML body, because base64 output contains no character JSON has to escape.
The 2.2 percent seen on the real report above is the escaping cost of ordinary prose and markup, not of the embedded images.

### Graph's cap admits about 3 MB of original image

A `data:` body is roughly the raw bytes times 4/3, so a 4,000,000-byte request holds roughly 3,000,000 bytes of original image.
Measured 2026-09-09: a 3,145,728-byte image becomes a 4,194,379-byte HTML body and a 4,194,554-byte `sendMail` request, which is already over the cap.

Moving the same bytes into attachments lifts the ceiling from about 3 MB in total to 150 MB per file.
That is the entire size argument for the rewrite, and it applies to one backend.

### The rewrite is not a bandwidth optimisation

This is the folklore worth killing.
The claim is that base64 in an HTML body costs 33 percent more on the wire than the same bytes as a MIME part.
It does not, because the body is not encoded as base64 a second time.

Python encodes a base64-heavy HTML body as **quoted-printable**, and base64's alphabet is entirely quoted-printable-safe, so quoted-printable passes it through and only adds a soft line break.

Measured 2026-09-08, CPython 3.13, on a 1 MiB image: 1,434,975 bytes on the wire as a `data:` URI against 1,417,302 as the `cid:` equivalent, a difference of **1.25 percent**.

Re-measured 2026-09-09, CPython 3.14.7, on random incompressible bytes, and the result holds at three sizes:

| Original image | `data:` on the wire | `cid:` on the wire | Difference |
| --- | --- | --- | --- |
| 1 MiB | 1,453,123 | 1,435,761 | 1.21% |
| 4 MiB | 5,810,840 | 5,740,441 | 1.23% |
| 16 MiB | 23,241,714 | 22,959,163 | 1.23% |

The ratio is stable because it is structural rather than input-dependent.
Quoted-printable emits 77 payload characters per line plus a `=` and a CRLF, so 3 bytes of framing per 77.
Base64 emits 76 payload characters plus a CRLF, so 2 bytes of framing per 76.
The whole difference is that framing.

So the `data:` to `cid:` rewrite buys two things and no others: images that render in Gmail, and a Graph request that fits under 4 MB because the bytes moved to where an upload session exists.

### Reconciling Microsoft's 33 percent with Google's 37 percent

[`attachment-and-inline-rules.md`](attachment-and-inline-rules.md) records that Microsoft states 33 percent base64 expansion where Google states 37 percent, and leaves the disagreement open.
They are not in conflict.
They measure different things.

Measured 2026-09-09 on 1 MiB of random bytes:

- base64 alone: 1,398,104 characters, **33.3 percent** expansion, which is 4/3 exactly.
- base64 with the CRLF every 76 characters that MIME requires: 1,434,898 bytes, **36.8 percent**.

Microsoft quotes the encoding.
Google quotes the encoding as it actually appears in a message.
Both are right and a caller should budget for Google's.

## Prior art for rewriting `data:` to `cid:`

### blastula does it, and it is the closest analogue

blastula's `cid_images()` walks the rendered HTML, pulls each `data:` image out, and rewrites it as a `cid:` reference backed by an inline attachment ([`R/utils-html_manipulation.R`](https://github.com/rstudio/blastula/blob/master/R/utils-html_manipulation.R), line 346, read 2026-09-09).
`render_email()` calls it immediately after rendering, which is exactly the epistole use case.

### Steal the content id format, and the reason

blastula writes `img1.png`, with no `@domain` part, against RFC 2045.
The source says why, at lines 357 and 358:

```text
# According to the spec there should be an @domain on this, but it makes
# attachment UI show up for Outlook.com (e.g. AT00001.bin)
```

A spec-compliant `Content-ID` makes Outlook.com display a spurious attachment.
This is an interoperability finding no RFC will give you, and it is the reason to ignore the world-uniqueness advice that a `msg-id` invites.

### Two bugs in blastula's version not to copy

- Its regex `^data:image/(\w+);(base64,)(.+)` misses `image/svg+xml`, because `+` is not `\w` (line 384).
- It only touches `<img src>`, so `url(data:...)` inside CSS is ignored.
  The string `url(` appears nowhere in the file; every rewrite goes through `replace_attr(..., tag_name = "img", attr_name = "src", ...)`.
  Pandoc emits exactly the construct it misses.

Both fire on a real input.
The measured Quarto report contains `url(data:image/svg+xml,...)` inside its embedded CSS.

**A third item recorded on [#11](https://github.com/ozanozbeker/epistole/issues/11) does not survive checking.**
That comment says blastula "runs the regex with `perl = FALSE` to dodge a stack overflow on large unicode input", and attributes it to the `data:` regex.
It belongs to a different one.
The `data:` regex is run by `stringr::str_match`, which takes no `perl` argument at all.
The `perl = FALSE` is at line 225, on the `gfsub` call inside `replace_attr` that scans for `<img\s[^>]*>`, and line 220 carries the comment: "perl needs to be FALSE to prevent stack overflow for very very large input".
The hazard is real and worth knowing about, but it is a property of the tag scan rather than of the URI match.

### Quarto solves the same problem earlier in its own pipeline

Quarto's [`email.lua`](https://github.com/quarto-dev/quarto-cli/blob/main/src/resources/filters/quarto-post/email.lua) filter walks pandoc `Image` nodes twice, read 2026-09-09.
The first pass rewrites each `src` to `cid:<name>` for the email body and records the path.
The second pass walks the same div again and rewrites `src` to a `data:image/<ext>;base64,` string, for a local preview copy.
The bytes are then base64-encoded into the `.output_metadata.json` that Posit Connect consumes.

Two things to take from it.

It names its content ids `img<N>.<ext>`, the same shape blastula chose and for a codebase with no connection to blastula.
Two independent implementations landing on the same bare, domain-less name is the strongest evidence available that the RFC-compliant form is the one that causes trouble.

It also stands somewhere epistole cannot.
Quarto owns the document, so it intervenes before the `data:` URI exists. epistole receives finished HTML and has to intervene after, which is why a parse-and-rewrite step is unavoidable rather than a shortcut.

### No Python library does this

None was found.
`python-emails` declines explicitly, returning the URI untouched ([`emails/transformer.py`](https://github.com/lavr/python-emails/blob/master/emails/transformer.py), line 245, inside `_load_attachment_func`):

```text
if uri[:5].lower() == 'data:':
    return uri
```

That absence is the reason the rewrite has to be epistole's own code rather than a dependency.

## Unverified and conflicting

Carried forward rather than resolved.
Do not settle any of these by inference.

- **Whether Gmail's image proxy is the mechanism that breaks `data:` URIs.**
  Google documents the proxy and says nothing about URI schemes.
  Checked again on 2026-09-09: the Gmail CSS reference contains no occurrence of `data:`, `cid:` or `http:`, and the word "image" appears only inside CSS property names such as `background-image`.
  The causal story is plausible and unsourced, so this file does not tell it.
- **Whether the 8192 character `<style>` limit for Gmail has any vendor source.**
  Can I Email says 16 KB, community-tested.
  Neither figure is Google's, and Google publishes no figure at all.
- **Whether new Outlook for Windows renders `data:` URIs.**
  Confirmed 2026-09-09 that Can I Email has no row for it, so the question is open rather than answered badly.
  Only a live test settles it.
- **Whether Apple has ever documented Mail's HTML support.**
  Nothing was found.
  A negative is hard to prove and this one is not proven.
- **How current Can I Email's Gmail rows are.**
  Sharpened rather than carried: the iOS, Android and mobile-webmail rows were last tested 2020-02, but desktop webmail was retested 2024-05 and is still `n`.
  The claim recorded on #22 that all the Gmail rows date to February 2020 is wrong on the desktop row.
- **Whether Graph's "4 MB" means 4,000,000 or 4,194,304 bytes.**
  Microsoft writes "4 MB" and never disambiguates. [#20](https://github.com/ozanozbeker/epistole/issues/20) picked `4_000_000` as the conservative reading, which is a choice rather than a citation.
- **Whether Graph applies a lower write cap to the mail endpoints.**
  Microsoft says the limit is "in some cases" below 4 MB and names only a calendar endpoint.
  Nothing states that `sendMail` is or is not one of those cases.

## Figures to recheck

Local runs are dated inline above: 2026-09-08 against Quarto 1.10.18, pandoc 3.11 and CPython 3.13, and 2026-09-09 against CPython 3.14.7.
Provider limits move; re-check before anything in the spec depends on one.

Specifically:

- Graph's 4 MB write-request cap, and whether a chunked body path has appeared.
- Gmail's 36,700,160-byte cap, which comes from the v1 discovery document rather than a prose page.
- Can I Email's `image-base64` rows for Gmail, and whether any row yet covers new Outlook for Windows.
- Whether Google has published anything at all about images or URI schemes in HTML bodies.

Reproduce the wire arithmetic with:

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

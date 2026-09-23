# A caller passes content as HTML, Markdown, or plain text, and every message has plain text

`Message` takes its content through one of three keywords: `html=`, `markdown=`, or `text=`.
Every message carries plain text.
When the content is HTML, Epistole derives the plain text itself with an extractor written on the stdlib `html.parser`.
The extractor is in the core and needs no extra.
When the content is Markdown, the source is the plain text.
An extra renders the HTML.
When the content is plain text, that is the whole message.
`text=` alongside `html=` or `markdown=` takes precedence outright.
`text_renderer=` replaces Epistole's extractor with the caller's.
Decided on [#15](https://github.com/ozanozbeker/epistole/issues/15), based on `docs/research/html-to-plain-text.md`.
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): a test reads the plain text as `submissions[0].message.text`, because the doubles record a `Submission` rather than a message with those headers set (ADR-0015).
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): derived plain text may be empty, so the non-empty rule holds for `text=` alone.
Amended on [#36](https://github.com/ozanozbeker/epistole/issues/36): `text=""` is allowed, because some callers send the subject alone.

## Why

**Every message carries a plain-text field, and it is a `str` that may be empty.**
An image-only body and a body whose only text is in `<style>` both derive to `""`.
A caller who puts the whole message in the subject passes `text=""`.
This audience sends all three.
Raising on any of them would make a legitimate message unsendable.
Substituting a placeholder would send words that nobody wrote.
So the invariant is that `.text` is always a `str`, not that it always holds characters.

**Epistole derives, and no other Python library does.**
red-mail, python-emails, Django, and Flask-Mail take `text` and `html` separately and leave the text to the caller.
Epistole's audience sends rendered reports.
A rendered report has no hand-written text version, and never will.
Requiring `text` would mean HTML-only mail in practice.
The case for plain text is not spam scoring, which SpamAssassin puts at 0.1.
It is text-only clients, screen readers, preview panes, notification pipes, and archive search.
Derivation takes 0.27 ms on a 3 KB body.
It runs once per construction, so every copy in the send loop shares it (ADR-0002).

**The extractor is hand-rolled because the missing-extra branch has no good answer.**
An extra needs a behaviour for its absence.
Both candidates are wrong.
Omitting plain text produces the HTML-only mail that derivation exists to prevent.
Naive tag stripping sends the entire `<style>` block to the recipient.
So the absent branch has to be a real extractor.
Once that exists, the extra adds nothing.
The two libraries that match or exceed the hand-rolled output both have a disqualifying cost.
`inscriptis` is 22 MB with a hard `requests` dependency and an `lxml<6.2.0` bound that would apply to every Epistole user.
`html2text` is GPL-3.0-or-later, and Epistole is MIT.
The hand-rolled version came second of seven on output quality in under 90 lines.

**Markdown is the second entry because the audience prefers writing it, and its source is better plain text than any extractor makes.**
blastula's `md()` is the precedent.
It is not composition: it renders the caller's words and does not supply a header, footer, or template.
[#8](https://github.com/ozanozbeker/epistole/issues/8)'s "Epistole never composes HTML" was about blastula's block and section helpers.
That rule still applies.
People already write `[view it online](https://...)` for text.
So the source ships verbatim as the plain text, and the extractor never runs.

**Plain text alone is the third entry because an alert has no HTML to give.**
A cron failure or a pipeline notice is a sentence.
Making the caller wrap it in `<pre>` and escape it is extra work with no benefit.
Synthesizing HTML from it would give Epistole the composition path #8 ruled out.

**The tag is the keyword, never a sniff.**
blastula takes one `body` argument and dispatches on class.
A bare string is plain text, `md()` tags Markdown, and `htmltools::HTML()` tags raw HTML.
It sniffs nothing.
Python's keyword argument is the same tag one level up, with no wrapper types to import.
We considered a `content=` argument that guessed the format, and rejected it on `docs/research/prior-art.md`'s rule.
Every plain-text string is valid Markdown, so the guess is undecidable.
The failure is silent: `2 * 3 * 4` is sent as emphasis.

**The renderer hook exists because of ordering.**
Under ADR-0003, the `data:` rewrite runs before the plain text is made.
So the text never holds megabytes of base64.
A caller rendering from their own HTML string gets the base64.
The hook is the one way to render from the rewritten HTML in a single construction.
It also keeps `html2text`'s licence with the caller who chose it.

## Rules

- **A message takes exactly one of `html=` or `markdown=`, or neither.**
  Both is a `TypeError`.
  `text=` may accompany either, or stand alone.
  `Message()` with no content is a `TypeError`.
- **`text=` takes precedence.**
  Supplied plain text ships verbatim.
  Epistole never checks it against the HTML, never merges, and never derives.
  `text=""` is allowed and sends empty plain text, because some callers put the whole message in the subject.
  It differs from `None`: with `html=`, `None` derives the plain text and `""` sends none.
- **Plain text from HTML is `text_renderer(rewritten_html)` when given, else `epistole.html_to_text(rewritten_html)`.**
  The renderer is `Callable[[str], str]` and runs once at construction.
  It is not stored on the value, so equality stays by content (ADR-0002).
  It receives the HTML after the `data:` rewrite (ADR-0003).
  Passing it with `text=` or with `markdown=` is a `TypeError`, because it would be silently ignored otherwise.
  An exception it raises propagates unwrapped at the line that built the message.
  It is not an `EpistoleError` (ADR-0004).
  A return that is not a `str` is a `ValueError`.
  A return of `""` is not.
  The renderer replaces `html_to_text`, and `html_to_text` returns `""` for HTML with no text.
- **Plain text from Markdown is the source, verbatim.**
  Raw HTML blocks in the source, which CommonMark allows, ship as written.
  The alternative is a sniff, rejected above.
- **Markdown renders through `epistole[markdown]` on `markdown-it-py`, `commonmark` preset, no options.**
  When the extra is absent, the constructor raises `ImportError` naming it, as pandas and httpx do.
  Tables, footnotes, and `linkify` are not exposed in v1.
  A caller who needs them renders and passes `html=`.
  The rendered HTML goes through the `data:` rewrite like any other HTML.
- **Plain text alone ships `text/plain` alone.**
  There is no `multipart/alternative` and no synthesized HTML.
  On Graph, the body is `contentType: "text"`.
  An inline image on a text-only message has no HTML that references it, and degrades to a listed file (ADR-0003).
- **`epistole.html_to_text` is exported.**
  The default is visible, testable, and wrappable.
- **The extractor is best effort, pinned by fixtures.**
  It keeps links as `label <url>`, marks list items, and keeps one table row per line.
  It drops `<head>`, `<style>`, `<script>`, `<title>`, and comments.
  It prints an image's alt text in brackets and decodes entities.
  It never raises on malformed HTML.
  The exact output is not a contract.
  It may improve in a minor version.
  Two messages built from the same HTML are equal within one version, not across versions.
  A caller who needs frozen bytes passes `text=`.
- **The content attributes are `.html` and `.text`, with no underscore.**
  No builder method shares a constructor keyword's name, so ADR-0007's suffix does not apply.
  `.text` is always a `str`.
  `.html` is `None` on a text-only message.
  There is no `.markdown`.
  The source is in `.text` unless `text=` replaced it.
  The caller still holds their string, the same reasoning ADR-0003 used for the original HTML.

## Considered options

- **Require `text` for a multipart message.**
  It is the cheapest option, and every Python library does it.
  Rejected because the audience never has a text version, so the real outcome is HTML-only mail.
- **Raise on `text=""`.**
  This was the rule until [#36](https://github.com/ozanozbeker/epistole/issues/36), on the reasoning that nobody means to send empty plain text.
  Reversed because a caller who puts the whole message in the subject means exactly that.
- **Put the extractor in an extra.**
  Rejected above: the absent branch needs a real extractor anyway.
- **Depend on `inscriptis` or `html2text`.**
  Rejected on 22 MB plus an `lxml` upper bound, and on GPL, respectively.
  A caller who wants either can pass it as `text_renderer=`.
- **Take `content=` and detect the format.**
  Rejected above: it is a guess at meaning with a silent failure.
- **Take `content=` plus tagged `Html()` and `Markdown()` wrapper types, blastula's shape literally.**
  It is as explicit as keywords, but costs two exported types and a wrapper on the Quarto happy path.
- **Add a `markdown` helper returning HTML, `Message(html=md(src))`.**
  The source is gone by construction time.
  So the plain text would come from the extractor instead of the source.
- **Synthesize HTML for a text-only message, as blastula does.**
  blastula must, because its template is HTML.
  Epistole has no template.
  The HTML would be a worse copy of text every client already renders.
- **Lock the extractor's output as a contract.**
  Rejected because an 87-line extractor should be free to get better.
  Nobody diffs the derived plain text.

## Consequences

- Content has three ways in, one field each, and each field has one spelling.
  So ADR-0002's constructor rule still holds, with three keywords instead of one.
- The glossary gains *Content* and *Plain text*.
  *Complete message* now reads "plain text present, and HTML present whenever the content entered as HTML or Markdown".
- `Message(...)` can raise `ImportError`.
  The `html_to_text` extractor runs on every HTML construction.
- `MemoryBackend` tests read `submissions[0].message.text` on any entry, and get the text a text-only client shows (ADR-0015).
- The implementation adds `epistole[markdown]`, the first optional dependency that is not a backend.
- [#21](https://github.com/ozanozbeker/epistole/issues/21) documents `markdown=` as the entry for hand-written mail and `html=` for rendered reports.
- The `data:` rewrite in ADR-0003 and the `cid:` check in ADR-0002 run only when HTML exists.

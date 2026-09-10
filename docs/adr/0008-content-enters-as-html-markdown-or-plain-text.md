# Content enters as HTML, Markdown, or plain text, and plain text is always present

`Message` takes its content through one of three keywords: `html=`, `markdown=`, or `text=`.
Every message carries plain text.
When the content is HTML, Epistole derives the plain text itself with an extractor written on the stdlib `html.parser`, in the core, behind no extra.
When the content is Markdown, the source is the plain text and an extra renders the HTML.
When the content is plain text, that is the whole message.
`text=` alongside `html=` or `markdown=` wins outright, and `text_renderer=` swaps Epistole's extractor for the caller's.
Decided on [#15](https://github.com/ozanozbeker/epistole/issues/15), grounded by `docs/research/html-to-plain-text.md`.

## Why

**Epistole derives, and no other Python library does.** red-mail, python-emails, Django, and Flask-Mail take `text` and `html` separately and leave the text to the caller.
Epistole's audience sends rendered reports, and a rendered report has no hand-written text twin and never will.
Requiring `text` would mean HTML-only mail in practice.
The case for the part is not spam scoring, which SpamAssassin puts at 0.1, but text-only clients, screen readers, preview panes, notification pipes, and archive search.
Derivation costs 0.27 ms on a 3 KB body and runs once per construction, so every copy in the send loop shares it (ADR-0002).

**The extractor is hand-rolled because the missing-extra branch has no good answer.**
An extra needs a behaviour for its absence, and both candidates are wrong: omitting the part is the HTML-only mail derivation exists to prevent, and naive tag stripping ships the entire `<style>` block to the recipient.
So the absent branch has to be a real extractor, and once that exists the extra earns nothing.
The two libraries that beat or match the hand-rolled output both carry a disqualifying cost: `inscriptis` is 22 MB with a hard `requests` dependency and an `lxml<6.2.0` bound Epistole would push onto every user, and `html2text` is GPL-3.0-or-later against Epistole's MIT.
The hand-rolled version came second of seven on output quality in under 90 lines.

**Markdown is the second entry because the audience prefers writing it, and its source is better plain text than any extractor makes.** blastula's `md()` is the precedent, and it is not composition: it renders the caller's words, it does not supply a header, footer, or template. [#8](https://github.com/ozanozbeker/epistole/issues/8)'s "Epistole never composes HTML" was about blastula's block and section helpers, and it stands.
`[view it online](https://...)` is what people already write for text, so the source ships verbatim as the plain text and the extractor never runs.

**Plain text alone is the third entry because an alert has no HTML to give.**
A cron failure or a pipeline notice is a sentence.
Making the caller wrap it in `<pre>` and escape it is a tax with no return, and synthesizing HTML from it would give Epistole the composition path #8 ruled out.

**The tag is the keyword, never a sniff.** blastula takes one `body` argument and dispatches on class: a bare string is plain text, `md()` tags Markdown, and `htmltools::HTML()` tags raw HTML.
No sniffing anywhere.
Python's keyword argument is the same tag one level up, with no wrapper types to import.
A `content=` argument that guessed the format was considered and rejected on `docs/research/prior-art.md`'s rule: every plain-text string is valid Markdown, so the guess is undecidable, and the failure is silent, `2 * 3 * 4` sent as emphasis.

**The renderer hook exists because of ordering.**
ADR-0003 rewrites `data:` images before the plain text is made, so megabytes of base64 never reach the text.
A caller rendering from their own HTML string gets the base64.
The hook is the one way to render from the rewritten HTML in a single construction.
It also keeps `html2text`'s licence with the caller who chose it.

## Rules

- **Exactly one of `html=` or `markdown=`, or neither.**
  Both is a `TypeError`.
  `text=` may accompany either, or stand alone.
  `Message()` with no content is a `TypeError`.
- **`text=` wins.**
  Supplied plain text ships verbatim.
  Epistole never checks it against the HTML, never merges, and never derives.
  `text=""` is a `ValueError`: an empty part is never what anyone means, and treating it as absent would make `""` and `None` synonyms.
- **Plain text from HTML is `text_renderer(rewritten_html)` when given, else `epistole.html_to_text(rewritten_html)`.**
  The renderer is `Callable[[str], str]`, runs once at construction, and is not stored on the value, so equality stays by content (ADR-0002).
  It receives the HTML after the `data:` rewrite (ADR-0003).
  Passing it with `text=` or with `markdown=` is a `TypeError`, because it would be silently ignored otherwise.
  An exception it raises propagates unwrapped at the line that built the message, and is not a `EpistoleError` (ADR-0004).
  A return that is not a `str`, or is `""`, is rejected the same way `text=` is.
- **Plain text from Markdown is the source, verbatim.**
  Raw HTML blocks in the source, which CommonMark allows, ship as written.
  The alternative is a sniff, rejected above.
- **Markdown renders through `epistole[markdown]` on `markdown-it-py`, `commonmark` preset, no options.**
  Absent, the constructor raises `ImportError` naming the extra, the pandas and httpx shape.
  Tables, footnotes, and `linkify` are not exposed in v1; a caller who needs them renders and passes `html=`.
  The rendered HTML runs the `data:` rewrite like any other HTML.
- **Plain text alone ships `text/plain` alone.**
  No `multipart/alternative`, no synthesized HTML.
  On Graph the body is `contentType: "text"`.
  An inline image on a text-only message has nothing to reference and degrades to a listed file (ADR-0003).
- **`epistole.html_to_text` is exported.**
  The default is visible, testable, and wrappable.
- **The extractor is best effort, pinned by fixtures.**
  It keeps links as `label <url>`, marks list items, keeps one table row per line, drops `<head>`, `<style>`, `<script>`, `<title>`, and comments, prints an image's alt text in brackets, decodes entities, and never raises on malformed HTML.
  The exact output is not a contract.
  It may improve in a minor version, and two messages built from the same HTML are equal within one version, not across versions.
  A caller who needs frozen bytes passes `text=`.
- **Readbacks are `.html` and `.text`, no underscore.**
  Constructor keywords claim no method name, so ADR-0007's suffix does not apply.
  `.text` is always a `str`.
  `.html` is `None` on a text-only message.
  There is no `.markdown`: the source is in `.text` unless `text=` replaced it, and the caller still holds their string, the reasoning ADR-0003 used for the original HTML.

## Considered options

- **Require `text` for a multipart message.**
  Cheapest and what every Python library does.
  Rejected because the audience never has a text twin, so the real outcome is HTML-only mail.
- **An extra for the extractor.**
  Rejected above: the absent branch needs a real extractor anyway.
- **`inscriptis` or `html2text` as a dependency.**
  Rejected on 22 MB plus an `lxml` upper bound, and on GPL, respectively.
  Both remain one `text_renderer=` away for a caller who wants them.
- **`content=` with format detection.**
  Rejected above; a guess at meaning with a silent failure.
- **`content=` plus tagged `Html()` and `Markdown()` wrapper types, blastula's shape literally.**
  Same explicitness as keywords at the cost of two exported types and a wrapper on the Quarto happy path.
- **A `markdown` helper returning HTML, `Message(html=md(src))`.**
  Loses the source by construction time, so the plain text would come from the extractor instead of the source.
- **Synthesize HTML for a text-only message, as blastula does.** blastula must, because its template is HTML.
  Epistole has no template, and the HTML would be a worse copy of text every client already renders.
- **Locking the extractor's output as a contract.**
  Rejected because an 87-line extractor should be free to get better, and the part is a fallback nobody diffs.

## Consequences

- Three ways in, one field each, and each field has one spelling, so ADR-0002's constructor rule survives with three keywords instead of one.
- The glossary gains *Content* and *Plain text*, and *Complete message* now reads "plain text present, and HTML present whenever the content entered as HTML or Markdown".
- `Message(...)` can raise `ImportError`, and the `html_to_text` extractor runs on every HTML construction.
- `MemoryBackend` tests read `outbox[0].text` on any entry and see what a text client sees.
- The first optional dependency that is not a backend, `epistole[markdown]`, lands with the implementation.
- [#21](https://github.com/ozanozbeker/epistole/issues/21) documents `markdown=` as the entry for hand-written mail and `html=` for rendered reports.
- The `data:` rewrite in ADR-0003 and the `cid:` check in ADR-0002 run only when HTML exists.

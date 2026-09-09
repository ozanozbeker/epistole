# A `data:` image becomes an inline image at construction

Herma promises to send caller-supplied HTML as written, and `Message(html=...)` edits it anyway.
Every `<img>` whose `src` is a `data:` URI is rewritten to a `cid:` reference, and the bytes become an inline image on the message.
No flag turns it off.
The content id Herma generates is a digest with no `@domain` part, against RFC 2045.
Decided on [#11](https://github.com/ozanozbeker/herma/issues/11), building on the prototype findings in [#8](https://github.com/ozanozbeker/herma/issues/8).

## Why

A `data:` image in a mail body has one reading, and it fails.
Gmail renders none of them on any platform (Can I Email, a community source; no vendor documents it either way).
Graph caps a write request at 4 MB with no path past it, so a report with one embedded chart gets `413`.
Rewriting is a choice of encoding, not a guess at meaning.
The warning in `docs/research/prior-art.md` is about strings that could mean two things.

The rewrite is lossless and visible.
The bytes still travel, `cid:` resolves on all three backends, and the rewritten HTML and the inline images it made are readable on the message before anything is sent.

A flag defaulting on buys nothing.
`cid:` is the mechanism every client was built for, and no client is known that renders `data:` but not `cid:`.
Adding a flag later is non-breaking.
Removing the rewrite later breaks every Gmail send.

The glossary had already decided.
*Complete message* required "every `data:` image already an attachment referenced by `cid:`" before this ADR existed, and a flag would have made the definition wrong.

The content id format is a compatibility surface, not an implementation detail.
blastula's source records why it omits the domain: "According to the spec there should be an @domain on this, but it makes attachment UI show up for Outlook.com (e.g. AT00001.bin)".
Anymail hit the same field from the other side and uses a fake `inline` domain, because Gmail blocks a Content-ID ending in `.com` when a provider reuses it as a filename.
No RFC records either bug.

## Rules

- **`<img src>` only, `image/*` only, both RFC 2397 payload forms.**
  Base64 and percent-encoded, because Pandoc emits SVG percent-encoded and blastula's base64-only regex was the recorded bug.
  Media type parameters are tolerated, and the declared type passes through unsniffed.
  A payload that does not decode raises at construction.
  A `data:` URI in CSS `url()`, in `srcset`, or with a non-image media type stays as written: `cid:` inside CSS has no reliable client support, and no inline image can stand in for a stylesheet or a font.
- **Byte-identical except the `src` values it rewrote.**
  Quotes, whitespace, entities, attribute order, and comments are untouched.
  Zero `data:` images means output identical to input.
  Located with `html.parser.HTMLParser` and spliced in place, never re-serialized, so no dependency and no drift.
  An `<img>` inside an HTML comment is not rewritten, including Outlook `<!--[if mso]>` blocks.
- **One inline image per distinct (media type, bytes).**
  A logo in the header and the footer travels once.
  This is not the `.attach(x).attach(x)` rule: that covers a caller action written twice, and here the caller wrote one image referenced twice.
- **Content id is `{sha256 hex, first 16}.{ext}`**, extension from `mimetypes.guess_extension`, none if unknown.
  Deterministic from content, so two messages built from the same HTML compare equal (ADR-0002), which rules out `make_msgid()` and uuid.
  The same string is the attachment filename, so MIME `filename=`, Graph `name`, and the `cid:` reference are one value.
  Stored bare; angle brackets are added only when a MIME header is written.
- **Rewrite runs before the plain-text renderer.**
  Both run in the constructor, and this order keeps megabytes of base64 out of the text.
- **Original HTML is not stored.**
  The caller still holds the string they passed and can diff.

## Considered options

- **A constructor flag, default on.**
  Rejected because neither default is safe, and "always" is the only answer under which the glossary's *Complete message* stays true.
- **Index-based ids, `img1.png`, as blastula does.**
  Readable, but the index shifts when an image is inserted earlier, and it can collide with a name a caller chose for an explicit inline image.
- **Also rewriting CSS `url(data:...)`.**
  Pandoc emits these for Bootstrap icons, tiny SVGs that render in no mail client either way.
  If [#19](https://github.com/ozanozbeker/herma/issues/19) inlines or strips CSS they vanish upstream.
- **Resolving local paths, `<img src="logo.png">`, as blastula also does.**
  Rejected because Herma reading a file named inside HTML, relative to some directory, is the working-directory guess `prior-art.md` warns about, and #8 killed `from_html_file` on the same ground.
- **Keeping the original HTML for preview, as blastula does.**
  Doubles a multi-MB body per message for a diff the caller can already make.

## Consequences

- `Message(...)` parses HTML and can raise on a malformed payload, at the line that supplied the HTML.
- The rewrite is not a bandwidth optimization.
  Python sends a base64-heavy HTML body as quoted-printable, and the measured difference on a 1 MiB image is 1.25 percent (1,434,975 bytes as `data:` against 1,417,302 as `cid:`).
  It buys rendering in Gmail and a Graph request under 4 MB, nothing else.
- A caller who wants a `data:` image on the wire cannot have one.
- The stdlib trap: `add_related(..., filename=, cid=)` writes `Content-Disposition: attachment` unless `disposition="inline"` is passed explicitly.
  The MIME builder must pass it.
- [#15](https://github.com/ozanozbeker/herma/issues/15) inherits the renderer order.
  [#21](https://github.com/ozanozbeker/herma/issues/21) tells authors: no `data:` images, use `cid:` and `.embed()`, and an `<img>` in a comment is not rewritten.

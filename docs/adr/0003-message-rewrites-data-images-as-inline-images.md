# `Message` rewrites a `data:` image as an inline image at construction

Epistole guarantees that it sends caller-supplied HTML as written.
`Message(html=...)` edits it anyway.
It rewrites every `<img>` whose `src` is a `data:` URI to a `cid:` reference.
The bytes become an inline image on the message.
No flag turns it off.
The content id Epistole generates is a digest with no `@domain` part, against RFC 2045.
Decided on [#11](https://github.com/ozanozbeker/epistole/issues/11), based on the prototype findings in [#8](https://github.com/ozanozbeker/epistole/issues/8).
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): the digest covers the media type as well as the bytes, so the content id is unique per dedupe key by construction.

## Why

A `data:` image in a mail body has one reading, and it fails.
Gmail renders none of them on any platform, according to Can I Email, a community source.
No vendor documents it either way.
Graph caps a write request at 4 MB with no path past it.
So Graph returns `413` for a report with one embedded chart.
Rewriting is a choice of encoding, not a guess at meaning.
The warning in `docs/research/prior-art.md` is about strings that could mean two things.

The rewrite is lossless and visible.
Epistole still sends the bytes.
`cid:` resolves on all three backends.
The rewritten HTML and the inline images it made are readable on the message before anything is sent.

A flag that defaults to on gives no benefit.
`cid:` is the mechanism every client was built for.
No known client renders `data:` but not `cid:`.
Adding a flag later is non-breaking.
Removing the rewrite later breaks every Gmail send.

The glossary already required the rewrite.
*Complete message* required "every `data:` image already an attachment referenced by `cid:`" before this ADR existed.
A flag would have made the definition wrong.

The content id format is a compatibility surface, not an implementation detail.
blastula's source records why it omits the domain: "According to the spec there should be an @domain on this, but it makes attachment UI show up for Outlook.com (e.g. AT00001.bin)".
Anymail found a bug in the same field, from the other side.
It uses a fake `inline` domain, because Gmail blocks a Content-ID ending in `.com` when a provider reuses it as a filename.
No RFC records either bug.

## Rules

- **The rewrite covers `<img src>` only, `image/*` only, and both RFC 2397 payload forms.**
  The forms are base64 and percent-encoded, because Pandoc emits SVG percent-encoded and blastula's base64-only regex was the recorded bug.
  The rewrite tolerates media type parameters.
  The declared type passes through unsniffed.
  The constructor raises on a payload that does not decode.
  A `data:` URI in CSS `url()`, in `srcset`, or with a non-image media type stays as written.
  `cid:` inside CSS has no reliable client support, and no inline image can replace a stylesheet or a font.
- **The output is byte-identical except the `src` values it rewrote.**
  The rewrite leaves quotes, whitespace, entities, attribute order, and comments untouched.
  Zero `data:` images means output identical to input.
  It locates each image with `html.parser.HTMLParser` and splices in place, never re-serializing.
  So it adds no dependency and no drift.
  The rewrite skips an `<img>` inside an HTML comment, including Outlook `<!--[if mso]>` blocks.
- **The rewrite makes one inline image per distinct (media type, bytes).**
  A logo in the header and the footer is sent once.
  This is not the `.attach(x).attach(x)` rule.
  That rule covers a caller action written twice.
  Here the caller wrote one image referenced twice.
- **The content id is `{sha256 hex, first 16}.{ext}`.**
  The digest covers the media type, a `NUL` byte, and the payload.
  The extension comes from `mimetypes.guess_extension`, and the id has none if it is unknown.
  The id is deterministic from content, so two messages built from the same HTML compare equal (ADR-0002).
  That rules out `make_msgid()` and uuid.
  Hashing the media type alongside the bytes keeps the id unique per dedupe key.
  Without it, `image/jpeg` and `image/pjpeg` over identical bytes share an extension and a digest, so one message holds two inline images under one id.
  The same string is the attachment filename, so MIME `filename=`, Graph `name`, and the `cid:` reference are one value.
  Epistole stores it bare.
  It adds angle brackets only when it writes a MIME header.
- **Rewrite runs before the plain-text renderer.**
  Both run in the constructor.
  This order keeps megabytes of base64 out of the text.
- **Original HTML is not stored.**
  The caller still holds the string they passed, so they can diff.

## Considered options

- **Add a constructor flag, default on.**
  Rejected because neither default is safe.
  Only "always" keeps the glossary's *Complete message* true.
- **Use index-based ids, `img1.png`, as blastula does.**
  They are readable, but the index shifts when the caller inserts an image earlier.
  An index can also collide with a name a caller chose for an explicit inline image.
- **Also rewrite CSS `url(data:...)`.**
  Pandoc emits these for Bootstrap icons, tiny SVGs that render in no mail client either way.
  If [#19](https://github.com/ozanozbeker/epistole/issues/19) inlines or strips CSS, an earlier step removes them.
- **Resolve local paths, `<img src="logo.png">`, as blastula also does.**
  Rejected because it makes Epistole read a file that the HTML names relative to some directory.
  That is the working-directory guess `prior-art.md` warns about.
  #8 removed `from_html_file` for the same reason.
- **Keep the original HTML for preview, as blastula does.**
  It doubles a multi-MB body per message for a diff the caller can already make.

## Consequences

- `Message(...)` parses HTML and can raise on a malformed payload, at the line that supplied the HTML.
- The rewrite is not a bandwidth optimization.
  Python sends a base64-heavy HTML body as quoted-printable.
  The measured difference on a 1 MiB image is 1.25 percent (1,434,975 bytes as `data:` against 1,417,302 as `cid:`).
  Its only gains are rendering in Gmail and a Graph request under 4 MB.
- A caller who wants to send a `data:` image cannot.
- A stdlib default is easy to miss: `add_related(..., filename=, cid=)` writes `Content-Disposition: attachment` unless the caller passes `disposition="inline"` explicitly.
  The MIME builder must pass it.
- [#15](https://github.com/ozanozbeker/epistole/issues/15) takes the renderer order as given.
  [#21](https://github.com/ozanozbeker/epistole/issues/21) documents this for authors: no `data:` images, use `cid:` and `.embed()`, and an `<img>` in a comment is not rewritten.

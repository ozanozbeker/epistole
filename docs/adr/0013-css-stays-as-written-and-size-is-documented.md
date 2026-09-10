# The caller's CSS stays as written, and size is documented rather than warned

Epistole never rewrites the caller's CSS onto elements.
There is no `css-inline` dependency and no `epistole[css]` extra.
It emits no warning when the HTML is large enough that Gmail will clip it.
The HTML authoring guide on [#21](https://github.com/ozanozbeker/epistole/issues/21) names the ceiling, labels where the number came from, and carries a recipe the caller runs themselves.
Decided on [#25](https://github.com/ozanozbeker/epistole/issues/25), grounded by `docs/research/css-in-an-html-body.md`.

## Why

**Rewriting is lossy in a way Epistole cannot report.**
`css-inline` drops every `:hover` rule, and by default every `@media` block, because neither can become a `style` attribute.
Measured on 0.21.2: `keep_at_rules=True` saves the at-rules and does not save the pseudo-classes, and the README does not say so.
The caller's responsive layout would disappear with no signal.
ADR-0003 accepted an edit to caller HTML only because that edit is lossless and inspectable: the bytes still travel, and the rewritten HTML and the inline images it made are readable on the message before anything is sent.
A CSS rewrite has neither property.

**It raises on the input that motivated the question.**
A Quarto document rendered with `embed-resources: true` carries its stylesheets as `<link href="data:text/css,...">`, because Pandoc leaves a `<link>` alone when the CSS contains `</` (`src/Text/Pandoc/SelfContained.hs`, the `TagOpen "link"` case).
`css_inline.inline()` resolves that `href` as a filesystem path and raises `InlineError: File name too long (os error 63)`.
Owning the rewrite would mean stripping those tags first, discarding 650 KB of the caller's CSS before anything else happens.

**Size moves both ways by roughly an order of magnitude.**
A 1,188,695-byte Quarto report inlines to 195,706 bytes, a 6.1x shrink, because almost all of the Bootstrap it ships matches nothing.
A 292,714-byte table whose cells all match one nine-property rule inlines to 2,362,519 bytes, an 8.1x growth.
A styled data table is exactly what a report emailed from Python contains.
Epistole cannot tell the caller in advance which way it will go, and a step that runs automatically should not have that spread.

**The premise the question was written on was wrong.**
[#19](https://github.com/ozanozbeker/epistole/issues/19) held that Outlook's Word engine ignores a `<head>` stylesheet at any size.
It does not.
Community testing records Outlook Windows 2007 through 2019 as partial support, with the caveat that rules must precede the elements they style.
Apple Mail, Outlook.com, Outlook macOS, Yahoo, Thunderbird and ProtonMail all record full or partial support.
The one outright hole is Gmail mobile webmail.
So rewriting would move properties that already work into a place where they still work, and it would not rescue `@media` or `:hover`, which fail in the same clients that ignore the stylesheet.

**No CSS strategy fixes the email that is actually broken.**
The measured report is 11.6x Gmail's clip threshold.
After a perfect rewrite it is 195,706 bytes, still 1.9x over, because 155,053 of them are `<script>`.
Strip the scripts and rewrite the CSS and it is 3,212 bytes.
The script half matters more than the CSS half, and neither is Epistole's to do.

**No warning, on its own terms.**
ADR-0004 and ADR-0010 both refused a warning, each time as a downgrade of a known error.
Clipping is not that shape: nothing goes wrong, the service accepts the message, and it arrives.
So the precedent does not decide this, and the refusal stands on the number instead.
Google documents no threshold.
The 102,400-byte figure is vendor documentation, and [hteumeuleu/email-bugs#41](https://github.com/hteumeuleu/email-bugs/issues/41) collects reports of clipping below it.
A warning would spend a permanent third channel, its own filterable class, and a release-versioned constant on a prediction about a third party's undocumented behaviour that Epistole cannot verify and Google can change without telling anyone.
The cost of the refusal is real and is recorded below.

**The backend was never the right axis.**
#25 raised that `Message(...)` knows the HTML but not the backend.
Knowing the backend would not have helped.
Clipping is recipient-side, and Gmail receives mail from every backend, so a check that fired only on the Gmail backend would miss the Gmail recipient reached over SMTP.
Keying on `@gmail.com` in the recipients is worse, because Workspace domains are not `@gmail.com`, so it would be confidently silent on the corporate case.

**The seam is a sentence, because the ordering argument does not repeat.**
ADR-0008 gave `text_renderer=` its surface on ordering: without it, a caller rendering from their own HTML string gets the base64 that ADR-0003's rewrite would have removed, and it ships inside the plain-text part recipients read.
An `html_renderer=` fails the same test.
ADR-0003 rewrites `<img src>` only and leaves a `data:` URI with a non-image media type as written, so the `<link href="data:text/css,...">` that raises survives the rewrite, and running after it avoids nothing.
`css-inline` does not read an `<img src>` data URI as a stylesheet, so nothing is corrupted by running before it either.
The hook would save the inliner from parsing base64 it did not need, which measured 2 to 9 ms on documents between 0.3 and 1.2 MB.
It would also introduce a question that does not exist today: whether the plain text comes from the rewritten HTML or the inlined HTML.

## Rules

- **Epistole never rewrites the caller's CSS.**
  No `css-inline` dependency, no `epistole[css]` extra, no constructor argument, no flag.
  The only edit `Message(html=...)` makes to caller HTML is the `<img src>` rewrite in ADR-0003.
- **No warning at any size.**
  Epistole has two channels, raise and return, and neither carries this.
  A caller mistake before the wire is a `TypeError` or `ValueError` and a backend-local limit is `RejectedError` (ADR-0004); an oversized body is neither, because every backend accepts it.
- **`Inline` is reserved.**
  In Epistole's documentation, code, and glossary, *inline* names the `cid:` mechanism of an inline image.
  The CSS operation is *rewriting CSS onto elements*, and `css-inline` is named as a package.
  Bare "inline the CSS" is not written.
- **The guide names the numbers and labels their source.**
  Roughly 102,400 bytes for Gmail clipping, sourced to vendor documentation rather than to Google, with `email-bugs#41`'s contrary reports noted.
  16 KB for the Gmail desktop webmail `<style>` cap, sourced to community testing.
  The superseded 8192 figure is not repeated.
- **The recipe covers scripts, not only CSS.**
  `Message(html=css_inline.inline(html))`, the `<link href="data:text/css">` caveat that makes it raise on a Quarto report, and the measurement showing scripts are the larger half.

## Considered options

- **Depend on `css-inline` and rewrite by default.**
  Rejected above.
  The package itself is not the problem: MIT, no runtime dependencies, 3.70 MB installed, one `abi3` wheel per platform, seven releases in the last twelve months.
- **An `epistole[css]` extra.**
  Fails the missing-extra test [#7](https://github.com/ozanozbeker/epistole/issues/7) applied to the text extractor.
  "Rewrote the CSS" and "did not" are visibly different emails, so a library must not choose between them on what happens to be installed.
- **`premailer`, `toronado`, or `emails[html]`.**
  Five runtime dependencies including 19 MB of `lxml`; dead since 2020; and a chain back to premailer, respectively.
  `emails` also deletes every `<style>` tag after inlining, accepting the loss by design, which suits a marketing-email library and not this one.
- **`html_renderer=`, symmetric with `text_renderer=`.**
  Rejected above; the ordering argument that earned `text_renderer=` its surface does not repeat.
- **Warn at 102,400 bytes.**
  What `docs/research/css-in-an-html-body.md` recommends.
  Rejected above.
  The research is not corrected on its facts, only on this call.
- **Export `GMAIL_CLIP_BYTES`.**
  Public API owed a deprecation cycle, for a number Epistole never reads and does not control.
  It also helps only a caller who already knows clipping exists, which is the caller who did not need it.
- **Warn on the presence of a `<style>` block.**
  Noise on correct input, since most recipients honour it.

## Consequences

- A caller who sends a 1.19 MB report gets no signal from Epistole, and the recipient on Gmail sees "View entire message".
  The guide is the only mitigation, and it reaches only the caller who reads it.
- The `<link href="data:text/css">` caveat has to appear wherever the recipe appears, or the first Quarto user to follow it hits `InlineError`.
- #21 can now write its two deferred bullets, "Keep the CSS small" and "Watch the body size".
- A post-v1 composition surface is not foreclosed.
  blastula authors CSS rather than rewriting it: `blastula_template()` writes a `<head>` `<style>` block containing an `@media` query, and `block_text()` and `add_cta_button()` write `style` attributes through `htmltools::css()`.
  Composing would mean Epistole owns CSS it wrote, which this ADR does not speak to.
  It does reopen [#8](https://github.com/ozanozbeker/epistole/issues/8)'s "Epistole never composes HTML", restated in ADR-0008, and that is where the argument belongs.
- `CONTEXT.md`'s *Inline image* entry gains the sentence reserving the word.

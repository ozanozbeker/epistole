# The caller's CSS stays as written, and Epistole documents size limits instead of warning about them

Epistole never rewrites the caller's CSS onto elements.
There is no `css-inline` dependency and no `epistole[css]` extra.
It emits no warning when the HTML is large enough that Gmail will clip it.
The HTML authoring guide on [#21](https://github.com/ozanozbeker/epistole/issues/21) names the limit and labels where the number came from.
It includes a recipe the caller runs themselves.
Decided on [#25](https://github.com/ozanozbeker/epistole/issues/25), based on `docs/research/css-in-an-html-body.md`.

## Why

**Rewriting is lossy in a way Epistole cannot report.**
`css-inline` drops every `:hover` rule, and by default every `@media` block, because neither can become a `style` attribute.
Measured on 0.21.2, `keep_at_rules=True` keeps the at-rules but not the pseudo-classes.
The README does not say so.
The caller's responsive layout would disappear with no signal.
ADR-0003 accepted an edit to caller HTML only because that edit is lossless and inspectable.
It is lossless because Epistole still sends the bytes.
It is inspectable because the rewritten HTML and the inline images the rewrite made are readable on the message before anything is sent.
A CSS rewrite has neither property.

**It raises on the input that motivated the question.**
A Quarto document rendered with `embed-resources: true` holds its stylesheets as `<link href="data:text/css,...">`.
Pandoc keeps a `<link>` as written when the CSS contains `</` (`src/Text/Pandoc/SelfContained.hs`, the `TagOpen "link"` case).
`css_inline.inline()` resolves that `href` as a filesystem path and raises `InlineError: File name too long (os error 63)`.
Owning the rewrite would mean stripping those tags first, discarding 650 KB of the caller's CSS before anything else happens.

**Rewriting changes size in both directions by roughly an order of magnitude.**
Rewriting a 1,188,695-byte Quarto report gives 195,706 bytes, a 6.1x shrink, because almost none of the Bootstrap it includes matches an element.
Rewriting a 292,714-byte table whose cells all match one nine-property rule gives 2,362,519 bytes, an 8.1x growth.
A report sent from Python contains exactly this kind of styled data table.
Epistole cannot report in advance which way the size will move.
A step that runs automatically should not have that spread.

**The premise the question was written on was wrong.**
[#19](https://github.com/ozanozbeker/epistole/issues/19) held that Outlook's Word engine ignores a `<head>` stylesheet at any size.
It does not.
Community testing records Outlook Windows 2007 through 2019 as partial support, with the caveat that rules must precede the elements they style.
Apple Mail, Outlook.com, Outlook macOS, Yahoo, Thunderbird and ProtonMail all show full or partial support.
The one client with no support is Gmail mobile webmail.
So rewriting would move properties that already work into a place where they still work.
It would not make `@media` or `:hover` work either, because they fail in the same clients that ignore the stylesheet.

**No CSS strategy fixes the message that is actually broken.**
The measured report is 11.6x Gmail's clip threshold.
After a perfect rewrite it is 195,706 bytes, still 1.9x over, because 155,053 of them are `<script>`.
With the scripts stripped and the CSS rewritten, it is 3,212 bytes.
The script half matters more than the CSS half.
Neither is Epistole's job.

**The case against a warning does not rely on precedent.**
ADR-0004 and ADR-0010 both rejected a warning, each time as a downgrade of a known error.
Clipping is a different case.
Nothing goes wrong: the service accepts the message and delivers it.
So the precedent does not settle this case, and the decision depends on the number instead.
Google documents no threshold.
The 102,400-byte figure comes from vendor documentation.
[hteumeuleu/email-bugs#41](https://github.com/hteumeuleu/email-bugs/issues/41) collects reports of clipping below it.
A warning would need a permanent third channel, its own filterable class, and a release-versioned constant.
All three would exist for a prediction about a third party's undocumented behaviour.
Epistole cannot verify that behaviour, and Google can change it without telling anyone.
The cost of this decision is real and is recorded below.

**The choice of backend was never the right basis.**
#25 raised that `Message(...)` has the HTML but not the backend.
Having the backend would not have helped.
Clipping happens on the recipient's side.
Gmail receives messages from every backend, so a check that ran only on the Gmail backend would miss the Gmail recipient reached over SMTP.
Matching on `@gmail.com` in the recipients is worse, because Workspace domains are not `@gmail.com`.
So it would miss the corporate case without any sign.

**The guide's recipe replaces a hook, because the ordering argument does not apply again.**
ADR-0008 justified `text_renderer=` on ordering.
Without it, a caller rendering from their own HTML string gets the base64 that ADR-0003's rewrite would have removed.
That base64 then ships inside the plain text recipients read.
An `html_renderer=` fails the same test.
ADR-0003 rewrites `<img src>` only and leaves a `data:` URI with a non-image media type as written.
So the rewrite keeps the `<link href="data:text/css,...">` that raises, and running the CSS rewrite after it avoids nothing.
`css-inline` does not read an `<img src>` data URI as a stylesheet, so running before it corrupts nothing either.
The hook would stop the CSS rewriter from parsing base64 it did not need.
That parsing measured 2 to 9 ms on documents between 0.3 and 1.2 MB.
The hook would also introduce a question that does not exist today: whether the plain text comes from the HTML after the image rewrite or after the CSS rewrite.

## Rules

- **Epistole never rewrites the caller's CSS.**
  There is no `css-inline` dependency, no `epistole[css]` extra, no constructor argument, and no flag.
  The only edit `Message(html=...)` makes to caller HTML is the `<img src>` rewrite in ADR-0003.
- **Epistole emits no warning at any size.**
  Epistole has two channels, raise and return.
  Neither carries this.
  A caller mistake found before writing is a `TypeError` or `ValueError`.
  A backend-local limit is `RejectedError` (ADR-0004).
  Oversized HTML is neither, because every backend accepts it.
- **`Inline` is reserved.**
  In Epistole's documentation, code, and glossary, *inline* names the `cid:` mechanism of an inline image.
  The CSS operation is *rewriting CSS onto elements*.
  `css-inline` is named as a package.
  Bare "inline the CSS" is not written.
- **The guide names the numbers and labels their source.**
  It gives roughly 102,400 bytes for Gmail clipping and sources that to vendor documentation rather than to Google.
  It notes `email-bugs#41`'s contrary reports.
  It gives 16 KB for the Gmail desktop webmail `<style>` cap and sources that to community testing.
  The superseded 8192 figure is not repeated.
- **The recipe covers scripts, not only CSS.**
  It includes `Message(html=css_inline.inline(html))`, the caveat about `<link href="data:text/css">` that makes it raise on a Quarto report, and the measurement showing scripts are the larger half.

## Considered options

- **Depend on `css-inline` and rewrite by default.**
  Rejected above.
  The package itself is not the problem: MIT, no runtime dependencies, 3.70 MB installed, one `abi3` wheel per platform, seven releases in the last twelve months.
- **Offer an `epistole[css]` extra.**
  It fails the missing-extra test [#7](https://github.com/ozanozbeker/epistole/issues/7) applied to the text extractor.
  "Rewrote the CSS" and "did not" produce visibly different messages.
  So the choice between them must not depend on what happens to be installed.
- **Use `premailer`, `toronado`, or `emails[html]`.**
  The first has five runtime dependencies, including 19 MB of `lxml`.
  The second has been unmaintained since 2020.
  The third depends on premailer through a chain of dependencies.
  `emails` also deletes every `<style>` tag after rewriting the CSS.
  That loss is by design, which suits a marketing-email library and not this one.
- **Add `html_renderer=`, symmetric with `text_renderer=`.**
  Rejected above.
  The ordering argument that justified `text_renderer=` does not apply again.
- **Warn at 102,400 bytes.**
  `docs/research/css-in-an-html-body.md` recommends it.
  Rejected above.
  The research is not corrected on its facts, only on this decision.
- **Export `GMAIL_CLIP_BYTES`.**
  It would be public API that needs a deprecation cycle to change.
  Epistole never reads that number and does not control it.
  It also helps only a caller who already knows clipping exists, and that caller does not need it.
- **Warn on the presence of a `<style>` block.**
  It is noise on correct input, since most recipients' clients apply the block.

## Consequences

- A caller who sends a 1.19 MB report gets no signal from Epistole.
  The recipient on Gmail sees "View entire message".
  The guide is the only mitigation.
  It helps only the caller who reads it.
- The `<link href="data:text/css">` caveat has to appear wherever the recipe appears.
  Otherwise the first Quarto user to follow it gets `InlineError`.
- The guide on #21 can now include its two deferred bullets, "Keep the CSS small" and "Watch the body size".
- A post-v1 composition surface is still possible.
  blastula authors CSS rather than rewriting it.
  `blastula_template()` writes a `<head>` `<style>` block containing an `@media` query.
  `block_text()` and `add_cta_button()` write `style` attributes through `htmltools::css()`.
  Composing would mean Epistole owns CSS it wrote, which this ADR does not cover.
  Composing would reopen [#8](https://github.com/ozanozbeker/epistole/issues/8)'s "Epistole never composes HTML", restated in ADR-0008.
  That argument belongs there.
- The sentence reserving the word goes into `CONTEXT.md`'s *Inline image* entry.

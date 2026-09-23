# CSS in an HTML body

This note records research for [issue #19](https://github.com/ozanozbeker/epistole/issues/19).
It uses primary sources only.
Every factual claim below has a URL.
Where a claim comes from a live probe or a local run rather than a document, the text says so.

I did the local runs on 2026-09-09.
They used macOS arm64, a CPython 3.14.7 free-threading build, `uv` 0.12.10, Quarto 1.10.18 and Pandoc 3.11.

## What this means for Epistole's design

Epistole did not adopt the size warning this note recommends.
[ADR-0013](../adr/0013-css-stays-as-written-and-size-is-documented.md) adopted the rest and says nothing about size.

Do not inline.
Warn about size, not about CSS.
Document the limitation with a one-line recipe the caller can run themselves.

Four measurements support that.
Two of them contradict the framing in #19.

**First, `css_inline.inline()` raises on the exact input that motivated this ticket.**
A Quarto document rendered with `embed-resources: true` includes its stylesheets as `<link href="data:text/css,...">`.
`css-inline` resolves a `<link href>` as a path.
A percent-encoded 650 KB `data:` URI is not a path.
Measured locally on a freshly rendered report: `css_inline.inline(html)` with default options raises `InlineError: File name too long (os error 63)`.
On a short `data:text/css` URI it raises `InlineError: Missing stylesheet file: data:text/css,p%7Bcolor%3Ared%7D`.
So Epistole could not just call `inline()`.
It would have to strip the `<link>` tags first.
That would silently discard 650 KB of the caller's authored CSS before any other step.

**Second, inlining changes size in both directions, by roughly an order of magnitude either way.**
On the report described below, I measured 1,188,695 bytes in and 195,706 bytes out: a 6.1x shrink.
It shrinks because css-inline drops every rule whose selector matches nothing, and a Quarto report includes almost all of Bootstrap unused.
On a synthetic worst case, I measured 292,714 bytes in and 2,362,519 bytes out: an 8.1x growth.
The worst case is a 2,000-row table whose cells all match one nine-property rule.
The caller cannot know in advance which direction they will get.
That is a bad property for a step that runs automatically.

**Third, recipient support for a `<head>` stylesheet is much better than #19 assumed.**
The claim in #19 that "Outlook's Word rendering engine will not render a `<head>` stylesheet at any size" is wrong.
Community testing records Outlook on Windows 2007 through 2019 as partial support for the `<style>` element, not as no support ([Can I Email, `<style>` element](https://www.caniemail.com/features/html-style/), community-maintained).
The caveat is that the rules must be declared before the elements that use them.
The same source records full or partial support for Apple Mail, Outlook.com, Outlook for macOS, Yahoo, Thunderbird and Gmail desktop webmail.
The only client it records as no support is Gmail mobile webmail, since 2020-02.

**Fourth, inlining does not solve the actual problem: size.**
Gmail clips a message over roughly 102 KB and hides the rest behind a "View entire message" link.
The measured report is 1,188,695 bytes, about 11.6x that threshold.
It is still 195,706 bytes after inlining, because 155,053 of those bytes are `<script>` that css-inline does not change.
No CSS strategy fixes a message that is ten times too big.

So Epistole should state plainly that it does not own the caller's CSS.

Concretely, this means:

- Add no `epistole[css]` extra and no `css-inline` dependency.
  Under #7's test, such an extra fails on the missing-extra branch.
  There is no acceptable fallback, because "inline the CSS" and "do not inline the CSS" produce visibly different messages.
  A library must not silently change its output based on what happens to be installed.
- Issue one warning at `Message(...)` construction when the assembled HTML exceeds 102,400 bytes.
  That is the only threshold in this whole area with a consistent published figure and an exact, fast check.
  It also stays valid whatever the caller does about CSS.
- Do not warn when a `<style>` block is present.
  Most mail clients apply it, so that warning would trigger on correct input.
- Document the recipe `Message(html=css_inline.inline(html))`, with the `<link href="data:text/css">` caveat spelled out.
  A caller who wants inlining then opts in with their own dependency and their own licence review.
  This matches the `text_renderer=` seam settled in #15.

This also keeps the guarantee from ADR-0003 and #11: the HTML Epistole sends is byte-identical to what the caller passed, except for rewritten `src` values.
Inlining rewrites every element in the document.
Epistole should not make that rewrite without the caller's knowledge.

## Recipient-side support

The constraint is recipient-side, so it applies whichever backend sent the message.

### Gmail: documented, no stated limit

Google's own [CSS Support](https://developers.google.com/workspace/gmail/design/css) page states: "You can style email sent to Gmail using inline `<style>` blocks and standard CSS.
Most CSS selectors, attributes, and media-queries are supported.
Unsupported CSS properties and selectors may be ignored by Gmail."
Both worked examples on that page put the `<style>` element inside `<head>`.

The page states "Gmail supports class, element, and id selectors".
It documents media queries against screen width, orientation and resolution.
It lists several hundred supported properties.

The page states no size limit.
I fetched and searched it on 2026-09-09.
The words "limit", "KB", "byte", "8192" and "16384" do not appear anywhere in the article body.

I could find no Google source for the widely repeated 8192 figure.
I do not believe one exists.
The figure comes from community testing, not documentation.
The issue [hteumeuleu/email-bugs#90](https://github.com/hteumeuleu/email-bugs/issues/90) records two tests.
One spreads 1,024 declarations across several `<style>` tags.
The other uses 1,024 separate `<style>` tags.
Both show a 16 KB cap.
The issue notes that Gmail keeps the rules before the limit and drops everything after.
That issue itself cites a 2017 observation of 8192 bytes.
It says the figure was "recently updated to 16384 bytes according to Eric Lepetit on the Emailgeeks Slack".
[Can I Email](https://www.caniemail.com/features/html-style/) (community-maintained) lists the 16 KB figure as note 6 on Gmail desktop webmail from 2023-01.
That note links to the same issue.
So if Epistole quotes a number, it should quote 16 KB.
It should source that figure to community testing and label it as such.
The 8192 figure is a superseded community measurement that later sources copied.

### Outlook: first-party documentation exists, and it is from 2006

Microsoft's [Word 2007 HTML and CSS Rendering Capabilities in Outlook 2007](https://learn.microsoft.com/en-us/previous-versions/office/developer/office-2007/aa338201(v=office.12)) is the only first-party document on this.
It is archived and marked `ms.date: 2014-07-09`.
Microsoft wrote it in August 2006.
It states plainly: "Microsoft Office Outlook 2007 uses the HTML parsing and rendering engine from Microsoft Office Word 2007 to display HTML message bodies.
The same HTML and cascading style sheets (CSS) support available in Word 2007 is available in Outlook 2007."

The document actually says the following:

- Word 2007 supports "a subset of the standard HTML 4.01 specification and of the Internet Explorer 6.0 HTML specification" and "a subset of the standard Cascading Stylesheet Specification, Level 1".
- The supported HTML elements table lists the `<style>` element, with attributes `dir`, `lang` and `type`.
  Its "Cascading Style Sheet Style Support Level" column reads `None`.
  But that column describes which properties apply to the element itself, not whether Outlook applies the stylesheet.
  On a careful reading, this document does not say that Outlook ignores a `<head>` stylesheet.
- CSS support is tiered.
  `SPAN` gets CORE.
  `DIV` and `P` get COREEXTENDED.
  Most other elements get FULL.
  CORE has 28 properties and does not include `width`, `height` or `padding`.
- The document lists the `media` attribute as unsupported.
- The document lists `position`, `float`, `max-width`, `min-width`, `overflow`, `visibility`, `z-index`, `background-image`, `background-position` and `background-repeat` as unsupported against CSS 2.1.
- The document contradicts itself on `display`: it appears in the CORE supported list and in both unsupported lists.

Everything after Outlook 2007 comes from the community.
Microsoft has published nothing equivalent for 2010, 2013, 2016, 2019 or the new Outlook.
Searching learn.microsoft.com returns only Q&A threads, which are user-to-user posts, not documentation.

In community testing, Can I Email records Outlook Windows 2007 through 2019 as partial `<style>` support, with the ordering caveat.
It records **no** `@media` support and **no** `:hover` support.
That matters here, because css-inline cannot inline those same rules either.
On Outlook Windows, inlining adds nothing that a `<head>` stylesheet does not already provide.

### Apple Mail: no first-party statement

I could not find one.
Apple's developer documentation covers [MailKit](https://developer.apple.com/documentation/mailkit) extensions and the archived [Mail Stationery release notes](https://developer.apple.com/library/archive/releasenotes/AppleApplications/MailStationeryRelNote/index.html).
Neither documents CSS support for received messages.
The stationery notes only warn that email clients "are often much less capable than most web browsers".
Community testing records Apple Mail on macOS and iOS as full `<style>` support back to 10.3.

### Support table

All rows below come from [Can I Email](https://www.caniemail.com/), which is **community-maintained**, not first-party.
I pulled the data from `https://www.caniemail.com/api/data.json` on 2026-09-09.
`y` means supported, `a` partial, and `n` not supported.

| Client | `<style>` element | `@media` | `:hover` |
| --- | --- | --- | --- |
| Gmail desktop webmail | `a`, not inside `<body>`, capped at 16 KB | `a`, no height queries | `y` |
| Gmail mobile webmail | `n` | `n` | `n` |
| Gmail iOS / Android app | `a`, not inside `<body>`, not for non-Google accounts | `a` | `n` / `a` |
| Outlook Windows 2007-2019 | `a`, rules must precede their elements | `n` | `n` |
| Outlook.com | `y` | `a` | `a`, type selectors only |
| Outlook macOS 16.80 | `y` | `a` | `a`, type selectors only |
| Apple Mail macOS / iOS | `y` | `y` | `y` |
| Yahoo desktop / iOS | `y` | `a`, limited query set | `y` |
| Thunderbird | `y` | `n` | `y` |
| ProtonMail desktop | `y` | `a` | `y` |

`@media` and `:hover` fail in the same clients where a `<head>` stylesheet fails.
By default, css-inline drops both (measured below).
Inlining moves the properties that already work into a place where they still work.
It does not make the others work.

## Provider-side size limits

Gmail clips a message and hides the rest behind a "View entire message" link.

Google **does not document** the threshold.
I searched Gmail Help and the Workspace admin help.
The only size limit Google publishes is the 25 MB attachment cap, which is a different thing.
The best available source is vendor documentation.
Mailchimp states "Gmail clips emails that have a message size larger than 102KB, and hides the full content behind a 'View entire message' link".
It adds that the size counts "your text, the URLs and tracking code for links, the HTML used to style your content, and more" ([Mailchimp help](https://mailchimp.com/help/gmail-is-clipping-my-email/)).
Its trust level is vendor documentation.
The figure is consistent across ESPs.
Google has not confirmed it.

The community record acknowledges the uncertainty.
The issue [hteumeuleu/email-bugs#41](https://github.com/hteumeuleu/email-bugs/issues/41), opened 2018-05-17, says of the 102 kB figure that "no one seems to know where this number comes from".
It also collects reports of clipping below that figure.

Treat 102,400 bytes as a soft threshold and warn rather than raise.
The evidence supports only that.

## What Quarto and Pandoc actually do

### Pandoc leaves a stylesheet as a `<link>` when it contains `</`

I confirmed this from the source.
The check is in [`src/Text/Pandoc/SelfContained.hs`](https://github.com/jgm/pandoc/blob/main/src/Text/Pandoc/SelfContained.hs), in the `TagOpen "link"` case, at line 132 at the time of reading:

```haskell
Fetched (mime, bs)
  | ("text/css" `T.isPrefixOf` mime ||
      fromAttrib "rel" t == "stylesheet")
    && T.null (fromAttrib "media" t)
    && not ("</" `B.isInfixOf` bs) -> do
```

All three conditions must hold before Pandoc promotes the `<link>` into an inline `<style>` element.
Otherwise it falls through to the `otherwise` branch.
That branch rewrites `href` to a `data:` URI and keeps the `<link>`.

The `</` guard has no comment.
The nearby `-- see #5725` comment refers to the `type` attribute on the emitted `<style>` tag, not to this check.
The reason is inferable rather than documented.
The HTML tokenizer ends a `<style>` element at the first `</style`.
Pandoc's guard is the conservative version of that: it skips promotion on any `</` at all.
Modern CSS triggers it easily, for instance through `content: "</div>"` or an escaped sequence inside a `url()`.
The same guard exists for scripts one case up.
There it checks only for `"</script"`.

The `media` condition matters too and is easy to miss.
A `<link media="print">` also stays a `<link>`, whatever its contents.

Pandoc's manual documents `--embed-resources` as "Produce a standalone HTML file with no external dependencies, using `data:` URIs to incorporate the contents of linked scripts, stylesheets, images, and videos" ([Pandoc manual](https://pandoc.org/MANUAL.html)).
It documents `--self-contained` as a "Deprecated synonym for `--embed-resources --standalone`".
Nothing in the manual mentions inlining CSS into `style` attributes.

### Neither Quarto nor Pandoc inlines CSS for HTML output

I checked this three ways.

Pandoc's manual has no such option.
Grepping the Pandoc HTML writer and `SelfContained.hs` finds no per-element style rewriting.
`SelfContained.hs` only rewrites `src` and `href` attributes and promotes `<link>` to `<style>`.

Quarto **does ship a CSS inliner**.
It looks like a counterexample, but it is not one.
`/Applications/quarto/share/scripts/juice.ts` is a four-line Deno wrapper around the npm `juice` package.
It has exactly one caller: a local function `juice()` in `/Applications/quarto/share/filters/main.lua` at line 9797 (and its copy in `crossref.lua`).
At both call sites, lines 9860 and 9967, the guard is `if(_quarto.format.isTypstOutput())`.
Quarto only inlines CSS when it flattens a raw HTML table for **Typst** output, which cannot include a stylesheet.
Quarto never calls it for HTML output.
The Lua source also records a limitation: "juice truncates around 15k characters; let's guard any over 2000 characters".
So Quarto swaps long `data:image` URIs for a UUID before the call and swaps them back after.

Quarto's `email` format exists for Posit Connect.
`/Applications/quarto/share/schema/document-email.yml` defines `email-version` 1 and 2.
Quarto implements the format inside the compiled binary, so I could not read what it does with CSS.
It is a Connect integration, not a general-purpose email body.
So it does not change the answer for Epistole.

### What one small Quarto report actually weighs

I measured this locally.
I wrote a 30-line `.qmd` with a heading, a three-row Markdown table, a callout, a list and one Python code block.
Then I ran `quarto render report.qmd --to html` with `embed-resources: true`.

| Component | Chars |
| --- | --- |
| Whole document | 1,188,688 |
| `<style>` blocks, 3 of them | 342,705 |
| `<link href="data:text/css,...">` tags, 2 of them | 650,344 |
| `<script>` blocks, 8 of them | 155,053 |
| Machine-generated `style="..."` attributes | 0 |

That is 993,049 characters of CSS for a document whose actual prose is under 400 characters.
The proportions match #19's measurement on a real report.
The absolute numbers differ because the documents differ.
Both documents are mine.
I measured both.

As the last row shows, neither Quarto nor Pandoc emits a single `style` attribute.

## `css-inline`

See [PyPI](https://pypi.org/project/css-inline/) and the [repository](https://github.com/Stranger6667/css-inline).

### Provenance

| Field | Value | Source |
| --- | --- | --- |
| Latest | 0.21.2, uploaded 2026-08-24 | PyPI JSON API |
| Licence | MIT | PyPI trove classifier, repo licence |
| Author | Dmitry Dygalo | PyPI metadata |
| `requires-python` | `>=3.10` | PyPI metadata |
| Runtime dependencies | none | PyPI metadata, `requires_dist` is null |
| Releases in 24 months | 17, from 0.14.2 on 2024-11-11 to 0.21.2 | PyPI JSON API |
| Longest recent gap | 2024-04-27 to 2024-11-11, 198 days | PyPI JSON API |
| Last push | 2026-09-08 | GitHub API |
| Stars / open issues | 316 / 24 | GitHub API |

Releases are frequent and recent: seven in the last twelve months.
The one gap in 2024 has not repeated.

The PyPI `license` field is empty.
The licence comes from the `License :: OSI Approved :: MIT License` classifier and the repository.
The GitHub API also reports the repository as MIT.

### Install weight

It is a compiled Rust extension built with maturin.
There is no pure-Python fallback.

The PyPI JSON API lists these published wheels for 0.21.2:

| Wheel | Size |
| --- | --- |
| `cp310-abi3-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2` | 3.58 MB |
| `cp310-abi3-macosx_10_12_x86_64` | 1.84 MB |
| `cp310-abi3-manylinux_2_17_x86_64` | 1.95 MB |
| `cp310-abi3-manylinux_2_24_aarch64` | 1.89 MB |
| `cp310-abi3-manylinux_2_24_armv7l` | 1.75 MB |
| `cp310-abi3-manylinux_2_12_i686` | 1.86 MB |
| `cp310-abi3-musllinux_1_2_{x86_64,aarch64,armv7l}` | 1.99 to 2.19 MB |
| `cp310-abi3-win32`, `cp310-abi3-win_amd64` | 1.60 MB, 1.91 MB |
| `cp310-abi3-pyemscripten_2025_0_wasm32` | 0.53 MB |
| `pp311-pypy311_pp73-{macosx_x86_64,manylinux aarch64,manylinux x86_64}` | 1.84 to 1.95 MB |
| `css_inline-0.21.2.tar.gz` | 73 KB |

One `abi3` wheel per platform covers CPython 3.10 and every later 3.x.
The same property made `lxml` tolerable in #7.
One wheel per platform is also better than `lxml`'s per-version matrix.
No macOS arm64-only wheel exists.
Users on arm64 get the 3.58 MB universal2 wheel.

**There is no free-threaded wheel.**
Measured: `uv pip install css-inline` into a CPython 3.14.7 free-threading venv falls back to the sdist and builds from source.
The build took 26.7 s wall and 67.5 s CPU.
It produced `css_inline.cpython-314t-darwin.so` rather than an `abi3` file.
It succeeded on a machine with no `rustc` or `cargo` on `PATH` and no `~/.cargo` or `~/.rustup`.
`uv` resolved maturin's build requirements, which include [`puccinialin`](https://pypi.org/project/puccinialin/).
Then maturin downloaded a Rust toolchain itself.
So the no-wheel branch is slow rather than fatal.
But it is a multi-minute surprise inside `pip install` for anyone on a free-threaded interpreter.
Epistole targets Python 3.13+, where free-threading is a real option.

The installed size is **3.70 MB**, measured as the whole `site-packages` of a fresh `uv venv` minus a 5,264-byte empty-venv baseline.
That is one shared object of 3,438,560 bytes plus a 123-byte `__init__.py`.
For comparison, #7's table lists `lxml` at 19 MB, `inscriptis` at 22 MB and `html2text` at 164 KB.

### API and behaviour

The API has `inline(html)`, `inline_fragment(fragment, css)`, `inline_many(documents)`, `inline_many_fragments(...)`, and a configurable `CSSInliner` class ([Python README](https://github.com/Stranger6667/css-inline/blob/master/bindings/python/README.md)).
`inline_many` distributes the work across Rust-level threads.

The README lists these options on `CSSInliner`:

| Option | Default |
| --- | --- |
| `inline_style_tags` | `True` |
| `keep_style_tags` | `False` |
| `keep_link_tags` | `False` |
| `keep_at_rules` | `False` |
| `load_remote_stylesheets` | `True` |
| `base_url` | `None` |
| `extra_css` | `None` |
| `cache` | `None` |
| `minify_css` | `False` |
| `remove_inlined_selectors` | `False` |
| `apply_width_attributes` / `apply_height_attributes` | `False` |
| `preallocate_node_capacity` | `32` |

The `data-css-inline` attribute overrides behaviour per element.
`ignore` skips inlining for that element, or skips a `link` or `style` tag entirely.
`keep` retains a `style` tag even when `keep_style_tags` is off.

**I measured what it does with rules it cannot inline.**
I ran every case locally on 0.21.2.

The input is:

```html
<style>p{color:red}@media (max-width:600px){p{color:blue}}a:hover{color:green}@font-face{font-family:X;src:url(x.woff2)}</style>
```

Default options produce:

```html
<html><head></head><body><p style="color: red;">hi</p><a href="#">l</a></body></html>
```

`keep_at_rules=True` produces:

```html
<html><head><style>@media (max-width:600px){p{color:blue}} @font-face{font-family:X;src:url(x.woff2)} </style></head><body><p style="color: red;">hi</p><a href="#">l</a></body></html>
```

So css-inline drops at-rules by default and keeps them with a flag, as the README says.
**It drops pseudo-class rules either way.**
`a:hover` is gone in both outputs.
`keep_at_rules` does not keep it, because it is not an at-rule.
The README does not say this.
Inlining silently drops any hover state in the caller's CSS.

**I measured its failure behaviour.**

- Malformed HTML does not raise.
  `<p style="color:red">a<style>p{color:` returns `<p style="color:red">a</p>`.
- Broken CSS does not raise.
  `p{{{color:red}` yields `<p style="">x</p>`.
  So css-inline drops the rule and leaves an empty `style` attribute behind.
- A `<link href="data:text/css,...">` **raises `InlineError`**, as described at the top.
  This happens with default options, since `load_remote_stylesheets` defaults to `True`.
- Setting `load_remote_stylesheets=False` does not inline those stylesheets.
  It deletes the `<link>` tags and loses their contents.

The README states no document size limit.
I found none either: the 1.19 MB report inlined in 2 to 7 ms.

`css_inline` has no `__version__` attribute.
Use `importlib.metadata.version("css_inline")` instead.

### Performance

The README publishes benchmarks against `premailer` on a Ryzen 9 9950X with `rustc 1.91` and Python 3.14.2.
It reports 4.27 µs on a 230 B document (19.93x faster than premailer), 80.59 µs on 8.58 KB (12.76x), 46.88 µs on 4.3 KB (30.73x), and 17.57 ms on a 1.81 MB GitHub page (613.48x).
The benchmarks are in-repo, at `css-inline/benches/inliner.rs` for the Rust core.
These are vendor-published benchmarks against a competitor, so treat the ratios as directional.
My own timings are consistent in magnitude: 2 to 9 ms on documents between 0.3 and 1.2 MB.

Speed is not the deciding factor here.
The library is fast enough that speed would never be the reason to reject it.

## Alternatives

| Package | Latest | Released | Licence | Runtime deps | Last push | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| [`css-inline`](https://pypi.org/project/css-inline/) | 0.21.2 | 2026-08-24 | MIT | none | 2026-09-08 | leading option, see above |
| [`premailer`](https://pypi.org/project/premailer/) | 3.10.0 | 2021-08-02 | BSD-3-Clause | `lxml`, `cssselect`, `cssutils`, `requests`, `cachetools` | 2023-12-16 | five years without a release |
| [`toronado`](https://pypi.org/project/toronado/) | 0.1.0 | 2020-12-10 | Apache-2.0 | `cssselect`, `cssutils`, `lxml` | 2020-12-10 | effectively unmaintained |
| [`emails`](https://pypi.org/project/emails/) | 1.1.2 | 2026-05-18 | Apache-2.0 | `python-dateutil`, `puremagic`, `dkimpy`; `[html]` adds `premailer`, `lxml`, `cssutils`, `chardet`, `requests` | 2026-05-18 | prior art, see below |

`premailer` has one metadata problem.
Its PyPI `license` field reads `Python`, while the GitHub API reports the repository's LICENSE as BSD-3-Clause.
It also pulls in `requests` and `cachetools` for one feature: fetching remote stylesheets.
That is the same complaint #7 raised against `inscriptis`.
All five of its runtime dependencies would become transitive dependencies for every Epistole user.
`lxml` alone is 19 MB.

`toronado` had five releases between 2016 and 2020 and 61 stars.
It is not a candidate.

### `emails`' `load_and_transform()`

This is the prior art #19 names.
I read it from [`emails/transformer.py`](https://github.com/lavr/python-emails/blob/master/emails/transformer.py).

The transform chain is five numbered steps in one method:

1. `css_inline=True`: run `LocalPremailer(...).transform()`.
   `LocalPremailer` is a subclass of `premailer.Premailer` that overrides `_load_external` so a stylesheet can come from a local file store rather than only from HTTP.
   All of the inlining itself is premailer code.
2. `load_images=True`: walk `<img src>`, CSS `url()` values in `style` attributes, and background attributes, and fetch each into an attachment store.
   `load_images` may be a callable, which becomes a per-image filter.
3. `remove_unsafe_tags=True`: delete `script`, `object`, `iframe`, `frame`, `base`, `meta`, `link` and `style` outright.
4. `set_content_type_meta=True`: insert a `<meta http-equiv="content-type">`.
5. `images_inline=False`: if requested, convert every loaded image to a `data:` URI.

Two findings matter for Epistole.

**`emails` does not implement inlining.**
It delegates to premailer.
Its own code fetches images, which is the part Epistole already decided to own in #11.
So the prior art amounts to "call somebody else's inliner".
This note is about exactly that choice.

**Step 3 deletes `<style>` unconditionally, after step 1.**
So `emails` is lossy by design.
Anything premailer could not inline is gone, including every `@media` block and every `:hover` rule.
That is a defensible choice for a library whose whole purpose is producing marketing email.
It is not defensible for Epistole, whose purpose is to send the caller's HTML.

The dependency chain is `emails[html]` to `premailer` to `lxml` plus `cssselect`, `cssutils`, `chardet`, `requests`.
Under #7's weight test, that alone disqualifies it.

`emails` is active again, incidentally.
Version 1.1.2 shipped on 2026-05-18, after a long period without releases.
It sets `requires-python >=3.10`.

## The scale problem, measured

All numbers below come from my own runs on the report described above.
I invoked `css-inline` through `uv run --no-project --with css-inline`.
I added nothing to this project's dependencies.

| Scenario | Bytes | Note |
| --- | --- | --- |
| Rendered Quarto report, as-is | 1,188,695 | 11.6x Gmail's clip threshold |
| `css_inline.inline()`, default options | raises `InlineError` | `data:text/css` `<link>` treated as a path |
| `load_remote_stylesheets=False` | 195,706 | 6.1x smaller, 650 KB of CSS discarded, 5 `style` attributes produced |
| `load_remote_stylesheets=False, keep_at_rules=True` | 436,598 | one `<style>` block remains |
| `load_remote_stylesheets=False, keep_style_tags=True` | 538,488 | all three `<style>` blocks remain |
| `data:text/css` `<link>`s stripped by hand, then inlined | 195,706 | same as above; those links contributed nothing |
| ... and `<script>` blocks also stripped | 3,212 | the actual message |
| `<script>` stripped, no inlining | 996,201 | still 9.7x the clip threshold |
| Synthetic worst case in: 2,000-row table, one 9-property rule matching 10,000 cells | 292,714 | |
| Synthetic worst case out | 2,362,519 | 8.07x growth, 9 ms |

Read the middle of that table carefully.
The 6.1x shrink does not come from a clever step in the inlining.
It comes from css-inline discarding Bootstrap, which the document never used.
Only **five** elements in the whole report received a `style` attribute.
Four of those are in the syntax-highlighted code block.
Everything else in 993,049 characters of CSS matched nothing.

The last two rows show the opposite case.
When the CSS does match, every matching element receives the full rule.
The document grows by the number of matches times the rule length.
A styled data table is the worst case for this growth.
A report emailed from Python contains precisely that.

The key number for #19 is 3,212 bytes.
With the scripts stripped and the CSS inlined, this report becomes a perfectly ordinary message.
Epistole should do neither step unless the caller asks.
The script-stripping matters more than the CSS.

## Reproduction

The `.qmd`, the rendered `report.html`, the inlined output, and the throwaway venvs are in `/tmp/eps-css/` for this session only.
I installed nothing into the project venv and did not change `pyproject.toml`.

# CSS in an HTML body

Research for [issue #19](https://github.com/ozanozbeker/epistole/issues/19).
Primary sources only.
Every factual claim below carries a URL.
Where a claim comes from a live probe or a local run rather than a document, the text says so.

Local runs were done on 2026-09-09, macOS arm64, CPython 3.14.7 free-threading build, `uv` 0.12.10, Quarto 1.10.18, Pandoc 3.11.

## What this means for epistole's design

Do not inline.
Warn about size, not about CSS.
Document the limitation with a one-line recipe the caller can run themselves.

Four measurements drive that, and two of them contradict the framing in #19.

**First, `css_inline.inline()` raises on the exact input that motivated this ticket.**
A Quarto document rendered with `embed-resources: true` carries its stylesheets as `<link href="data:text/css,...">`.
`css-inline` resolves a `<link href>` as a path, and a percent-encoded 650 KB `data:` URI is not one.
Measured locally on a freshly rendered report: `css_inline.inline(html)` with default options raises `InlineError: File name too long (os error 63)`.
On a short `data:text/css` URI it raises `InlineError: Missing stylesheet file: data:text/css,p%7Bcolor%3Ared%7D`.
So epistole could not just call `inline()`.
It would have to strip the `<link>` tags first, which means silently discarding 650 KB of the caller's authored CSS before doing anything else.

**Second, inlining changes size in both directions, by roughly an order of magnitude either way.**
Measured on the report described below: 1,188,695 bytes in, 195,706 bytes out, a 6.1x shrink, because css-inline drops every rule whose selector matches nothing and a Quarto report ships almost all of Bootstrap unused.
Measured on a synthetic worst case, a 2,000-row table whose cells all match one nine-property rule: 292,714 bytes in, 2,362,519 bytes out, an 8.1x growth.
Whichever way it moves, the library cannot tell the caller in advance which one they will get.
That is a bad property for a step that runs automatically.

**Third, recipient support for a `<head>` stylesheet is much better than #19 assumed.**
The claim in #19 that "Outlook's Word rendering engine will not render a `<head>` stylesheet at any size" is wrong.
Community testing records Outlook on Windows 2007 through 2019 as partial support for the `<style>` element, with the caveat that the rules must be declared before the elements that use them, not as no support ([Can I Email, `<style>` element](https://www.caniemail.com/features/html-style/), community-maintained).
Apple Mail, Outlook.com, Outlook for macOS, Yahoo, Thunderbird and Gmail desktop webmail all record full or partial support.
The one outright hole is Gmail mobile webmail, recorded as no support since 2020-02.

**Fourth, inlining does not solve the problem that actually breaks the email, which is size.**
Gmail clips a message over roughly 102 KB and hides the rest behind a "View entire message" link.
The measured report is 1,188,695 bytes, about 11.6x that threshold, and it is still 195,706 bytes after inlining because 155,053 of those bytes are `<script>` that css-inline does not touch.
No CSS strategy fixes an email that is ten times too big.

So the honest position is: epistole does not own the caller's CSS, and says so.

Concretely:

- No `epistole[css]` extra and no `css-inline` dependency.
  Under #7's test this fails on the missing-extra branch: there is no acceptable fallback, because "inline the CSS" and "do not inline the CSS" produce visibly different emails, and a library must not silently pick one based on what happens to be installed.
- One warning at `Message(...)` construction when the assembled HTML exceeds 102,400 bytes.
  That is the only threshold in this whole area with a consistent published figure and an exact, cheap check.
  It also survives whatever the caller does about CSS.
- No warning on the presence of a `<style>` block.
  Most recipients honour it, so that warning would be noise on correct input.
- Document the recipe: `Message(html=css_inline.inline(html))`, with the `<link href="data:text/css">` caveat spelled out, so a caller who wants inlining opts in with their own dependency and their own licence review.
  This mirrors the `text_renderer=` seam settled in #15.

This also preserves the promise made in ADR-0003 and #11: the HTML epistole sends is byte-identical to what the caller passed except for rewritten `src` values.
Inlining rewrites every element in the document.
That is not a rewrite epistole should perform behind the caller's back.

## Recipient-side support

The constraint is recipient-side, so it applies whichever backend sent the message.

### Gmail: documented, no stated limit

Google's own [CSS Support](https://developers.google.com/workspace/gmail/design/css) page states: "You can style email sent to Gmail using inline `<style>` blocks and standard CSS.
Most CSS selectors, attributes, and media-queries are supported.
Unsupported CSS properties and selectors may be ignored by Gmail."
Both worked examples on that page put the `<style>` element inside `<head>`.

The page states "Gmail supports class, element, and id selectors", documents media queries against screen width, orientation and resolution, and lists several hundred supported properties.

The page states no size limit.
Fetched and searched on 2026-09-09: the words "limit", "KB", "byte", "8192" and "16384" do not appear anywhere in the article body.

The widely repeated 8192 figure has no Google source that I could find, and I do not believe one exists.
The trail leads to community testing, not documentation.
The issue [hteumeuleu/email-bugs#90](https://github.com/hteumeuleu/email-bugs/issues/90) records two tests, one with 1,024 declarations spread across several `<style>` tags and one with 1,024 separate `<style>` tags, both landing on a 16 KB cap, with the note that Gmail keeps the rules before the limit and drops everything after.
That issue itself cites a 2017 observation of 8192 bytes and says it was "recently updated to 16384 bytes according to Eric Lepetit on the Emailgeeks Slack".
[Can I Email](https://www.caniemail.com/features/html-style/) (community-maintained) carries the 16 KB figure as note 6 on Gmail desktop webmail from 2023-01, linking to that same issue.
So the number epistole should quote, if it quotes one, is 16 KB, sourced to community testing and labelled as such.
The 8192 figure is a superseded community measurement that got copied forward.

### Outlook: first-party documentation exists, and it is from 2006

Microsoft's [Word 2007 HTML and CSS Rendering Capabilities in Outlook 2007](https://learn.microsoft.com/en-us/previous-versions/office/developer/office-2007/aa338201(v=office.12)) is the only first-party document on this.
It is archived, marked `ms.date: 2014-07-09`, and written in August 2006.
It states plainly: "Microsoft Office Outlook 2007 uses the HTML parsing and rendering engine from Microsoft Office Word 2007 to display HTML message bodies.
The same HTML and cascading style sheets (CSS) support available in Word 2007 is available in Outlook 2007."

What the document actually supports:

- Word 2007 supports "a subset of the standard HTML 4.01 specification and of the Internet Explorer 6.0 HTML specification" and "a subset of the standard Cascading Stylesheet Specification, Level 1".
- The `<style>` element is listed in the supported HTML elements table, with attributes `dir`, `lang` and `type`.
  Its "Cascading Style Sheet Style Support Level" column reads `None`, but that column describes which properties apply to the element itself, not whether the stylesheet is honoured.
  Read carefully, this document does not say a `<head>` stylesheet is ignored.
- CSS support is tiered.
  `SPAN` gets CORE, `DIV` and `P` get COREEXTENDED, most other elements get FULL.
  CORE has 28 properties and does not include `width`, `height` or `padding`.
- The `media` attribute is listed as unsupported.
- `position`, `float`, `max-width`, `min-width`, `overflow`, `visibility`, `z-index`, `background-image`, `background-position` and `background-repeat` are all listed as unsupported against CSS 2.1.
- The document contradicts itself on `display`: it appears in the CORE supported list and in both unsupported lists.

Everything past Outlook 2007 is community lore.
Microsoft has published nothing equivalent for 2010, 2013, 2016, 2019 or the new Outlook.
Searching learn.microsoft.com returns only Q&A threads, which are user-to-user posts, not documentation.

Community testing fills the gap: Can I Email records Outlook Windows 2007 through 2019 as partial `<style>` support with the ordering caveat, and as **no** `@media` support and **no** `:hover` support.
That matters here, because those are exactly the rules css-inline cannot inline either.
Inlining does not buy anything on Outlook Windows that a `<head>` stylesheet does not already buy.

### Apple Mail: no first-party statement

I could not find one.
Apple's developer documentation covers [MailKit](https://developer.apple.com/documentation/mailkit) extensions and the archived [Mail Stationery release notes](https://developer.apple.com/library/archive/releasenotes/AppleApplications/MailStationeryRelNote/index.html), neither of which documents CSS support for received messages.
The stationery notes only warn that email clients "are often much less capable than most web browsers".
Community testing records Apple Mail on macOS and iOS as full `<style>` support back to 10.3.

### Support table

All rows below are from [Can I Email](https://www.caniemail.com/), which is **community-maintained**, not first-party.
Data pulled from `https://www.caniemail.com/api/data.json` on 2026-09-09.
`y` supported, `a` partial, `n` not supported.

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

Note the shape of it.
`@media` and `:hover` fail in the same places a `<head>` stylesheet fails, and css-inline drops both by default (measured below).
Inlining moves the properties that already work into a place where they still work.
It does not rescue the ones that do not.

## Provider-side size ceilings

Gmail clips a message and hides the tail behind a "View entire message" link.

The threshold is **not documented by Google**.
I searched Gmail Help and the Workspace admin help; the only size limit Google publishes is the 25 MB attachment cap, which is a different thing.
The best available source is vendor documentation: Mailchimp states "Gmail clips emails that have a message size larger than 102KB, and hides the full content behind a 'View entire message' link", and that the size counts "your text, the URLs and tracking code for links, the HTML used to style your content, and more" ([Mailchimp help](https://mailchimp.com/help/gmail-is-clipping-my-email/)).
Trust level: vendor documentation, consistent across ESPs, unconfirmed by Google.

The community record is honest about the uncertainty. [hteumeuleu/email-bugs#41](https://github.com/hteumeuleu/email-bugs/issues/41), opened 2018-05-17, says of the 102 kB figure that "no one seems to know where this number comes from", and collects reports of clipping below it.

Treat 102,400 bytes as a soft threshold and warn rather than raise.
That is what the evidence supports.

## What Quarto and Pandoc actually do

### Pandoc leaves a stylesheet as a `<link>` when it contains `</`

Confirmed from source.
[`src/Text/Pandoc/SelfContained.hs`](https://github.com/jgm/pandoc/blob/main/src/Text/Pandoc/SelfContained.hs), the `TagOpen "link"` case, line 132 at the time of reading:

```haskell
Fetched (mime, bs)
  | ("text/css" `T.isPrefixOf` mime ||
      fromAttrib "rel" t == "stylesheet")
    && T.null (fromAttrib "media" t)
    && not ("</" `B.isInfixOf` bs) -> do
```

All three conditions must hold before Pandoc promotes the `<link>` into an inline `<style>` element.
Otherwise it falls through to the `otherwise` branch and rewrites `href` to a `data:` URI, keeping the `<link>`.

The `</` guard carries no comment.
The nearby `-- see #5725` comment is attached to the `type` attribute on the emitted `<style>` tag, not to this check.
The reason is inferable rather than documented: the HTML tokenizer ends a `<style>` element at the first `</style`, and Pandoc's guard is the conservative version of that, refusing on any `</` at all.
Modern CSS hits it easily, for instance through `content: "</div>"` or an escaped sequence inside a `url()`.
The same guard exists for scripts one case up, and there it is narrowed to `"</script"`.

The `media` condition matters too and is easy to miss: a `<link media="print">` also stays a `<link>`, whatever its contents.

Pandoc's manual documents `--embed-resources` as "Produce a standalone HTML file with no external dependencies, using `data:` URIs to incorporate the contents of linked scripts, stylesheets, images, and videos" and `--self-contained` as a "Deprecated synonym for `--embed-resources --standalone`" ([Pandoc manual](https://pandoc.org/MANUAL.html)).
Nothing in the manual mentions inlining CSS into `style` attributes.

### Neither Quarto nor Pandoc inlines CSS for HTML output

Checked three ways.

Pandoc's manual has no such option.
Grepping the Pandoc HTML writer and `SelfContained.hs` turns up no per-element style rewriting; `SelfContained.hs` only rewrites `src` and `href` attributes and promotes `<link>` to `<style>`.

Quarto **does ship a CSS inliner**, and this is worth recording because it looks like a counterexample and is not one.
`/Applications/quarto/share/scripts/juice.ts` is a four-line Deno wrapper around the npm `juice` package.
It is called from exactly one place, a local function `juice()` in `/Applications/quarto/share/filters/main.lua` at line 9797 (and its copy in `crossref.lua`).
Reading the two call sites at lines 9860 and 9967, the guard is `if(_quarto.format.isTypstOutput())`.
Quarto only inlines CSS when it is flattening a raw HTML table for **Typst** output, where no stylesheet can follow.
HTML output never touches it.
The Lua source also records a limitation worth knowing: "juice truncates around 15k characters; let's guard any over 2000 characters", which is why Quarto swaps long `data:image` URIs for a UUID before the call and swaps them back after.

Quarto's `email` format exists for Posit Connect (`/Applications/quarto/share/schema/document-email.yml` defines `email-version` 1 and 2) but is implemented inside the compiled binary, so I could not read what it does with CSS.
It is a Connect integration, not a general-purpose email body, so it does not change the answer for epistole.

### What one small Quarto report actually weighs

Measured locally.
I wrote a 30-line `.qmd` with a heading, a three-row Markdown table, a callout, a list and one Python code block, then ran `quarto render report.qmd --to html` with `embed-resources: true`.

| Component | Chars |
| --- | --- |
| Whole document | 1,188,688 |
| `<style>` blocks, 3 of them | 342,705 |
| `<link href="data:text/css,...">` tags, 2 of them | 650,344 |
| `<script>` blocks, 8 of them | 155,053 |
| Machine-generated `style="..."` attributes | 0 |

That is 993,049 characters of CSS for a document whose actual prose is under 400 characters.
The shape matches #19's measurement on a real report.
The absolute numbers differ because the documents differ; both are mine and both are measured.

Note the last row.
Neither Quarto nor Pandoc emits a single `style` attribute.

## `css-inline`

[PyPI](https://pypi.org/project/css-inline/), [repository](https://github.com/Stranger6667/css-inline).

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

Cadence is healthy and recent: seven releases in the last twelve months.
The one gap in 2024 has not repeated.

The PyPI `license` field is empty; the licence comes from the `License :: OSI Approved :: MIT License` classifier and the repository, which the GitHub API also reports as MIT.

### Install weight

It is a compiled Rust extension built with maturin.
There is no pure-Python fallback.

Published wheels for 0.21.2, from the PyPI JSON API:

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

One `abi3` wheel per platform covers CPython 3.10 and every later 3.x, which is the same property that made `lxml` tolerable in #7 and better than `lxml`'s per-version matrix.
No macOS arm64-only wheel exists; arm64 users get the 3.58 MB universal2 wheel.

**There is no free-threaded wheel.**
Measured: `uv pip install css-inline` into a CPython 3.14.7 free-threading venv falls back to the sdist and builds from source.
The build took 26.7 s wall, 67.5 s CPU, and produced `css_inline.cpython-314t-darwin.so` rather than an `abi3` file.
It succeeded on a machine with no `rustc` or `cargo` on `PATH` and no `~/.cargo` or `~/.rustup`: `uv` resolved maturin's build requirements, which include [`puccinialin`](https://pypi.org/project/puccinialin/), and maturin downloaded a Rust toolchain itself.
So the no-wheel branch is slow rather than fatal, but it is a multi-minute surprise inside `pip install` for anyone on a free-threaded interpreter, and epistole targets Python 3.13+ where free-threading is a live choice.

Installed size, measured as the whole `site-packages` of a fresh `uv venv` minus a 5,264-byte empty-venv baseline: **3.70 MB**.
That is one shared object of 3,438,560 bytes plus a 123-byte `__init__.py`.
For comparison with #7's table: `lxml` is 19 MB, `inscriptis` 22 MB, `html2text` 164 KB.

### API and behaviour

`inline(html)`, `inline_fragment(fragment, css)`, `inline_many(documents)`, `inline_many_fragments(...)`, and a configurable `CSSInliner` class ([Python README](https://github.com/Stranger6667/css-inline/blob/master/bindings/python/README.md)).
`inline_many` releases work into Rust-level threads.

Options on `CSSInliner`, from the README:

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

The `data-css-inline` attribute overrides behaviour per element: `ignore` skips inlining for that element or skips a `link` or `style` tag entirely, and `keep` retains a `style` tag even when `keep_style_tags` is off.

**What it does with rules it cannot inline.**
Measured locally, all on 0.21.2.

Input:

```html
<style>p{color:red}@media (max-width:600px){p{color:blue}}a:hover{color:green}@font-face{font-family:X;src:url(x.woff2)}</style>
```

Default options:

```html
<html><head></head><body><p style="color: red;">hi</p><a href="#">l</a></body></html>
```

`keep_at_rules=True`:

```html
<html><head><style>@media (max-width:600px){p{color:blue}} @font-face{font-family:X;src:url(x.woff2)} </style></head><body><p style="color: red;">hi</p><a href="#">l</a></body></html>
```

So at-rules are dropped by default and survivable with a flag, matching the README.
**Pseudo-class rules are dropped either way.**
`a:hover` is gone in both outputs, and `keep_at_rules` does not save it because it is not an at-rule.
The README does not say this.
Any hover state in the caller's CSS is lost silently.

**Failure behaviour.**
Measured.

- Malformed HTML does not raise.
  `<p style="color:red">a<style>p{color:` returns `<p style="color:red">a</p>`.
- Broken CSS does not raise.
  `p{{{color:red}` yields `<p style="">x</p>`, so the rule is dropped and an empty `style` attribute is left behind.
- A `<link href="data:text/css,...">` **raises `InlineError`**, as described at the top.
  This is the default path, since `load_remote_stylesheets` defaults to `True`.
- Setting `load_remote_stylesheets=False` does not inline those stylesheets; it deletes the `<link>` tags and their contents are lost.

The README states no document size limit, and none showed up: the 1.19 MB report inlined in 2 to 7 ms.

`css_inline` exposes no `__version__` attribute; use `importlib.metadata.version("css_inline")`.

### Performance

The README publishes benchmarks against `premailer` on a Ryzen 9 9950X with `rustc 1.91` and Python 3.14.2: 4.27 µs on a 230 B document (19.93x faster than premailer), 80.59 µs on 8.58 KB (12.76x), 46.88 µs on 4.3 KB (30.73x), and 17.57 ms on a 1.81 MB GitHub page (613.48x).
The benchmarks are in-repo, at `css-inline/benches/inliner.rs` for the Rust core.
Vendor-published benchmarks against a competitor, so treat the ratios as directional.
My own timings are consistent in magnitude: 2 to 9 ms on documents between 0.3 and 1.2 MB.

Speed is not the deciding factor here.
It is fast enough that it would never be the reason to say no.

## Alternatives

| Package | Latest | Released | Licence | Runtime deps | Last push | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| [`css-inline`](https://pypi.org/project/css-inline/) | 0.21.2 | 2026-08-24 | MIT | none | 2026-09-08 | leading option, see above |
| [`premailer`](https://pypi.org/project/premailer/) | 3.10.0 | 2021-08-02 | BSD-3-Clause | `lxml`, `cssselect`, `cssutils`, `requests`, `cachetools` | 2023-12-16 | five years without a release |
| [`toronado`](https://pypi.org/project/toronado/) | 0.1.0 | 2020-12-10 | Apache-2.0 | `cssselect`, `cssutils`, `lxml` | 2020-12-10 | effectively dead |
| [`emails`](https://pypi.org/project/emails/) | 1.1.2 | 2026-05-18 | Apache-2.0 | `python-dateutil`, `puremagic`, `dkimpy`; `[html]` adds `premailer`, `lxml`, `cssutils`, `chardet`, `requests` | 2026-05-18 | prior art, see below |

`premailer` has one metadata problem worth flagging: its PyPI `license` field reads `Python`, while the repository's LICENSE is BSD-3-Clause per the GitHub API.
It also pulls `requests` and `cachetools` for one feature, fetching remote stylesheets, which is the same complaint #7 raised against `inscriptis`.
Five of its five runtime dependencies are transitive weight epistole would push onto every user, and `lxml` alone is 19 MB.

`toronado` had five releases between 2016 and 2020 and 61 stars.
Not a candidate.

### `emails`' `load_and_transform()`

The prior art #19 names.
Read from [`emails/transformer.py`](https://github.com/lavr/python-emails/blob/master/emails/transformer.py).

The transform chain is five numbered steps in one method:

1. `css_inline=True`: run `LocalPremailer(...).transform()`.
   `LocalPremailer` is a subclass of `premailer.Premailer` that overrides `_load_external` so a stylesheet can come from a local file store rather than only from HTTP.
   The inlining itself is 100 percent premailer.
2. `load_images=True`: walk `<img src>`, CSS `url()` values in `style` attributes, and background attributes, fetching each into an attachment store.
   `load_images` may be a callable, which becomes a per-image filter.
3. `remove_unsafe_tags=True`: delete `script`, `object`, `iframe`, `frame`, `base`, `meta`, `link` and `style` outright.
4. `set_content_type_meta=True`: insert a `<meta http-equiv="content-type">`.
5. `images_inline=False`: if requested, convert every loaded image to a `data:` URI.

Two things stand out for epistole.

**`emails` does not implement inlining.**
It delegates to premailer and spends its own code on image harvesting, which is the part epistole already decided to own in #11.
So the prior art is really "call somebody else's inliner", which is exactly the choice this note is deciding.

**Step 3 deletes `<style>` unconditionally, after step 1.**
So `emails` accepts the lossy outcome by design: anything premailer could not inline, including every `@media` block and every `:hover` rule, is gone.
That is a defensible choice for a library whose whole job is producing marketing email.
It is not defensible for epistole, whose job is to send the caller's HTML.

The dependency chain is `emails[html]` to `premailer` to `lxml` plus `cssselect`, `cssutils`, `chardet`, `requests`.
Under #7's weight test that is disqualifying on its own.

`emails` is alive again, incidentally: 1.1.2 on 2026-05-18 after a long dormancy, and `requires-python >=3.10`.

## The scale problem, measured

All numbers below are my own runs on the report described above.
`css-inline` was invoked through `uv run --no-project --with css-inline`, and nothing was added to this project's dependencies.

| Scenario | Bytes | Note |
| --- | --- | --- |
| Rendered Quarto report, as-is | 1,188,695 | 11.6x Gmail's clip threshold |
| `css_inline.inline()`, default options | raises `InlineError` | `data:text/css` `<link>` treated as a path |
| `load_remote_stylesheets=False` | 195,706 | 6.1x smaller, 650 KB of CSS discarded, 5 `style` attributes produced |
| `load_remote_stylesheets=False, keep_at_rules=True` | 436,598 | one `<style>` block survives |
| `load_remote_stylesheets=False, keep_style_tags=True` | 538,488 | all three `<style>` blocks survive |
| `data:text/css` `<link>`s stripped by hand, then inlined | 195,706 | same as above; those links contributed nothing |
| ... and `<script>` blocks also stripped | 3,212 | the actual email |
| `<script>` stripped, no inlining | 996,201 | still 9.7x the clip threshold |
| Synthetic worst case in: 2,000-row table, one 9-property rule matching 10,000 cells | 292,714 | |
| Synthetic worst case out | 2,362,519 | 8.07x growth, 9 ms |

Read the middle of that table carefully.
The 6.1x shrink is not inlining doing something clever.
It is inlining throwing away Bootstrap, which the document never used.
Only **five** elements in the whole report received a `style` attribute, and four of those are the syntax-highlighted code block.
Everything else in 993,049 characters of CSS matched nothing.

The last two rows are the other half of the truth.
When the CSS does match, every matching element pays the full cost of the rule, and the document grows by the number of matches times the rule length.
A styled data table, which is precisely what a report emailed from Python contains, is the shape that explodes.

The one number that answers #19 is 3,212 bytes.
Strip the scripts, inline the CSS, and this report becomes a perfectly ordinary email.
Neither step is something epistole should do without being asked, and the script-stripping matters more than the CSS.

## Reproduction

The `.qmd`, the rendered `report.html`, the inlined output, and the throwaway venvs live under `/tmp/eps-css/` for this session only.
Nothing was installed into the project venv and `pyproject.toml` was not touched.

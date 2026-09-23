# HTML to plain-text extraction

This is research for [#7](https://github.com/ozanozbeker/epistole/issues/7).
I measured all figures on 2026-09-07, with Python 3.13.12 on macOS arm64.
I installed each candidate into its own throwaway venv and ran it against one realistic marketing message.

## Recommendation

Hand-roll the extractor on `html.parser` and put it in the core.
Ship no extra for this.

Three facts support that.

First, the hand-rolled version is good.
It came second on output quality, behind `inscriptis` and ahead of everything else.
It is under 90 lines long.
It keeps every `href`, marks list items, holds table rows on one line, drops `<style>` and `<title>`, and normalises `&nbsp;`.

Second, the two libraries that beat it or match it both have a disqualifying drawback.
`inscriptis` produces the best output of the candidates.
But it hard-depends on `lxml` and on `requests`, which its own package only imports from the CLI.
That is 22 MB installed.
It would also impose a `lxml>=5.4.0,<6.2.0` upper bound on every Epistole user.
`html2text` is GPL-3.0-or-later.
Epistole is MIT.
A GPL runtime import raises a licence question that Epistole's users should never have to answer.

Third, the "extra absent" branch has no good option.
Omitting the `text/plain` part is wrong.
Naive tag stripping produces the `lxml` output shown below, which is worse than no message at all.
So the absent branch has to be a real extractor anyway.
Once you have written that extractor, the extra adds almost nothing.

Instead of an extra, expose two parameters:

- Put `text: str | None` on the message.
  When a caller supplies text, Epistole uses it and derivation never runs.
- Accept `text_renderer: Callable[[str], str] | None`.
  A caller who wants `inscriptis` or `html2text` installs it themselves and passes `inscriptis.get_text` or `html2text.html2text`.
  Epistole never depends on either, so only the caller who opted in has the GPL question to answer.

Never omit the plain text.
Spam scoring is a weaker reason to include it than commonly believed: SpamAssassin scores HTML-only messages at 0.1 via `MIME_HTML_ONLY` ([`50_scores.cf`](https://github.com/apache/spamassassin/blob/trunk/rules/50_scores.cf), [`20_body_tests.cf`](https://github.com/apache/spamassassin/blob/trunk/rules/20_body_tests.cf)).
The `multipart/alternative` variant `MIME_HTML_ONLY_MULTI` scores 0.000 to 0.001 across the four scoresets.
The real reasons are text-only clients, screen readers, notification pipes, and archive search.
Derivation takes 0.27 ms on a 3 KB message, so there is no reason to skip it.

## Side-by-side output

The fixture is a marketing invoice message: hidden preheader, `<style>` block, logo `<img>`, `<h1>`/`<h2>`, a paragraph with an inline `<a>`, a bulleted list with a link inside a list item, a three-column table with `<thead>`/`<tbody>`/`<tfoot>`, an anchor styled as a button, a `mailto:` link, an `&middot;` separator and a 1x1 tracking pixel.

This section ranks the candidates best to worst.

### 1. inscriptis, strict CSS profile, `display_links=True`

```text
Your March invoice is ready. Total due: $148.00 by April 15.

Your March invoice is ready

Hi Ozan,

Thanks for using Acme Analytics. Your invoice for March 2026 is attached, and you can also [view it online](https://billing.example.com/invoices/2026-03).

What changed this month

  * We raised the free tier to 50,000 events.
  * Webhook retries now back off exponentially.
  * The [v3 API](https://docs.example.com/api/v3) is out of beta.

Usage summary

Item              Quantity   Amount
Events ingested  1,240,000   $98.00
Seats                    5   $50.00
Total due                   $148.00

[Pay invoice](https://billing.example.com/pay/inv_9f31?utm_source=email)

Questions? Reply to this email or reach us at [support@example.com](mailto:support@example.com).

Acme Analytics, 100 Market St, San Francisco, CA 94105
[Unsubscribe](https://example.com/unsubscribe?u=abc123) · [Email preferences](https://example.com/preferences)
```

It is the only candidate that aligns table columns.
It drops `<style>`, `<title>` and the tracking pixel.
It keeps `·`.
`display_links` defaults to `False`, so the href-preserving behaviour above is opt-in.

### 2. stdlib `html.parser`, hand-rolled, tuned

```text
Your March invoice is ready. Total due: $148.00 by April 15.

[Acme Analytics]

Your March invoice is ready

Hi Ozan,

Thanks for using Acme Analytics. Your invoice for March 2026 is attached, and you can also view it online <https://billing.example.com/invoices/2026-03>.

What changed this month

- We raised the free tier to 50,000 events.

- Webhook retries now back off exponentially.

- The v3 API <https://docs.example.com/api/v3> is out of beta.

Usage summary

Item  Quantity  Amount

Events ingested  1,240,000  $98.00

Seats  5  $50.00

Total due  $148.00

Pay invoice <https://billing.example.com/pay/inv_9f31?utm_source=email>

Questions? Reply to this email or reach us at support@example.com.

---

Acme Analytics, 100 Market St, San Francisco, CA 94105
Unsubscribe <https://example.com/unsubscribe?u=abc123> · Email preferences <https://example.com/preferences>
```

The remaining flaws are cosmetic: a blank line between list items and between table rows, and table columns that are space-separated rather than aligned.
Note the `mailto:` handling.
The link label already equals the address, so the extractor suppresses the redundant `<support@example.com>`.

### 3. html2text, `body_width=0`, `unicode_snob=True`

```text
Your March invoice is ready. Total due: $148.00 by April 15.
---

# Your March invoice is ready

Hi Ozan,

Thanks for using **Acme Analytics**. Your invoice for _March 2026_ is attached, and you can also [view it online](https://billing.example.com/invoices/2026-03).

## What changed this month

  * We raised the free tier to 50,000 events.
  * Webhook retries now back off exponentially.
  * The [v3 API](https://docs.example.com/api/v3) is out of beta.

## Usage summary

Item | Quantity | Amount
---|---|---
Events ingested | 1,240,000 | $98.00
Seats | 5 | $50.00
**Total due** |  | **$148.00**

[Pay invoice](https://billing.example.com/pay/inv_9f31?utm_source=email)

Questions? Reply to this email or reach us at [support@example.com](mailto:support@example.com).

* * *

Acme Analytics, 100 Market St, San Francisco, CA 94105
[Unsubscribe](https://example.com/unsubscribe?u=abc123) * [Email preferences](https://example.com/preferences)
```

The structure is good, with two caveats.
The preheader and logo are in the presentational wrapper table.
So html2text renders them as a Markdown header row and emits `---` under them.
`&middot;` became `*`, not `·`.

The bigger problem is the default config.
Without `unicode_snob=True`, html2text transliterates to ASCII:

```text
input:   <p>Caf&eacute; &mdash; caf&eacute;s &hellip;</p>
default: Cafe -- cafes …
snob:    Café — cafés …
```

A mail library that silently turns `Café` into `Cafe` is shipping a bug.
Anyone using html2text must set `unicode_snob=True`.

### 4. markdownify, defaults

```text
Your March invoice is ready


Your March invoice is ready. Total due: $148.00 by April 15.

|  |
| --- |
| Acme Analytics |

Your March invoice is ready
===========================

Hi Ozan,

Thanks for using **Acme Analytics**. Your invoice for
*March 2026* is attached, and you can also
[view it online](https://billing.example.com/invoices/2026-03).

...

| Item | Quantity | Amount |
| --- | --- | --- |
| Events ingested | 1,240,000 | $98.00 |
| Seats | 5 | $50.00 |
|  |  |  |
| --- | --- | --- |
| **Total due** | | **$148.00** |
```

It has two defects.
The `<title>` text becomes the first line of output, so the subject appears three times before the greeting.
`<tfoot>` gets a second `| --- |` separator row, which is broken Markdown.
Source newlines are preserved verbatim, so paragraphs keep the author's HTML indentation breaks.
`markdownify` does drop `<style>` and `<script>` via its `convert_style` and `convert_script` handlers.
It is the only Markdown-producing candidate that keeps `·` intact.

### 5. beautifulsoup4, `get_text(separator="\n", strip=True)`

```text
Your March invoice is ready
Your March invoice is ready. Total due: $148.00 by April 15.
Your March invoice is ready
Hi Ozan,
Thanks for using
Acme Analytics
. Your invoice for
March 2026
is attached, and you can also
view it online
.
What changed this month
We raised the free tier to 50,000 events.
...
```

`get_text` does not distinguish inline elements from block elements.
Every `<strong>`, `<em>` and `<a>` becomes a line break, so a sentence splits into six lines and a stray `.`.
Dropping the separator keeps sentences intact but produces long runs of blank lines and no list markers.
Every href is lost either way.
By default, bs4 gets only `<style>` and `<script>` right.
`get_text` skips them because bs4 stores their contents as the `Stylesheet` and `Script` string subclasses, which are not in `MAIN_CONTENT_STRING_TYPES`.

### 6. lxml `text_content()`

```text

  Your March invoice is ready

    body { margin: 0; padding: 0; background: #f4f4f7; font-family: Helvetica, Arial, sans-serif; }
    .btn { background: #2f6fed; color: #ffffff; padding: 12px 24px; border-radius: 4px; text-decoration: none; display: inline-block; }
    .preheader { display: none !important; visibility: hidden; opacity: 0; height: 0; width: 0; }
    table.usage td, table.usage th { border: 1px solid #dddddd; padding: 8px; }


  Your March invoice is ready. Total due: $148.00 by April 15.
...
```

The recipient would receive the entire CSS block.
Every href is lost.
Whitespace passes through raw, so the output keeps the source file's indentation.
`lxml_html_clean.Cleaner(style=True, scripts=True)` removes the CSS and nothing else.

`text_content()` also joins adjacent blocks with no separator:

```text
input:  <ul><li>a<ul><li>a1</li></ul></li><li>b</li></ul>
output: aa1b
```

That alone rules it out.

### 7. html-to-text (PyPI `html_to_text`)

```text
Your March invoice is ready. Total due: $148.00 by April 15. Your March invoice is readyHi Ozan, Thanks for using Acme Analytics. Your invoice for March 2026 is attached, and you can also view it online. What changed this monthWe raised the free tier to 50,000 events.Webhook retries now back off exponentially. The v3 API is out of beta. Usage summaryItemQuantityAmountEvents ingested1,240,000$98.00Seats5$50.00Total due$148.00 Pay invoice  Questions? Reply to this email or reach us at support@example.com.  Acme Analytics, 100 Market St, San Francisco, CA 94105 Unsubscribe · Email preferences
```

It produces one run-on paragraph, with words joined across block boundaries: `ItemQuantityAmountEvents ingested1,240,000$98.00`.
This is not the plain-text extractor the name suggests.
It is a boilerplate-removal tool that scores HTML chunks and joins the chunks it keeps with `' '`.
Its API is also wrong for this job: `get_parser` takes `tags_to_save`, `tags_to_remove`, `punctuation` and `min_allowed_weight`.

## Robustness

I ran the same six fragments through each candidate.

| Input | inscriptis | stdlib | html2text | markdownify | bs4 | lxml |
| --- | --- | --- | --- | --- | --- | --- |
| Fragment, no `<html>`/`<body>` | ok | ok | ok | ok | href lost | `Hello worldonetwo` |
| Unclosed `<a>` across `</p>` | href kept | href lost | href lost, `**` unbalanced, `[link` dangling | href kept | href lost | href lost, text fused |
| `&nbsp;` and `&mdash;` | normalised to space, `—` kept | normalised to space, `—` kept | `--` unless `unicode_snob` | raw `\xa0` | raw `\xa0` | raw `\xa0` |
| `<a>` with no href | ok | ok | emits `[that]()` | ok | stray space before `.` | ok |
| MSO conditional comment | dropped | dropped | dropped | dropped | dropped | dropped |
| Nested `<ul>` | indented | flattened | indented | indented | flattened | `aa1b` |

No candidate raised on malformed input.

Timings on the 3 KB fixture are the mean of 20 runs:

| lxml | inscriptis | stdlib | html2text | bs4 | markdownify |
| --- | --- | --- | --- | --- | --- |
| 0.07 ms | 0.27 ms | 0.27 ms | 0.43 ms | 0.57 ms | 1.02 ms |

Speed is irrelevant at these magnitudes.

## Install weight and maintenance

Installed size is the whole `site-packages` of a fresh `uv venv` after installing the package, minus a 12 KB empty-venv baseline.
Release counts cover the trailing 24 months ending 2026-09-07.
Download counts are `pypistats.org` last-month figures.

| Package | Latest | Released | Age | Releases/24mo | Installed | Transitive deps | C or Rust extension |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [html2text](https://pypi.org/project/html2text/) | 2025.4.15 | 2025-04-15 | 510 d | 1 | 164 KB | none | no, pure Python |
| [markdownify](https://pypi.org/project/markdownify/) | 1.2.3 | 2026-06-30 | 69 d | 7 | 964 KB | `beautifulsoup4`, `soupsieve`, `six`, `typing-extensions` | no |
| [lxml](https://pypi.org/project/lxml/) | 6.1.3 | 2026-09-02 | 5 d | 16 | 19 MB | none | yes, Cython over libxml2/libxslt |
| [lxml-html-clean](https://pypi.org/project/lxml-html-clean/) | 0.4.5 | 2026-05-20 | 110 d | 8 | 19 MB with lxml | `lxml` | inherits lxml's |
| [beautifulsoup4](https://pypi.org/project/beautifulsoup4/) | 4.15.0 | 2026-06-07 | 92 d | 12 | 820 KB | `soupsieve`, `typing-extensions` | no |
| [inscriptis](https://pypi.org/project/inscriptis/) | 2.7.4 | 2026-08-10 | 28 d | 9 | 22 MB | `lxml`, `requests`, `certifi`, `urllib3`, `idna`, `charset-normalizer` | inherits lxml's |
| [html-to-text](https://pypi.org/project/html-to-text/) | 1.0.0 | 2016-05-24 | 3758 d | 0 | 68 KB | none | no |
| stdlib `html.parser` | n/a | n/a | n/a | n/a | 0 | none | no |

Last month's downloads were `beautifulsoup4` 360.4M, `lxml` 346.5M, `markdownify` 62.9M, `lxml-html-clean` 18.3M, `html2text` 13.4M, `inscriptis` 0.93M, `html-to-text` 652.

### On the C extension question

Only `lxml` compiles anything.
`inscriptis` and `lxml-html-clean` inherit that.
Installing it is easier than it used to be.
`lxml` 6.1.3 publishes wheels for CPython 3.8 through 3.15, including free-threaded 3.14t and 3.15t.
The wheels cover macOS universal2 and x86_64, manylinux and musllinux for x86_64/aarch64/i686/armv7l/ppc64le/riscv64, Windows 32/64/arm64, and PyPy.
Each wheel is 3.5 MB to 8.4 MB.
The installed size is 19 MB.
The failure mode is a platform with no wheel.
There `pip` falls back to the sdist and needs libxml2 and libxslt headers plus Cython.
A zero-dependency core exists to protect exactly that class of user.
So `lxml` should not become an Epistole dependency for a job the stdlib already does adequately.

### On maintenance health

`html2text` is the outlier.
Its release history has a 1501-day gap (2020-01-16 to 2024-02-25).
It has been 510 days since 2025.4.15.
The repository is active ([last push 2025-10-28](https://github.com/Alir3z4/html2text), 2168 stars, 96 open issues).
But its release cadence does not suit a dependency in the code that sends messages.

`html-to-text` is unmaintained.
It has one release, from 2016-05-24.
Its repository has [four stars and a last push on 2016-06-07](https://github.com/emludei/html_to_text).

`inscriptis` is the best maintained of the extraction-specific candidates: 9 releases in 24 months, [last push 2026-08-31](https://github.com/weblyzard/inscriptis).
Its problem is dependencies, not upkeep.

`beautifulsoup4` is developed on [Launchpad](https://code.launchpad.net/beautifulsoup).
The [`wention/BeautifulSoup4` GitHub repo](https://github.com/wention/BeautifulSoup4) is an archived mirror, last pushed 2022-11-08.
Do not use it to judge maintenance.

## Licences

| Package | Licence | Source |
| --- | --- | --- |
| html2text | **GPL-3.0-or-later** | [`pyproject.toml`](https://github.com/Alir3z4/html2text/blob/master/pyproject.toml), [`COPYING`](https://github.com/Alir3z4/html2text/blob/master/COPYING) |
| markdownify | MIT | [`LICENSE`](https://github.com/matthewwithanm/python-markdownify/blob/develop/LICENSE) |
| lxml | BSD-3-Clause | [PyPI metadata](https://pypi.org/project/lxml/), [repo](https://github.com/lxml/lxml) |
| lxml-html-clean | BSD-3-Clause | [repo](https://github.com/fedora-python/lxml_html_clean/) |
| beautifulsoup4 | MIT | `beautifulsoup4-4.15.0.dist-info/licenses/LICENSE` |
| inscriptis | Apache-2.0 | [`pyproject.toml`](https://github.com/weblyzard/inscriptis/blob/master/pyproject.toml) |
| html-to-text | Apache-2.0 | [repo](https://github.com/emludei/html_to_text) |

One licence needs attention: **html2text is GPL-3.0-or-later**.
Epistole is MIT.
A GPL dependency does not relicense Epistole's own source.
But importing GPL code at runtime creates a combined-work argument that Epistole's downstream users would have to evaluate.
Even as an optional extra, it adds a licence decision to installation.
`inscriptis` (Apache-2.0) produces better output, and the stdlib approach produces comparable output.
So there is no reason to accept that.

If a caller wants html2text, they install it and pass `html2text.html2text` to `text_renderer`.
Their project then declares the dependency, and their licence review covers it.

## Caller-supplied plain text

Caller-supplied plain text should be the primary path.
`text` is the input.
Derivation runs only when `text` is absent.

Every Python mail library surveyed takes the plain text as an input, and none derives it:

- [red-mail](https://github.com/Miksus/red-mail): `EmailSender.send(html=..., text=...)` takes two independent parameters and does no derivation.
- [python-emails](https://github.com/lavr/python-emails): `Message(html=..., text=...)` takes both, and `set_text` just stores the string.
- [Django](https://docs.djangoproject.com/en/stable/topics/email/): `EmailMultiAlternatives(subject, body, ...)` takes the plain text as `body`, then `attach_alternative(html, "text/html")` adds the HTML.
  `send_mail`'s `html_message` is keyword-only and the plain `message` is positional, so the caller must supply text.
- Flask-Mail: `Message(body=..., html=...)` takes both.

The closest precedent for derivation is Node, and it is instructive.
`nodemailer` does not derive either, but an official optional plugin, [`nodemailer-html-to-text`](https://www.npmjs.com/package/nodemailer-html-to-text), wraps the npm `html-to-text` package.
The plugin has not been published since 2021-04-22.
It pins `html-to-text@7.1.1` while upstream is on 10.0.1.
That is the maintenance cost of pinning someone else's extractor.

Epistole derives by default because otherwise most callers would send HTML-only.
But the parameter must exist.
Supplying it must skip derivation entirely rather than merging or validating.

## CSS inlining: overlap

The two do not overlap.
Every candidate here reads HTML and emits text.
CSS inlining reads HTML and emits HTML.
Neither `css-inline` nor `premailer` exposes any plain-text function.
`premailer`'s Python port has no equivalent of the Ruby gem's `to_plain_text`.

They share one indirect dependency: `lxml`.
`premailer` depends on it, and so does `inscriptis`.
If Epistole ever adds an `lxml` dependency for CSS inlining, the marginal cost of `inscriptis` drops to 46 KB.
This recommendation would then be worth revisiting.

The leading Python option is [`css-inline`](https://pypi.org/project/css-inline/) 0.21.2 (2026-08-24), which is MIT-licensed.
It is a Rust extension built on Mozilla Servo components.
It has [16 releases in 24 months](https://github.com/Stranger6667/css-inline) and 2.8M downloads/month.
It publishes `abi3` wheels for cp310+, so one wheel covers all future CPython 3.x.
The red-mail `style` extra depends on it ([PyPI metadata](https://pypi.org/project/redmail/)).
The other option, [`premailer`](https://pypi.org/project/premailer/), is BSD-3-Clause.
It has not released since 2021-08-02.
It depends on `lxml`, `cssselect`, `cssutils`, `requests` and `cachetools`.

That is a separate question for a separate issue.

## Reproduction

The fixture, the per-candidate scripts and the venvs are stored under `/tmp/epistole-h2t/` for this session only.
I installed nothing into the project venv.
I did not change `pyproject.toml`.

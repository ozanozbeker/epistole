import pytest

from epistole import html_to_text

# Every expected string here pins today's output, so any change to it is deliberate. None is a contract: ADR-0008 lets the output improve in a minor version.


def test_a_line_break_starts_a_new_line():
    assert html_to_text("<p>Data team<br>Acme Analytics</p>") == (
        "Data team\nAcme Analytics"
    )


def test_words_in_adjacent_blocks_are_kept_apart():
    html = "<div>Weekly numbers</div><div>Data team</div><hr><pre>exit status 1</pre><blockquote>Quoted</blockquote>"

    assert html_to_text(html) == (
        "Weekly numbers\nData team\n\nexit status 1\n\nQuoted"
    )


def test_a_pre_block_keeps_its_line_breaks_and_indentation():
    html = """<p>The export failed:</p>
<pre>
Traceback (most recent call last):
  File "export.py", line 12, in &lt;module&gt;

    upload(report)
ValueError: bucket not found
</pre>
<p>It retries at 06:00.</p>"""

    assert html_to_text(html) == (
        "The export failed:\n"
        "\n"
        "Traceback (most recent call last):\n"
        '  File "export.py", line 12, in <module>\n'
        "\n"
        "    upload(report)\n"
        "ValueError: bucket not found\n"
        "\n"
        "It retries at 06:00."
    )


def test_a_br_inside_a_pre_block_ends_the_line():
    assert html_to_text("<pre>exit status 1<br>  retrying in 60s</pre>") == (
        "exit status 1\n  retrying in 60s"
    )


def test_a_pandoc_code_block_keeps_its_code_and_drops_its_line_anchors():
    # pandoc 3.11 wrote this for a fenced Python block and an indented block.
    html = """<p>Intro text.</p>
<div class="sourceCode" id="cb1"><pre
class="sourceCode python"><code class="sourceCode python"><span id="cb1-1"><a href="#cb1-1" aria-hidden="true" tabindex="-1"></a><span class="im">import</span> polars <span class="im">as</span> pl</span>
<span id="cb1-2"><a href="#cb1-2" aria-hidden="true" tabindex="-1"></a></span>
<span id="cb1-3"><a href="#cb1-3" aria-hidden="true" tabindex="-1"></a></span>
<span id="cb1-4"><a href="#cb1-4" aria-hidden="true" tabindex="-1"></a><span class="kw">def</span> total(df):</span>
<span id="cb1-5"><a href="#cb1-5" aria-hidden="true" tabindex="-1"></a>    <span class="cf">return</span> df.<span class="bu">sum</span>()</span></code></pre></div>
<pre><code>plain indented block
  with more indent</code></pre>
"""

    assert html_to_text(html) == (
        "Intro text.\n"
        "\n"
        "import polars as pl\n"
        "\n"
        "\n"
        "def total(df):\n"
        "    return df.sum()\n"
        "\n"
        "plain indented block\n"
        "  with more indent"
    )


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<a href="mailto:data@example.com">data@example.com</a>', "data@example.com"),
        (
            '<a href="https://example.com">https://example.com</a>',
            "https://example.com",
        ),
    ],
)
def test_a_link_labelled_with_its_own_address_is_written_once(html: str, expected: str):
    assert html_to_text(html) == expected


def test_a_link_without_an_href_is_written_as_its_label():
    assert html_to_text('<a name="top">Weekly numbers</a>') == "Weekly numbers"


def test_a_list_item_holding_a_paragraph_is_still_marked():
    assert html_to_text("<ol><li><p>First</p></li><li><p>Second</p></li></ol>") == (
        "- First\n\n- Second"
    )


def test_empty_cells_are_kept_so_columns_line_up():
    html = """
    <table>
      <tr><th></th><th>Signups</th><th>Change</th></tr>
      <tr><th>Paid</th><td></td><td>-3%</td></tr>
      <tr><td>&nbsp;</td><td></td></tr>
    </table>
    """

    assert html_to_text(html) == "| Signups | Change\nPaid | | -3%"


def test_only_the_title_of_an_unclosed_head_is_dropped():
    assert (
        html_to_text("<head><title>Weekly numbers</title><p>Hi Ada,</p>") == "Hi Ada,"
    )


def test_entities_are_decoded():
    assert html_to_text(
        "<p>Caf&eacute;&nbsp;&amp; bar: &#8364;5 &middot; &#x2212;3%</p>"
    ) == ("Café & bar: €5 · \u22123%")


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<",
        "&",
        "</",
        "<!",
        "<?",
        "<p>unclosed <b>bold <i>italic",
        "</div></p></a>stray end tags",
        '<a href="https://example.com">unclosed link</p><p>next',
        "<table><td>a cell with no row<tr>",
        "<![foo]>an unknown marked section",
        "<![ bogus",
        "<!-- an unterminated comment",
        '<div class="an unterminated attribute',
        "<style>an unclosed style",
        "&#99999999; &#xZZ; &bogus; &",
        "<svg><![CDATA[x > y]]></svg>",
    ],
)
def test_html_to_text_never_raises_on_malformed_html(html: str):
    assert isinstance(html_to_text(html), str)


def test_a_rendered_report_matches_the_pinned_text():
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Weekly numbers</title>
<style>
  body { font-family: Helvetica, Arial, sans-serif; }
  td, th { padding: 4px 8px; }
</style>
</head>
<body>
<!--[if mso]><table><tr><td><![endif]-->
<script>track("open")</script>
<h1>Weekly numbers</h1>
<p>Hi Ada,</p>
<p>Signups rose 12% this week. The full report is <a href="https://reports.example.com/weekly?week=38&amp;team=growth">online</a>.</p>
<h2>Highlights</h2>
<ul>
  <li>Mobile signups passed desktop.</li>
  <li>The <a href="https://docs.example.com/funnel">new funnel</a> shipped.</li>
</ul>
<img src="cid:signups.png" alt="Signups by day">
<table>
  <thead><tr><th>Channel</th><th>Signups</th><th>Change</th></tr></thead>
  <tbody>
    <tr><td>Organic</td><td>1,240</td><td>+8%</td></tr>
    <tr><td>Paid</td><td>310</td><td>&minus;3%</td></tr>
  </tbody>
  <tfoot><tr><td>Total</td><td>1,550</td><td></td></tr></tfoot>
</table>
<p>Questions? Write to <a href="mailto:data@example.com">data@example.com</a>.</p>
<p>Data team &middot; <a href="https://example.com/unsubscribe?u=abc123">Unsubscribe</a></p>
<img src="https://t.example.com/open.gif" width="1" height="1" alt="">
<!--[if mso]></td></tr></table><![endif]-->
</body>
</html>
"""

    assert html_to_text(html) == (
        "Weekly numbers\n"
        "\n"
        "Hi Ada,\n"
        "\n"
        "Signups rose 12% this week. The full report is online <https://reports.example.com/weekly?week=38&team=growth>.\n"
        "\n"
        "Highlights\n"
        "\n"
        "- Mobile signups passed desktop.\n"
        "- The new funnel <https://docs.example.com/funnel> shipped.\n"
        "\n"
        "[Signups by day]\n"
        "\n"
        "Channel | Signups | Change\n"
        "Organic | 1,240 | +8%\n"
        "Paid | 310 | \u22123%\n"
        "Total | 1,550 |\n"
        "\n"
        "Questions? Write to data@example.com.\n"
        "\n"
        "Data team · Unsubscribe <https://example.com/unsubscribe?u=abc123>"
    )

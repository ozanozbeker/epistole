"""`html_to_text` derives plain text from HTML on the stdlib `html.parser`, with no dependency. `Message` uses it unless the caller supplies `text=` or `text_renderer=`. Both `html_to_text` and the `data:` rewrite in `_message.py` parse with a subclass of `Parser`, so both skip the same comments."""

from html.parser import HTMLParser
from typing import override

_SKIPPED = frozenset({"script", "style", "title"})
"""A <head> holds text only in these, so skipping them drops the head even when it is never closed."""

_LINES = frozenset({"div", "li", "tr"})
"""Each of these block elements ends the line."""

_PARAGRAPHS = frozenset(
    {
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "ol",
        "p",
        "pre",
        "table",
        "ul",
    }
)
"""Each of these ends the line and leaves a blank line before the next."""


def html_to_text(html: str, /) -> str:
    """Derive plain text from `html`.

    It writes a link as `label <url>`, or as the label alone when the label is already the URL or the `mailto:` address, or when the URL is a fragment such as `#top`. It keeps the line breaks and indentation of a `<pre>` block, such as a code block or a log. It starts a list item with `- `. It writes a table row on one line with ` | ` between its cells. It writes empty cells too, so it never shifts a value into the wrong column. It writes an image as its alt text in brackets. It drops `<head>`, `<style>`, `<script>`, `<title>`, and comments. It decodes entities. It returns `""` for HTML that holds no text, such as a lone image with no alt text.

    It never raises on malformed HTML. The output is best effort and not a contract, so it may change in a minor version. Pass `text=` to `Message` when the exact text matters. See ADR-0008.

    Examples
    --------
    ```python
    from epistole import html_to_text

    html = '<p>The report is <a href="https://example.com/q3">online</a>.</p>'
    html_to_text(html)  # "The report is online <https://example.com/q3>."
    ```
    """
    extractor = _Extractor()
    extractor.feed(html)
    extractor.close()
    return "\n".join(extractor.lines)


class Parser(HTMLParser):
    """A parser reads every `<![` as a comment that ends at the next `>`, as HTML5 does outside SVG and MathML."""

    @override
    def parse_html_declaration(self, i: int) -> int:
        # Without this, Python reads <![CDATA[ up to ]]>, and 3.13.0 to 3.13.3 raise AssertionError on <![foo]>.
        if self.rawdata.startswith("<![", i):
            return self.parse_bogus_comment(i)

        return super().parse_html_declaration(i)


class _Extractor(Parser):
    """An extractor collects the plain text of the HTML it is fed, one line at a time."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self._cells: list[list[str]] = [[]]
        self._blank = False
        self._marker = ""
        self._skip_depth = 0
        self._pre: list[str] | None = None
        self._href: str | None = None
        self._label: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED:
            self._skip_depth += 1
        self._break(tag)
        if tag == "pre" and self._pre is None:
            self._pre = []
        elif tag == "li":
            self._marker = "- "
        elif tag in {"td", "th"}:
            self._cells.append([])
        elif tag == "br" and self._pre is not None:
            self._write("\n")
        elif tag == "br" and not self._flush():
            # A <br> on an empty line, such as the second of two in a row, makes a blank line.
            self._blank = True
        elif tag == "a":
            self._close_link()
            href = (dict(attrs).get("href") or "").strip()
            # A fragment such as #top names a place in the HTML, which the plain text lacks.
            self._href = href if href and not href.startswith("#") else None
        elif tag == "img" and (alt := (dict(attrs).get("alt") or "").strip()):
            self._write(f" [{alt}] ")

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "a":
            self._close_link()
        if tag == "pre":
            self._flush_pre()
        self._break(tag)
        if tag in {"li", "ol", "ul"}:
            self._marker = ""

    @override
    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._write(data)

    @override
    def close(self) -> None:
        super().close()
        self._close_link()
        self._flush_pre()
        self._flush()

    def _write(self, text: str) -> None:
        """Add `text` to the open `<pre>` or the current cell, and to the open link's label."""
        (self._cells[-1] if self._pre is None else self._pre).append(text)
        if self._href is not None:
            self._label.append(text)

    def _close_link(self) -> None:
        """Write the open link's URL after its label, unless the label already shows it."""
        href, self._href = self._href, None
        label = _collapse("".join(self._label))
        self._label = []
        if href is not None and label not in {href, href.removeprefix("mailto:")}:
            self._write(f" <{href}>")

    def _break(self, tag: str) -> None:
        """End the current line when `tag` is a block element, and leave a blank line after a paragraph."""
        if tag in _LINES or tag in _PARAGRAPHS:
            self._flush()
            self._blank |= tag in _PARAGRAPHS

    def _flush(self) -> bool:
        """End the current line, and return whether it held text."""
        cells = [_collapse("".join(cell)) for cell in self._cells]
        self._cells = [[]]
        # The first entry holds the text before a row's first cell, which is whitespace in a table.
        if not cells[0]:
            del cells[0]
        if not any(cells):
            return False

        self._add([_collapse(" | ".join(cells))])
        return True

    def _flush_pre(self) -> None:
        """Add the text of the open `<pre>` block, if any, keeping its line breaks and indentation."""
        if self._pre is None:
            return

        lines = [line.rstrip() for line in "".join(self._pre).splitlines()]
        self._pre = None
        if text := "\n".join(lines).strip("\n"):
            self._add(text.split("\n"))

    def _add(self, lines: list[str]) -> None:
        """Append `lines`, after the blank line that is due, with the list marker on the first."""
        if self._blank and self.lines:
            self.lines.append("")
        self.lines.append(self._marker + lines[0])
        self.lines.extend(lines[1:])
        self._blank = False
        self._marker = ""


def _collapse(text: str) -> str:
    """Collapse each run of whitespace in `text` to one space, and strip both ends."""
    return " ".join(text.split())

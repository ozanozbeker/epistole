import contextlib
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from epistole import (
    Backend,
    GmailBackend,
    GraphBackend,
    MemoryBackend,
    Message,
    SMTPBackend,
    Transport,
)

ROOT = Path(__file__).parents[1]
PAGES = [ROOT / "README.md", *sorted((ROOT / "user_guide").glob("*.qmd"))]
"""The README and the user guide pages, whose Python blocks the test runs."""
EXAMPLE = re.compile(r"^#+ ([^\n]+)$|^```python\n(.*?)^```$", re.MULTILINE | re.DOTALL)
"""A heading, or a Python block. A block with a filename is a script the reader saves and runs, so it does not match."""
RAISES = {"Kept a connection past its `with`": ValueError}
"""The guide shows the example under each of these headings raising."""

FILES = {
    "kpis.html": b"<p>Daily KPIs</p>",
    "logo.png": b"\x89PNG\r\n\x1a\n",
    "weekly.html": b"<p>Weekly numbers</p>",
    "weekly.pdf": b"%PDF-1.7",
    "weekly.txt": b"Weekly numbers",
}
"""The examples read each of these from the working directory."""


def examples() -> list[tuple[str, str]]:
    """Return each Python block in the pages, with the heading above it."""
    found: list[tuple[str, str]] = []
    for page in PAGES:
        heading = ""
        for title, code in EXAMPLE.findall(page.read_text(encoding="utf-8")):
            if title:
                heading = title
            else:
                found.append((heading, code))

    return found


def test_every_example_runs(
    subtests: pytest.Subtests, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Each real backend keeps its constructor's checks and sends through a MemoryBackend transport.
    memory = MemoryBackend()

    def open_memory(self: Backend) -> Transport:
        return memory._open()

    for backend in (SMTPBackend, GmailBackend, GraphBackend):
        monkeypatch.setattr(backend, "_open", open_memory)

    monkeypatch.chdir(tmp_path)
    for name, data in FILES.items():
        (tmp_path / name).write_bytes(data)

    # The examples read their secrets under `.env.example`'s names, so any other name raises KeyError.
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            monkeypatch.setenv(name, value.strip('"'))

    # The examples share one namespace, as cells in a notebook do, and assume these three names.
    namespace: dict[str, object] = {
        "html": "<p>Weekly numbers</p>",
        "message": Message(text="Weekly numbers").to("boss@corp.example"),
        "subscribers": [
            SimpleNamespace(email=f"reader{n}@corp.example") for n in range(3)
        ],
    }
    for heading, code in examples():
        with subtests.test(heading):
            raises = RAISES.get(heading)
            with pytest.raises(raises) if raises else contextlib.nullcontext():
                exec(code, namespace)  # noqa: S102

    assert memory.submissions

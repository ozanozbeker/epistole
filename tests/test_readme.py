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

README = Path(__file__).parents[1] / "README.md"
EXAMPLE = re.compile(r"^#+ ([^\n]+)$|^```python\n(.*?)^```$", re.MULTILINE | re.DOTALL)
RAISES = {"Kept a connection past its `with`": ValueError}
"""The README shows the example under each of these headings raising."""

FILES = {
    "kpis.html": b"<p>Daily KPIs</p>",
    "logo.png": b"\x89PNG\r\n\x1a\n",
    "weekly.html": b"<p>Weekly numbers</p>",
    "weekly.pdf": b"%PDF-1.7",
    "weekly.txt": b"Weekly numbers",
}
"""The README reads each of these from the working directory."""


def examples() -> list[tuple[str, str]]:
    """Return each Python block in the README, with the heading above it."""
    heading = ""
    found: list[tuple[str, str]] = []
    for title, code in EXAMPLE.findall(README.read_text(encoding="utf-8")):
        if title:
            heading = title
        else:
            found.append((heading, code))

    return found


def test_every_readme_example_runs(
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

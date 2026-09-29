import ast
import importlib.metadata
import importlib.resources
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

import epistole
from epistole import exceptions, gmail, graph, smtp

SPEC = Path(__file__).parents[1] / "docs" / "spec.md"
EXPORTS = re.compile(r"^# (epistole\S*)\n__all__ = (\[.*?\])", re.MULTILINE | re.DOTALL)
REQUIREMENT = re.compile(
    r"(?P<name>[\w.-]+(?:\[[\w,]+\])?)[^;]*; extra == '(?P<extra>\w+)'"
)
"""Match one requirement in the metadata: its name with any extras, then the extra that installs it."""


def test_the_package_imports():
    assert epistole.__name__ == "epistole"


def test_the_package_has_a_typing_marker():
    # The editable install reads src/, so this catches a deleted marker but not a wheel without one.
    marker = importlib.resources.files("epistole").joinpath("py.typed")
    assert marker.is_file()


def test_the_core_imports_without_the_markdown_extra():
    # A fresh interpreter, because an earlier test may already have imported markdown_it here.
    code = "import sys, epistole._rfc5322; assert 'markdown_it' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603


def test_the_http_backends_import_without_any_extra():
    # None in sys.modules makes an import raise, as if the extra were not installed.
    code = "import sys; sys.modules.update(dict.fromkeys(['httpx2', 'google.auth', 'msal', 'markdown_it'])); from epistole import GmailBackend, GraphBackend"
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603


def test_every_dependency_belongs_to_an_extra():
    requirements = importlib.metadata.requires("epistole") or []

    assert all("extra ==" in requirement for requirement in requirements)


def test_each_extra_installs_the_packages_the_spec_lists():
    # The dev group installs every extra, so only the metadata shows a package missing from one.
    installs: dict[str, set[str]] = {}
    for requirement in importlib.metadata.requires("epistole") or []:
        match = REQUIREMENT.fullmatch(requirement)
        assert match is not None, requirement
        installs.setdefault(match["extra"], set()).add(match["name"])

    assert installs == {
        "gmail": {"google-auth", "httpx2"},
        "graph": {"httpx2", "msal"},
        "markdown": {"markdown-it-py"},
        "all": {"epistole[gmail,graph,markdown]"},
    }


def test_epistole_re_exports_no_error_class_and_not_httpx2():
    bound = vars(epistole)

    assert "httpx2" not in bound
    assert [
        name
        for name, value in bound.items()
        if isinstance(value, type) and issubclass(value, BaseException)
    ] == []


@pytest.mark.parametrize("module", [epistole, exceptions])
def test_a_module_exports_exactly_what_the_spec_lists(module: ModuleType):
    lists = dict(EXPORTS.findall(SPEC.read_text(encoding="utf-8")))

    assert module.__all__ == ast.literal_eval(lists[module.__name__])


@pytest.mark.parametrize(
    ("module", "backend", "credentials"),
    [
        (smtp, "SMTPBackend", {"OAuth", "Password"}),
        (gmail, "GmailBackend", {"AuthorizedUser", "ServiceAccount"}),
        (graph, "GraphBackend", {"Certificate", "ClientSecret", "ManagedIdentity"}),
    ],
)
def test_a_backend_module_defines_its_backend_and_its_credentials(
    module: ModuleType, backend: str, credentials: set[str]
):
    assert set(module.__all__) == {backend, *credentials}
    assert {getattr(module, name).__module__ for name in module.__all__} == {
        module.__name__
    }
    assert getattr(epistole, backend) is getattr(module, backend)

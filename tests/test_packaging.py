import importlib.resources
import subprocess
import sys

import epistole


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


def test_the_gmail_backend_imports_without_its_extra():
    # None in sys.modules makes an import raise, as if the extra were not installed.
    code = "import sys; sys.modules.update(dict.fromkeys(['httpx2', 'google.auth'])); from epistole import GmailBackend"
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603


def test_the_graph_backend_imports_without_its_extra():
    code = "import sys; sys.modules.update(dict.fromkeys(['httpx2', 'msal'])); from epistole import GraphBackend"
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603

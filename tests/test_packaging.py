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

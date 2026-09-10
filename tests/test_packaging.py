import importlib.resources

import epistole


def test_the_package_imports():
    assert epistole.__name__ == "epistole"


def test_the_package_has_a_typing_marker():
    # Under the editable install this reads src/, so it guards the marker
    # against deletion but says nothing about what a built wheel contains.
    marker = importlib.resources.files("epistole").joinpath("py.typed")
    assert marker.is_file()

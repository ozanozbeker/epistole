import pytest

from epistole import Address


def test_an_address_writes_the_display_name_form():
    assert (
        Address("Ada Lovelace", "ada@example.com") == "Ada Lovelace <ada@example.com>"
    )


def test_an_address_is_a_string():
    assert isinstance(Address("Ada Lovelace", "ada@example.com"), str)


def test_an_address_quotes_a_name_that_needs_it():
    assert (
        Address("Lovelace, Ada", "ada@example.com")
        == '"Lovelace, Ada" <ada@example.com>'
    )


def test_an_address_encodes_a_non_ascii_name():
    encoded = "=?utf-8?q?Ada_L=C3=B8velace?= <ada@example.com>"
    assert Address("Ada Løvelace", "ada@example.com") == encoded


def test_an_empty_name_leaves_the_address_bare():
    assert Address("", "ada@example.com") == "ada@example.com"


def test_a_non_ascii_address_raises_with_the_encode_error_as_cause():
    with pytest.raises(ValueError, match="ASCII") as caught:
        Address("Ada", "用户@例子.广告")

    assert isinstance(caught.value.__cause__, UnicodeEncodeError)


@pytest.mark.parametrize("surrogate", [chr(0xD800), chr(0xDCFF)])
@pytest.mark.parametrize(
    ("name", "email", "argument"),
    [("Ada{}", "ada@example.com", "name"), ("Ada", "ada{}@example.com", "email")],
)
def test_a_surrogate_raises_naming_the_argument_that_holds_it(
    surrogate: str, name: str, email: str, argument: str
):
    with pytest.raises(ValueError, match=rf"^{argument}=.* holds the surrogate"):
        Address(name.format(surrogate), email.format(surrogate))


@pytest.mark.parametrize("value", [5, b"x", None], ids=["int", "bytes", "None"])
@pytest.mark.parametrize("argument", ["name", "email"])
def test_an_argument_that_is_not_a_str_raises_type_error_naming_it(
    argument: str, value: object
):
    arguments: dict[str, object] = {"name": "Ada", "email": "ada@example.com"}

    with pytest.raises(TypeError, match=rf"^{argument}="):
        Address(**arguments | {argument: value})  # pyrefly: ignore

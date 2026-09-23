import re
import sys

import pytest

from epistole import Address, Message

ADDRESS_METHODS = ("to", "cc", "bcc", "reply_to")

# A quoted local part may hold an @, and Epistole never checks character set (ADR-0014).
GOOD = (
    "ada@example.com",
    "Ada Lovelace <ada@example.com>",
    '"Lovelace, Ada" <ada@example.com>',
    '"a@b"@example.com',
    '"very.unusual.@.unusual.com"@example.com',
    "用户@例子.广告",
)

# getaddresses drops the address literals although RFC 5321 allows them, so they fail too (ADR-0014).
BAD = (
    "",
    "garbage",
    "@example.com",
    "ada@",
    "ada@example.com, bob@example.com",
    "a@[192.168.1.1]",
    "a@[IPv6:::1]",
)


def test_a_message_carries_the_text_it_was_built_with():
    assert Message(text="Weekly numbers").text == "Weekly numbers"


def test_the_text_of_an_html_message_is_derived():
    message = Message(html="<p>Weekly <b>numbers</b></p>")

    assert message.html == "<p>Weekly <b>numbers</b></p>"
    assert message.text == "Weekly numbers"


def test_text_supplied_with_html_is_kept_verbatim():
    message = Message(html="<p>Weekly numbers</p>", text="  Hand-written\n\ttext  ")

    assert message.html == "<p>Weekly numbers</p>"
    assert message.text == "  Hand-written\n\ttext  "


def test_text_renderer_runs_once_on_the_html():
    calls: list[str] = []

    def render(html: str) -> str:
        calls.append(html)
        return "Rendered"

    message = Message(html="<p>Weekly numbers</p>", text_renderer=render)
    message = message.to("ada@example.com").subject("Weekly numbers")

    assert message.text == "Rendered"
    assert calls == ["<p>Weekly numbers</p>"]


def test_a_message_does_not_keep_its_text_renderer():
    rendered = Message(html="<p>Weekly numbers</p>", text_renderer=lambda _: "Rendered")
    supplied = Message(html="<p>Weekly numbers</p>", text="Rendered")

    assert rendered == supplied
    assert hash(rendered) == hash(supplied)


def test_an_error_from_text_renderer_propagates_unchanged():
    error = LookupError("no template")

    def render(html: str) -> str:
        raise error

    with pytest.raises(LookupError) as raised:
        Message(html="<p>Weekly numbers</p>", text_renderer=render)

    assert raised.value is error


def test_text_renderer_returning_a_non_str_raises():
    with pytest.raises(ValueError, match="bytes"):
        Message(html="<p>Weekly numbers</p>", text_renderer=lambda _: b"Rendered")  # pyrefly: ignore


def test_text_renderer_may_return_empty_text():
    assert Message(html="<p>Weekly numbers</p>", text_renderer=lambda _: "").text == ""


@pytest.mark.parametrize(
    "html",
    ['<img src="cid:chart.png">', "<style>p { color: #333; }</style>"],
)
def test_text_derived_from_html_holding_none_is_empty(html: str):
    assert Message(html=html).text == ""


def test_a_markdown_message_renders_html_and_keeps_the_source_as_text():
    message = Message(markdown="Weekly *numbers*")

    assert message.html == "<p>Weekly <em>numbers</em></p>\n"
    assert message.text == "Weekly *numbers*"


def test_text_supplied_with_markdown_is_kept_verbatim():
    assert (
        Message(markdown="Weekly *numbers*", text="Weekly numbers").text
        == "Weekly numbers"
    )


def test_markdown_renders_on_the_commonmark_preset():
    # A table is a GFM extension, so the commonmark preset leaves it as a paragraph (ADR-0008).
    table = "| a | b |\n| - | - |\n| 1 | 2 |"

    assert Message(markdown=table).html == f"<p>{table}</p>\n"


def test_markdown_without_the_extra_raises_naming_it(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "markdown_it", None)

    with pytest.raises(ImportError, match=r"epistole\[markdown\]"):
        Message(markdown="Weekly numbers")


def test_a_text_only_message_has_no_html():
    assert Message(text="Weekly numbers").html is None


def test_messages_differing_in_html_are_not_equal():
    assert Message(html="<p>Weekly numbers</p>") != Message(
        html="<b>Weekly numbers</b>"
    )


def test_empty_text_sends_the_subject_alone():
    message = Message(text="").subject("The nightly export failed")

    assert message.text == ""
    assert message.html is None


def test_a_message_without_content_raises():
    with pytest.raises(TypeError, match="content"):
        Message()


def test_html_with_markdown_raises():
    with pytest.raises(TypeError, match="not both"):
        Message(html="<p>Weekly numbers</p>", markdown="Weekly numbers")


def test_text_renderer_with_markdown_raises():
    with pytest.raises(TypeError, match="text_renderer="):
        Message(markdown="Weekly numbers", text_renderer=lambda _: "Rendered")


def test_text_renderer_with_text_raises():
    with pytest.raises(TypeError, match="text_renderer="):
        Message(
            html="<p>Weekly numbers</p>",
            text="Weekly numbers",
            text_renderer=lambda _: "Rendered",
        )


def test_the_attributes_start_empty():
    message = Message(text="hi")

    assert message.to_ == ()
    assert message.cc_ == ()
    assert message.bcc_ == ()
    assert message.reply_to_ == ()
    assert message.subject_ is None


@pytest.mark.parametrize("method", ADDRESS_METHODS)
def test_an_address_method_reads_back_under_the_trailing_underscore(method: str):
    message = getattr(Message(text="hi"), method)("ada@example.com", "bob@example.com")

    assert getattr(message, f"{method}_") == ("ada@example.com", "bob@example.com")


def test_subject_reads_back_under_the_trailing_underscore():
    assert Message(text="hi").subject("Weekly numbers").subject_ == "Weekly numbers"


@pytest.mark.parametrize("method", [*ADDRESS_METHODS, "subject"])
def test_a_builder_method_leaves_the_receiver_unchanged(method: str):
    original = Message(text="hi")

    built = getattr(original, method)("ada@example.com")

    assert built is not original
    assert getattr(original, f"{method}_") in ((), None)


@pytest.mark.parametrize("method", ADDRESS_METHODS)
def test_an_address_method_replaces_rather_than_appends(method: str):
    message = getattr(Message(text="hi"), method)("ada@example.com")
    message = getattr(message, method)("bob@example.com")

    assert getattr(message, f"{method}_") == ("bob@example.com",)


def test_subject_replaces():
    assert Message(text="hi").subject("first").subject("second").subject_ == "second"


@pytest.mark.parametrize("method", ADDRESS_METHODS)
def test_an_address_method_needs_at_least_one_address(method: str):
    with pytest.raises(TypeError):
        getattr(Message(text="hi"), method)(*[])


@pytest.mark.parametrize("method", ADDRESS_METHODS)
@pytest.mark.parametrize("address", GOOD)
def test_an_address_method_accepts_a_structurally_sound_address(
    method: str, address: str
):
    message = getattr(Message(text="hi"), method)(address)

    assert getattr(message, f"{method}_") == (address,)


@pytest.mark.parametrize("method", ADDRESS_METHODS)
@pytest.mark.parametrize("address", BAD)
def test_an_address_method_refuses_a_structurally_unsound_address(
    method: str, address: str
):
    with pytest.raises(ValueError, match=re.escape(repr(address))):
        getattr(Message(text="hi"), method)(address)


@pytest.mark.parametrize("method", ADDRESS_METHODS)
def test_an_address_method_checks_every_address_it_is_given(method: str):
    with pytest.raises(ValueError, match=re.escape(repr("garbage"))):
        getattr(Message(text="hi"), method)("ada@example.com", "garbage")


def test_an_address_method_keeps_the_string_the_caller_wrote():
    assert Message(text="hi").to("Ada Lovelace <ada@example.com>").to_ == (
        "Ada Lovelace <ada@example.com>",
    )


def test_an_address_helper_passes_the_check():
    address = Address("Ada Lovelace", "ada@example.com")

    assert Message(text="hi").to(address).to_ == ("Ada Lovelace <ada@example.com>",)


def test_recipients_join_to_cc_and_bcc_in_that_order():
    message = (
        Message(text="hi")
        .to("ada@example.com")
        .cc("bob@example.com")
        .bcc("cleo@example.com")
        .reply_to("dana@example.com")
    )

    assert message.recipients == (
        "ada@example.com",
        "bob@example.com",
        "cleo@example.com",
    )


def test_recipients_keep_duplicates():
    message = Message(text="hi").to("ada@example.com").cc("ada@example.com")

    assert message.recipients == ("ada@example.com", "ada@example.com")


def test_two_messages_built_the_same_way_are_equal_and_hash_equal():
    first = Message(text="hi").to("ada@example.com").subject("Weekly numbers")
    second = Message(text="hi").to("ada@example.com").subject("Weekly numbers")

    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


@pytest.mark.parametrize("method", [*ADDRESS_METHODS, "subject"])
def test_messages_differing_in_one_field_are_not_equal(method: str):
    original = Message(text="hi")

    assert getattr(original, method)("ada@example.com") != original


def test_messages_differing_in_text_are_not_equal():
    assert Message(text="hi") != Message(text="bye")


def test_a_message_is_not_equal_to_a_non_message():
    assert Message(text="hi") != "hi"


def test_a_message_refuses_attribute_assignment():
    message = Message(text="hi")

    with pytest.raises(AttributeError, match="immutable"):
        message.subject_ = "Weekly numbers"


def test_a_message_refuses_attribute_deletion():
    message = Message(text="hi")

    with pytest.raises(AttributeError, match="immutable"):
        del message.subject_

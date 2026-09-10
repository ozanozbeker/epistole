import re

import pytest

from epistole import Address, Message

ADDRESS_METHODS = ("to", "cc", "bcc", "reply_to")

# Structurally sound: exactly one address, something on both sides of the last
# @. The quoted local part carries an @ of its own, and the non-ASCII address
# passes because Epistole never checks character set.
GOOD = (
    "ada@example.com",
    "Ada Lovelace <ada@example.com>",
    '"Lovelace, Ada" <ada@example.com>',
    '"a@b"@example.com',
    '"very.unusual.@.unusual.com"@example.com',
    "用户@例子.广告",
)

# The address literal is legal RFC 5321, and getaddresses drops it, so Epistole
# refuses it without having chosen to.
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


def test_empty_text_raises():
    with pytest.raises(ValueError, match="text="):
        Message(text="")


def test_a_message_without_content_raises():
    with pytest.raises(TypeError, match="content"):
        Message()


def test_the_readbacks_start_empty():
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

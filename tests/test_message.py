import re
import sys
from pathlib import Path

import pytest

from epistole import Address, Attachment, Message

ADDRESS_METHODS = ("to", "cc", "bcc", "reply_to")

PDF = b"%PDF-1.7 weekly numbers"
PNG = b"\x89PNG\r\n\x1a\n logo"
LOGO_HTML = '<p><img src="cid:logo.png" alt="Logo"></p>'
UNSUBSCRIBE = "<mailto:unsubscribe@example.com>"

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
    assert message.headers_ == {}


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
    def build() -> Message:
        return (
            Message(html=LOGO_HTML)
            .to("ada@example.com")
            .subject("Weekly numbers")
            .headers({"X-Campaign-Id": "autumn"})
            .attach(PDF, filename="weekly.pdf")
            .embed(PNG, cid="logo.png")
        )

    first, second = build(), build()

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


def test_attach_adds_an_attachment_typed_by_its_filename():
    message = Message(text="hi").attach(PDF, filename="weekly.pdf")

    assert message.attachments == (
        Attachment(
            filename="weekly.pdf",
            content_type="application/pdf",
            data=PDF,
            content_id=None,
        ),
    )


def test_attach_reads_a_path_when_called_and_names_the_attachment_after_it(
    tmp_path: Path,
):
    path = tmp_path / "weekly.pdf"
    path.write_bytes(PDF)

    message = Message(text="hi").attach(path)
    path.write_bytes(b"changed after the call")

    assert message.attachments[0].filename == "weekly.pdf"
    assert message.attachments[0].data == PDF


def test_filename_overrides_the_name_of_a_path(tmp_path: Path):
    path = tmp_path / "tmp4f2a.pdf"
    path.write_bytes(PDF)

    message = Message(text="hi").attach(path, filename="weekly.pdf")

    assert message.attachments[0].filename == "weekly.pdf"


def test_attach_reads_a_binary_file_and_leaves_it_open(tmp_path: Path):
    path = tmp_path / "weekly.pdf"
    path.write_bytes(PDF)

    with path.open("rb") as file:
        message = Message(text="hi").attach(file, filename="weekly.pdf")

        assert not file.closed

    assert message.attachments[0].data == PDF


def test_attach_never_names_an_attachment_after_an_open_file(tmp_path: Path):
    path = tmp_path / "weekly.pdf"
    path.write_bytes(PDF)

    with path.open("rb") as file:
        with pytest.raises(TypeError, match="filename="):
            Message(text="hi").attach(file)

        assert file.tell() == 0


@pytest.mark.parametrize("filename", [None, "weekly.pdf"])
def test_a_str_source_raises_naming_path(filename: str | None):
    with pytest.raises(TypeError, match=re.escape("Path()")):
        Message(text="hi").attach("weekly.pdf", filename=filename)  # pyrefly: ignore


@pytest.mark.parametrize("source", [bytearray(PDF), memoryview(PDF)])
def test_a_mutable_buffer_raises_naming_bytes(source: bytearray | memoryview):
    with pytest.raises(TypeError, match=re.escape("bytes()")):
        Message(text="hi").attach(source, filename="weekly.pdf")  # pyrefly: ignore


def test_a_text_mode_file_raises_naming_binary_mode(tmp_path: Path):
    path = tmp_path / "weekly.csv"
    path.write_text("week,sent\n38,1200\n", encoding="utf-8")

    with (
        path.open(encoding="utf-8") as file,
        pytest.raises(TypeError, match="'rb'"),
    ):
        Message(text="hi").attach(file, filename="weekly.csv")  # pyrefly: ignore


# Every case holds PDF bytes, so a result other than application/pdf shows the bytes were never sniffed.
@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("logo.PNG", "image/png"),
        ("weekly.epistole", "application/octet-stream"),
        # mimetypes reads this as text/csv with a gzip encoding.
        ("weekly.csv.gz", "application/octet-stream"),
    ],
)
def test_attach_infers_the_content_type_from_the_filename_alone(
    filename: str, content_type: str
):
    message = Message(text="hi").attach(PDF, filename=filename)

    assert message.attachments[0].content_type == content_type


def test_content_type_overrides_the_inferred_one():
    message = Message(text="hi").attach(
        PDF, filename="weekly.bin", content_type="application/pdf"
    )

    assert message.attachments[0].content_type == "application/pdf"


@pytest.mark.parametrize(
    "content_type",
    [
        "text/csv; charset=utf-8",
        "csv",
        "text/",
        "text/csv\r\nBcc: eve@example.com",
    ],
)
def test_content_type_must_be_a_media_type_without_parameters(content_type: str):
    with pytest.raises(ValueError, match=re.escape(repr(content_type))):
        Message(text="hi").attach(PDF, filename="weekly.csv", content_type=content_type)


def test_embed_names_an_inline_image_after_its_path(tmp_path: Path):
    path = tmp_path / "logo.png"
    path.write_bytes(PNG)

    message = Message(html=LOGO_HTML).embed(path)

    assert message.inline_images == (
        Attachment(
            filename="logo.png",
            content_type="image/png",
            data=PNG,
            content_id="logo.png",
        ),
    )
    assert message.attachments == ()


@pytest.mark.parametrize(
    ("filename", "cid", "expected"),
    [
        ("logo.png", None, ("logo.png", "logo.png")),
        (None, "logo.png", ("logo.png", "logo.png")),
        ("logo.png", "header", ("logo.png", "header")),
    ],
)
def test_embed_defaults_filename_and_cid_to_each_other(
    filename: str | None, cid: str | None, expected: tuple[str, str]
):
    image = (
        Message(html=LOGO_HTML).embed(PNG, filename=filename, cid=cid).inline_images[0]
    )

    assert (image.filename, image.content_id) == expected
    assert image.content_type == "image/png"


def test_a_path_names_an_inline_image_under_another_content_id(tmp_path: Path):
    path = tmp_path / "logo.png"
    path.write_bytes(PNG)

    image = Message(html=LOGO_HTML).embed(path, cid="header").inline_images[0]

    assert (image.filename, image.content_id) == ("logo.png", "header")


def test_embed_needs_a_filename_or_a_content_id_for_bytes():
    with pytest.raises(TypeError, match="cid="):
        Message(html=LOGO_HTML).embed(PNG)


@pytest.mark.parametrize(
    ("cid", "content_type"),
    [("weekly.pdf", None), ("logo", None), ("logo.png", "application/pdf")],
)
def test_embed_needs_an_image_content_type(cid: str, content_type: str | None):
    with pytest.raises(ValueError, match=re.escape("image/*")):
        Message(html=LOGO_HTML).embed(PNG, cid=cid, content_type=content_type)


@pytest.mark.parametrize("content_type", ["image/png", "Image/PNG"])
def test_embed_takes_an_image_content_type_override_in_any_case(content_type: str):
    image = (
        Message(html=LOGO_HTML)
        .embed(PNG, cid="logo", content_type=content_type)
        .inline_images[0]
    )

    assert image.content_type == content_type


@pytest.mark.parametrize("data", [PNG + b" retina", PNG])
def test_embed_raises_on_a_content_id_the_message_already_holds(data: bytes):
    message = Message(html=LOGO_HTML).embed(PNG, cid="logo.png")

    with pytest.raises(ValueError, match=re.escape("'logo.png'")):
        message.embed(data, cid="logo.png")


def test_attach_and_embed_append_in_call_order_and_leave_the_receiver_unchanged():
    base = Message(html=LOGO_HTML)

    message = (
        base.attach(PDF, filename="weekly.pdf")
        .embed(PNG, cid="logo.png")
        .attach(PDF, filename="weekly.pdf")
        .embed(PNG, cid="footer.png")
    )

    assert [one.filename for one in message.attachments] == ["weekly.pdf", "weekly.pdf"]
    assert [one.content_id for one in message.inline_images] == [
        "logo.png",
        "footer.png",
    ]
    assert base.attachments == ()
    assert base.inline_images == ()


def test_messages_differing_in_attachments_are_not_equal():
    base = Message(html=LOGO_HTML)
    attached = base.attach(PNG, filename="logo.png")

    assert attached != base
    assert attached != base.attach(PNG, filename="header.png")
    assert base.embed(PNG, cid="logo.png") != base


def test_headers_reads_back_in_the_given_order():
    message = Message(text="hi").headers(
        {"X-Campaign-Id": "autumn", "List-Unsubscribe": UNSUBSCRIBE}
    )

    assert message.headers_ == {
        "X-Campaign-Id": "autumn",
        "List-Unsubscribe": UNSUBSCRIBE,
    }
    assert list(message.headers_) == ["X-Campaign-Id", "List-Unsubscribe"]


def test_messages_differing_in_headers_are_not_equal():
    base = Message(text="hi")
    tagged = base.headers({"X-Campaign-Id": "autumn"})

    assert tagged != base
    assert tagged != base.headers({"X-Campaign-Id": "spring"})


def test_headers_replaces_the_whole_set():
    message = Message(text="hi").headers({"X-Campaign-Id": "autumn", "X-Segment": "b"})

    assert message.headers({"X-Campaign-Id": "spring"}).headers_ == {
        "X-Campaign-Id": "spring"
    }


def test_headers_copies_the_mapping_and_leaves_the_receiver_unchanged():
    mapping = {"X-Campaign-Id": "autumn"}
    base = Message(text="hi")

    message = base.headers(mapping)
    mapping["X-Campaign-Id"] = "spring"

    assert message.headers_ == {"X-Campaign-Id": "autumn"}
    assert base.headers_ == {}


def test_headers_reads_back_as_one_read_only_mapping():
    message = Message(text="hi").headers({"X-Campaign-Id": "autumn"})

    assert message.headers_ is message.headers_
    with pytest.raises(TypeError):
        message.headers_["X-Campaign-Id"] = "spring"  # pyrefly: ignore


def test_headers_takes_a_name_of_any_printable_ascii_but_colon():
    # RFC 5322 ftext is ASCII 33 to 126, and 58 is the colon.
    name = "".join(chr(code) for code in range(33, 127) if code != 58)

    assert Message(text="hi").headers({name: "autumn"}).headers_ == {name: "autumn"}


@pytest.mark.parametrize(
    "name",
    ["", "X Campaign", "X:Campaign", "X-Café", "X-Campaign\r\nBcc", "X-\x7f"],
)
def test_headers_raises_on_an_illegal_name(name: str):
    with pytest.raises(ValueError, match=re.escape(repr(name))):
        Message(text="hi").headers({name: "autumn"})


# The line boundaries str.splitlines() documents, each of which EmailMessage raises on.
@pytest.mark.parametrize(
    "value",
    [
        "autumn\r\nBcc: eve@example.com",
        "autumn\n",
        *(
            f"autumn{boundary}spring"
            for boundary in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"
        ),
    ],
)
def test_headers_raises_on_a_value_holding_a_line_break(value: str):
    with pytest.raises(ValueError, match="'X-Campaign-Id'"):
        Message(text="hi").headers({"X-Campaign-Id": value})


def test_headers_takes_a_non_ascii_value():
    message = Message(text="hi").headers({"X-Campaign-Id": "automne café"})

    assert message.headers_ == {"X-Campaign-Id": "automne café"}


@pytest.mark.parametrize(
    ("mapping", "match"),
    [({5: "autumn"}, "5"), ({"X-Campaign-Id": 5}, "'X-Campaign-Id'")],
)
def test_headers_raises_on_a_name_or_value_that_is_not_a_str(
    mapping: dict[object, object], match: str
):
    with pytest.raises(ValueError, match=match):
        Message(text="hi").headers(mapping)  # pyrefly: ignore


# ADR-0016 lists these names, and the casing varies because RFC 5322 names are case-insensitive.
@pytest.mark.parametrize(
    "name",
    [
        "From",
        "to",
        "CC",
        "Bcc",
        "reply-to",
        "Subject",
        "MESSAGE-ID",
        "Date",
        "Mime-Version",
        "Content-Type",
        "content-transfer-encoding",
        "Content-Id",
        "Content-Disposition",
    ],
)
def test_headers_raises_on_a_name_epistole_writes(name: str):
    with pytest.raises(ValueError, match=re.escape(repr(name))):
        Message(text="hi").headers({name: "autumn"})


def test_headers_matches_the_names_epistole_writes_exactly():
    message = Message(text="hi").headers({"In-Reply-To": "<1@example.com>"})

    assert message.headers_ == {"In-Reply-To": "<1@example.com>"}


def test_headers_needs_at_least_one_custom_header():
    with pytest.raises(ValueError, match="at least one"):
        Message(text="hi").headers({})


def test_headers_raises_on_a_name_repeated_in_another_case():
    with pytest.raises(ValueError, match="'x-campaign-id'"):
        Message(text="hi").headers(
            {"X-Campaign-Id": "autumn", "x-campaign-id": "spring"}
        )

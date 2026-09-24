from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.message import EmailMessage, MIMEPart
from email.policy import default

import pytest

from epistole import Message, Submission
from epistole._rfc5322 import build

MESSAGE_ID = "<179021486392.66219.11904006491029159968@example.com>"
DATE = datetime(2026, 9, 23, 21, 54, 23, tzinfo=timezone(timedelta(hours=-4)))

PDF = b"%PDF-1.7 weekly numbers"
CSV = b"region,total\r\nnorth,12\r\n"
PNG = b"\x89PNG\r\n\x1a\n logo"
LOGO_HTML = '<p><img src="cid:logo.png" alt="Logo"></p>'
UNSUBSCRIBE = "<mailto:unsubscribe@example.com>"
NON_ASCII = "用户@例子.广告"


def submission(message: Message) -> Submission:
    """Wrap `message` as `Connection.send` would, with a fixed id and date."""
    return Submission(
        message=message,
        from_address="Reports <reports@example.com>",
        message_id=MESSAGE_ID,
        date=DATE,
    )


def read_back(message: Message) -> EmailMessage:
    """Build `message`, and read the bytes it writes back with `email.parser`."""
    return message_from_bytes(build(submission(message)).as_bytes(), policy=default)


def unfolded(message: Message) -> bytes:
    """Build `message`, and return the bytes it writes with each CRLF before a space removed, which RFC 5322 calls unfolding.

    `email.parser` decodes an encoded-word even where RFC 2047 forbids one, so only the bytes show it.
    """
    return build(submission(message)).as_bytes().replace(b"\r\n ", b" ")


def lines(part: MIMEPart) -> list[str]:
    """Return the text of `part` as lines, because the generator ends every line with CRLF including the last."""
    return part.get_content().splitlines()


# --- Content -----------------------------------------------------------------


def test_a_text_only_message_builds_to_one_plain_text_part_with_no_unset_field():
    parsed = read_back(Message(text="Weekly numbers").to("ada@example.com"))

    assert parsed.get_content_type() == "text/plain"
    assert lines(parsed) == ["Weekly numbers"]
    assert not {"Cc", "Bcc", "Reply-To", "Subject"} & set(parsed.keys())


def test_an_html_message_builds_its_plain_text_before_its_html():
    parsed = read_back(
        Message(html="<p>Weekly <b>numbers</b></p>").to("ada@example.com")
    )

    assert [part.get_content_type() for part in parsed.walk()] == [
        "multipart/alternative",
        "text/plain",
        "text/html",
    ]
    plain, html = parsed.iter_parts()
    assert lines(plain) == ["Weekly numbers"]
    assert lines(html) == ["<p>Weekly <b>numbers</b></p>"]


# --- Attachments and inline images -------------------------------------------


def test_attachments_read_back_with_their_names_types_and_bytes():
    parsed = read_back(
        Message(html="<p>Weekly numbers</p>")
        .to("ada@example.com")
        .attach(PDF, filename="rapport-financiér.pdf")
        .attach(CSV, filename="weekly.csv")
    )

    assert parsed.get_content_type() == "multipart/mixed"
    assert [
        (part.get_filename(), part.get_content_type(), part.get_payload(decode=True))
        for part in parsed.iter_attachments()
    ] == [
        ("rapport-financiér.pdf", "application/pdf", PDF),
        ("weekly.csv", "text/csv", CSV),
    ]


def test_an_inline_image_sits_beside_the_html_that_names_it():
    parsed = read_back(
        Message(html=LOGO_HTML).to("ada@example.com").embed(PNG, filename="logo.png")
    )

    assert [part.get_content_type() for part in parsed.walk()] == [
        "multipart/alternative",
        "text/plain",
        "multipart/related",
        "text/html",
        "image/png",
    ]
    *_, image = parsed.walk()
    assert (image.get_filename(), image.get_payload(decode=True)) == ("logo.png", PNG)


def test_a_text_only_message_still_carries_its_inline_images():
    parsed = read_back(
        Message(text="Weekly numbers")
        .to("ada@example.com")
        .embed(PNG, filename="logo.png")
    )

    _, plain, image = parsed.walk()
    assert lines(plain) == ["Weekly numbers"]
    assert (image["Content-ID"], image.get_payload(decode=True)) == ("<logo.png>", PNG)


def test_each_part_carries_its_content_type_and_only_an_inline_image_a_content_id():
    parsed = read_back(
        Message(html=LOGO_HTML)
        .to("ada@example.com")
        .embed(PNG, filename="logo.png")
        .attach(PDF, filename="weekly.pdf")
    )

    assert all("Content-Type" in part for part in parsed.walk())
    parts = {part.get_content_type(): part for part in parsed.walk()}
    image, pdf = parts["image/png"], parts["application/pdf"]
    assert (image["Content-ID"], image.get_content_disposition()) == (
        "<logo.png>",
        "inline",
    )
    assert (pdf["Content-ID"], pdf.get_content_disposition()) == (None, "attachment")


def test_a_content_id_too_long_to_fold_is_written_unchanged():
    cid = f"quarterly-revenue-by-region-and-product-line-{'x' * 27}.png"
    message = Message(html=f'<img src="cid:{cid}">').to("ada@example.com")

    assert f"Content-ID: <{cid}>".encode() in unfolded(message.embed(PNG, filename=cid))


# --- Headers -----------------------------------------------------------------


def test_the_addressing_and_subject_read_back_as_written():
    parsed = read_back(
        Message(text="Weekly numbers")
        .to("ada@example.com", "Zoë <zoe@example.com>")
        .cc('"Lovelace, Ada" <lovelace@example.com>')
        .bcc("dan@example.com")
        .reply_to("help@example.com")
        .subject("Café numbers")
    )

    assert [
        parsed[name] for name in ("From", "To", "Cc", "Bcc", "Reply-To", "Subject")
    ] == [
        "Reports <reports@example.com>",
        "ada@example.com, Zoë <zoe@example.com>",
        '"Lovelace, Ada" <lovelace@example.com>',
        "dan@example.com",
        "help@example.com",
        "Café numbers",
    ]


@pytest.mark.parametrize("method", ["to", "cc", "bcc", "reply_to"])
def test_a_non_ascii_address_is_written_in_utf_8(method: str):
    message = Message(text="Weekly numbers").to("ada@example.com")

    assert NON_ASCII.encode() in unfolded(getattr(message, method)(NON_ASCII))


def test_a_non_ascii_from_address_is_written_in_utf_8():
    message = Message(text="Weekly numbers").to("ada@example.com")

    written = build(replace(submission(message), from_address=NON_ASCII)).as_bytes()

    assert f"From: {NON_ASCII}".encode() in written


def test_the_message_id_and_date_come_from_the_submission():
    parsed = read_back(Message(text="Weekly numbers").to("ada@example.com"))

    assert parsed["Message-ID"] == MESSAGE_ID
    assert parsed["Date"] == "Wed, 23 Sep 2026 21:54:23 -0400"


# --- Custom headers ----------------------------------------------------------


def test_custom_headers_follow_epistoles_own_in_the_callers_order():
    parsed = read_back(
        Message(html="<p>Weekly numbers</p>")
        .to("ada@example.com")
        .headers({"X-Campaign-Id": "autumn", "List-Unsubscribe": UNSUBSCRIBE})
        .attach(PDF, filename="weekly.pdf")
    )

    assert parsed.keys()[-2:] == ["X-Campaign-Id", "List-Unsubscribe"]
    assert [parsed["X-Campaign-Id"], parsed["List-Unsubscribe"]] == [
        "autumn",
        UNSUBSCRIBE,
    ]


def test_a_custom_header_value_too_long_to_fold_is_written_unchanged():
    url = f"<https://example.com/unsubscribe?token={'a' * 80}>"
    message = Message(text="Weekly numbers").to("ada@example.com")

    assert f"List-Unsubscribe: {url}".encode() in unfolded(
        message.headers({"List-Unsubscribe": url})
    )


def test_a_non_ascii_custom_header_value_reads_back():
    parsed = read_back(
        Message(text="Weekly numbers")
        .to("ada@example.com")
        .headers({"X-Campaign-Name": "Café d'automne"})
    )

    assert parsed["X-Campaign-Name"] == "Café d'automne"

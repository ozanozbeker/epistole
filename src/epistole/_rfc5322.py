"""`build` turns a submission into the RFC 5322 message that SMTP writes and Gmail sends as `raw`. Graph never calls it, because every Graph request is JSON (ADR-0012). It is in the core, so it takes no dependency."""

from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP
from typing import TYPE_CHECKING

from epistole._address import addr_spec

if TYPE_CHECKING:
    from email.message import MIMEPart

    from epistole._backend import Submission
    from epistole._message import Message


def build(submission: Submission, /) -> EmailMessage:
    """Return the RFC 5322 message for `submission`.

    It holds `Bcc`, because Gmail sends to the addresses in `To`, `Cc`, and `Bcc`. `smtplib`'s `send_message` deletes that header before it writes, so SMTP sends to the bcc addresses without naming them.
    """
    message: Message = submission.message
    # RFC 2047 allows an encoded-word in a display name but not in an addr-spec, and Epistole keeps no table of which custom headers allow one (ADR-0014, ADR-0016).
    ascii_only: bool = all(
        addr_spec(one).isascii()
        for one in (submission.from_address, *message.recipients, *message.reply_to_)
    ) and all(value.isascii() for value in message.headers_.values())
    # SMTP ends each line with CRLF. refold_source="none" writes a value stored with set_raw, the parser's API, as it stands.
    # With cte_type="7bit", EmailMessage writes non-ASCII text as quoted-printable or base64, so SMTP needs no BODY=8BITMIME (ADR-0020).
    mime = EmailMessage(
        policy=SMTP.clone(refold_source="none", utf8=not ascii_only, cte_type="7bit")
    )
    mime["From"] = submission.from_address
    for name, addresses in (
        ("To", message.to_),
        ("Cc", message.cc_),
        ("Bcc", message.bcc_),
        ("Reply-To", message.reply_to_),
    ):
        if addresses:
            mime[name] = ", ".join(addresses)

    if message.subject_ is not None:
        mime["Subject"] = message.subject_

    mime["Message-ID"] = submission.message_id
    mime["Date"] = submission.date
    mime.set_content(message.text)
    # A text-only message relates its images to the plain text, so a client lists them as files (ADR-0008).
    root: MIMEPart = mime
    if message.html is not None:
        mime.add_alternative(message.html, subtype="html")
        _, root = mime.iter_parts()

    for image in message.inline_images:
        maintype, _, subtype = image.content_type.partition("/")
        # A filename makes add_related write an attachment disposition unless disposition= overrides it (ADR-0003).
        root.add_related(
            image.data, maintype, subtype, filename=image.filename, disposition="inline"
        )
        *_, part = root.iter_parts()
        # cid= writes an id too long to fold as an encoded-word, which RFC 2047 forbids there.
        part.set_raw("Content-ID", f"<{image.content_id}>")

    for attachment in message.attachments:
        maintype, _, subtype = attachment.content_type.partition("/")
        mime.add_attachment(
            attachment.data, maintype, subtype, filename=attachment.filename
        )

    for name, value in message.headers_.items():
        # Assigning writes an ASCII word too long to fold as an encoded-word, which breaks a List-Unsubscribe URL.
        mime.set_raw(name, value)

    return mime

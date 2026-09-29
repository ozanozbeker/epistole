"""Send real mail through iCloud, and through an SMTP server on localhost such as aiosmtpd, skipping each test whose account or server is absent.

Run them with `uv run --env-file .env pytest tests/test_live_smtp.py --tb=short`. A long traceback prints each frame's arguments, and `smtplib.SMTP.login` takes the app password as one.
"""

import imaplib
import os
import socket
import time
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from email.utils import parseaddr
from typing import Literal

import pytest

from epistole import Message, SendResult, SMTPBackend, smtp
from epistole.exceptions import AuthenticationError, SenderRefusedError

ADDRESS = os.environ.get("ICLOUD_ADDRESS", "")
PASSWORD = os.environ.get("ICLOUD_APP_PASSWORD", "")
CUSTOM_ADDRESS = os.environ.get("ICLOUD_CUSTOM_ADDRESS", "")
ARRIVAL_SECONDS = 120
LOCAL_PORT = 1025

icloud = pytest.mark.skipif(
    not (ADDRESS and PASSWORD), reason="set ICLOUD_ADDRESS and ICLOUD_APP_PASSWORD"
)


def listening(port: int) -> bool:
    """Return whether a server accepts connections on `port` of localhost."""
    try:
        socket.create_connection(("localhost", port), timeout=1).close()
    except OSError:
        return False
    return True


def send(
    from_address: str,
    password: str = PASSWORD,
    *,
    port: int = 587,
    security: Literal["starttls", "tls"] = "starttls",
) -> SendResult:
    """Send one message from `from_address` to the iCloud account's own inbox."""
    backend = SMTPBackend(
        "smtp.mail.me.com",
        port=port,
        security=security,
        from_address=from_address,
        credential=smtp.Password(username=ADDRESS, password=password),
    )
    return backend.send(
        Message(text="Sent by tests/test_live_smtp.py.")
        .subject("epistole live test")
        .to(ADDRESS)
    )


def received(message_id: str) -> EmailMessage:
    """Return the headers of the message with `message_id` once it reaches the inbox or the junk folder."""
    with imaplib.IMAP4_SSL("imap.mail.me.com") as imap:
        imap.login(ADDRESS, PASSWORD)
        deadline = time.monotonic() + ARRIVAL_SECONDS
        while time.monotonic() < deadline:
            for mailbox in ("INBOX", "Junk"):
                imap.select(mailbox, readonly=True)
                _, found = imap.search(None, "HEADER", "Message-ID", f'"{message_id}"')
                # imaplib returns [None], not [b""], for a search that matches nothing.
                if numbers := (found[0] or b"").split():
                    _, data = imap.fetch(numbers[-1].decode(), "(BODY.PEEK[HEADER])")
                    # An unsolicited FETCH of another message's flags can come first.
                    header = next(part for part in data if isinstance(part, tuple))
                    return message_from_bytes(header[1], policy=default)
            time.sleep(5)
    pytest.fail(f"{message_id} did not arrive within {ARRIVAL_SECONDS} seconds")


@icloud
@pytest.mark.parametrize(("port", "security"), [(587, "starttls"), (465, "tls")])
def test_icloud_keeps_the_message_id(port: int, security: Literal["starttls", "tls"]):
    result = send(ADDRESS, port=port, security=security)

    assert received(result.message_id)["Message-ID"] == result.message_id


@icloud
@pytest.mark.skipif(not CUSTOM_ADDRESS, reason="set ICLOUD_CUSTOM_ADDRESS")
def test_icloud_keeps_a_custom_domain_from_address():
    result = send(CUSTOM_ADDRESS)

    assert parseaddr(received(result.message_id)["From"])[1] == CUSTOM_ADDRESS


@icloud
def test_icloud_refuses_a_from_address_the_account_does_not_own():
    with pytest.raises(SenderRefusedError):
        send("nobody@example.com")


@icloud
def test_a_wrong_app_password_raises_authentication_error():
    with pytest.raises(AuthenticationError):
        send(ADDRESS, "not-the-app-password")


@pytest.mark.skipif(
    not listening(LOCAL_PORT),
    reason="start an SMTP server on localhost:1025, such as `uvx aiosmtpd -n -l localhost:1025`",
)
def test_a_local_server_accepts_an_anonymous_plaintext_send():
    backend = SMTPBackend(
        "localhost",
        port=LOCAL_PORT,
        security="none",
        from_address="reports@example.com",
    )

    result = backend.send(Message(text="Weekly numbers").to("ada@example.com"))

    assert result.refused == {}

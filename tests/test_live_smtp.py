"""Send real mail through iCloud and Gmail, with an app password or Gmail's OAuth, and through an SMTP server on localhost such as aiosmtpd, skipping each test whose account or server is absent.

Run them with `uv run --env-file .env pytest tests/test_live_smtp.py --tb=short`. A long traceback prints each frame's arguments, and `smtplib.SMTP.docmd` takes the app password as one, in base64.
"""

import imaplib
import os
import socket
import time
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from email.utils import parseaddr
from pathlib import Path
from typing import Literal, NamedTuple

import pytest

from epistole import Message, SendResult, SMTPBackend, smtp
from epistole.exceptions import AuthenticationError, SenderRefusedError
from epistole.gmail import AuthorizedUser


class Account(NamedTuple):
    """An account that sends through `smtp_host` and reads its own mailboxes back through `imap_host`."""

    address: str
    password: str
    smtp_host: str
    imap_host: str
    mailboxes: tuple[str, ...]


def read_account(
    prefix: str, smtp_host: str, imap_host: str, *mailboxes: str
) -> Account:
    """Read the address and app password under `prefix` from the environment."""
    # Google shows an app password as four groups of four letters.
    password = os.environ.get(f"{prefix}_APP_PASSWORD", "").replace(" ", "")
    address = os.environ.get(f"{prefix}_ADDRESS", "")
    return Account(address, password, smtp_host, imap_host, mailboxes)


ICLOUD = read_account("ICLOUD", "smtp.mail.me.com", "imap.mail.me.com", "INBOX", "Junk")
GMAIL = read_account(
    "GMAIL", "smtp.gmail.com", "imap.gmail.com", "[Gmail]/All Mail", "[Gmail]/Spam"
)
CUSTOM_ADDRESS = os.environ.get("ICLOUD_CUSTOM_ADDRESS", "")
AUTHORIZED_USER = Path(os.environ.get("GMAIL_AUTHORIZED_USER", "")).expanduser()
ARRIVAL_SECONDS = 120
LOCAL_PORT = 1025

icloud = pytest.mark.skipif(
    not (ICLOUD.address and ICLOUD.password),
    reason="set ICLOUD_ADDRESS and ICLOUD_APP_PASSWORD",
)
gmail = pytest.mark.skipif(
    not (GMAIL.address and GMAIL.password),
    reason="set GMAIL_ADDRESS and GMAIL_APP_PASSWORD",
)
ACCOUNTS = [
    pytest.param(ICLOUD, id="icloud", marks=icloud),
    pytest.param(GMAIL, id="gmail", marks=gmail),
]


def listening(port: int) -> bool:
    """Return whether a server accepts connections on `port` of localhost."""
    try:
        socket.create_connection(("localhost", port), timeout=1).close()
    except OSError:
        return False
    return True


def send(
    account: Account,
    from_address: str,
    credential: smtp.Password | smtp.OAuth | None = None,
    *,
    port: int = 587,
    security: Literal["starttls", "tls"] = "starttls",
) -> SendResult:
    """Send one message from `from_address` to the account's own inbox, with its app password unless `credential` replaces it."""
    backend = SMTPBackend(
        account.smtp_host,
        port=port,
        security=security,
        from_address=from_address,
        credential=credential or smtp.Password(account.address, account.password),
    )
    return backend.send(
        Message(text="Sent by tests/test_live_smtp.py.")
        .subject("epistole live test")
        .to(account.address)
    )


def received(account: Account, message_id: str) -> EmailMessage:
    """Return the headers of the message with `message_id` once one of the account's mailboxes holds it."""
    with imaplib.IMAP4_SSL(account.imap_host) as imap:
        imap.login(account.address, account.password)
        deadline = time.monotonic() + ARRIVAL_SECONDS
        while time.monotonic() < deadline:
            for mailbox in account.mailboxes:
                imap.select(f'"{mailbox}"', readonly=True)
                _, found = imap.search(None, "HEADER", "Message-ID", f'"{message_id}"')
                # imaplib returns [None], not [b""], for a search that matches nothing.
                if numbers := (found[0] or b"").split():
                    _, data = imap.fetch(numbers[-1].decode(), "(BODY.PEEK[HEADER])")
                    # An unsolicited FETCH of another message's flags can come first.
                    header = next(part for part in data if isinstance(part, tuple))
                    return message_from_bytes(header[1], policy=default)
            time.sleep(5)
    pytest.fail(f"{message_id} did not arrive within {ARRIVAL_SECONDS} seconds")


@pytest.mark.parametrize("account", ACCOUNTS)
@pytest.mark.parametrize(("port", "security"), [(587, "starttls"), (465, "tls")])
def test_the_service_keeps_the_message_id(
    account: Account, port: int, security: Literal["starttls", "tls"]
):
    result = send(account, account.address, port=port, security=security)

    assert received(account, result.message_id)["Message-ID"] == result.message_id


@pytest.mark.parametrize("account", ACCOUNTS)
def test_a_wrong_app_password_raises_authentication_error(account: Account):
    with pytest.raises(AuthenticationError):
        send(account, account.address, smtp.Password(account.address, "wrong"))


@icloud
@pytest.mark.skipif(not CUSTOM_ADDRESS, reason="set ICLOUD_CUSTOM_ADDRESS")
def test_icloud_keeps_a_custom_domain_from_address():
    result = send(ICLOUD, CUSTOM_ADDRESS)

    assert parseaddr(received(ICLOUD, result.message_id)["From"])[1] == CUSTOM_ADDRESS


@icloud
def test_icloud_refuses_a_from_address_the_account_does_not_own():
    with pytest.raises(SenderRefusedError):
        send(ICLOUD, "nobody@example.com")


@gmail
def test_gmail_rewrites_a_from_address_the_account_does_not_own():
    result = send(GMAIL, "nobody@example.com")

    assert parseaddr(received(GMAIL, result.message_id)["From"])[1] == GMAIL.address


@gmail
@pytest.mark.skipif(
    not AUTHORIZED_USER.is_file(), reason="set GMAIL_AUTHORIZED_USER to a saved consent"
)
def test_gmail_keeps_the_message_id_over_oauth():
    credential = smtp.OAuth(
        username=GMAIL.address, credential=AuthorizedUser(path=AUTHORIZED_USER)
    )

    result = send(GMAIL, GMAIL.address, credential)

    assert received(GMAIL, result.message_id)["Message-ID"] == result.message_id


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

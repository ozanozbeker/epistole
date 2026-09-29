"""Send real mail through the Gmail API, skipping every test when `.env` names no Gmail account.

Run them with `uv run --env-file .env pytest tests/test_live_gmail.py --tb=short`. The saved consent must grant `https://mail.google.com/` as well as `gmail.send`, because each test reads its message back through the Gmail API.
"""

import json
import os
import time
import uuid
from email.utils import parseaddr
from pathlib import Path

import httpx2
import pytest

from epistole import GmailBackend, Message, SendResult, gmail

ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
AUTHORIZED_USER = Path(os.environ.get("GMAIL_AUTHORIZED_USER", "")).expanduser()
ARRIVAL_SECONDS = 120

pytestmark = pytest.mark.skipif(
    not (ADDRESS and AUTHORIZED_USER.is_file()),
    reason="set GMAIL_ADDRESS, and GMAIL_AUTHORIZED_USER to a saved consent",
)


def subject() -> str:
    """Return a subject no other message in the mailbox has."""
    return f"epistole live test {uuid.uuid4().hex}"


def send(from_address: str, subject: str) -> SendResult:
    """Send one message from `from_address` to the Gmail account's own inbox."""
    backend = GmailBackend(
        from_address=from_address,
        credential=gmail.AuthorizedUser(path=AUTHORIZED_USER),
    )
    return backend.send(
        Message(text="Sent by tests/test_live_gmail.py.").subject(subject).to(ADDRESS)
    )


def token() -> str:
    """Return an access token with every scope the saved consent granted."""
    saved = json.loads(AUTHORIZED_USER.read_text())
    reply = httpx2.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "client_id": saved["client_id"],
            "client_secret": saved["client_secret"],
            "refresh_token": saved["refresh_token"],
        },
    )
    return reply.raise_for_status().json()["access_token"]


def received(subject: str) -> dict[str, str]:
    """Return the headers of the message with `subject`, keyed by lowercase name, once Gmail finds it."""
    with httpx2.Client(
        base_url="https://gmail.googleapis.com/gmail/v1/users/me/",
        headers={"Authorization": f"Bearer {token()}"},
    ) as client:
        deadline = time.monotonic() + ARRIVAL_SECONDS
        while time.monotonic() < deadline:
            found = client.get(
                "messages",
                params={"q": f'subject:"{subject}"', "includeSpamTrash": "true"},
            )
            if messages := found.raise_for_status().json().get("messages"):
                message = client.get(
                    f"messages/{messages[0]['id']}",
                    params={
                        "format": "metadata",
                        "metadataHeaders": ["Message-ID", "From"],
                    },
                )
                headers = message.raise_for_status().json()["payload"]["headers"]
                return {header["name"].lower(): header["value"] for header in headers}
            time.sleep(5)
    pytest.fail(f"{subject!r} did not arrive within {ARRIVAL_SECONDS} seconds")


def test_gmail_replaces_the_message_id():
    sent = subject()

    result = send(ADDRESS, sent)

    replaced = received(sent)["message-id"]
    assert replaced != result.message_id
    assert replaced.endswith("@mail.gmail.com>")


def test_gmail_rewrites_a_from_address_the_account_does_not_own():
    sent = subject()

    send("nobody@example.com", sent)

    assert parseaddr(received(sent)["from"])[1] == ADDRESS

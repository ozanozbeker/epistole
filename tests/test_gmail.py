import base64
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import parse_qs

import httpx2
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth.exceptions import RefreshError

from epistole import GmailBackend, Message, TokenCredential, gmail, smtp
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RejectedError,
    ThrottledError,
    TransportError,
)

TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105
SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SCOPE = "https://www.googleapis.com/auth/gmail.send"

type Reply = httpx2.Response | Exception


class Google:
    """A fake of Google's token endpoint and the Gmail API, which every `httpx2.Client` the backend builds sends to.

    `replies` maps a URL to the replies it serves first, in order. An exception among them is raised rather than returned. After those, the token endpoint issues `token-1`, `token-2`, and so on, and the send endpoint accepts.
    """

    def __init__(self) -> None:
        self.replies: dict[str, list[Reply]] = {}
        self.requests: list[httpx2.Request] = []
        self.clients: list[httpx2.Client] = []
        self._issued = 0

    def sent(self) -> list[httpx2.Request]:
        """Return each request to the send endpoint."""
        return [one for one in self.requests if str(one.url) == SEND]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        url = str(request.url)
        if self.replies.get(url):
            reply = self.replies[url].pop(0)
            if isinstance(reply, Exception):
                raise reply

            return reply

        if url == TOKEN_URI:
            self._issued += 1
            return httpx2.Response(
                200,
                json={"access_token": f"token-{self._issued}", "expires_in": 3600},
            )

        if url == SEND:
            return httpx2.Response(200, json={"id": "1", "labelIds": ["SENT"]})

        return httpx2.Response(404)


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> Google:
    """Send every request of every `httpx2.Client` the backend builds to a fake Google, keeping the options the backend set."""
    fake = Google()
    build = httpx2.Client

    def client(**options: Any) -> httpx2.Client:
        fake.clients.append(build(transport=httpx2.MockTransport(fake), **options))
        return fake.clients[-1]

    monkeypatch.setattr(httpx2, "Client", client)
    return fake


@pytest.fixture(scope="session")
def private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def service_account(tmp_path: Path, private_key: str) -> gmail.ServiceAccount:
    path = tmp_path / "service-account.json"
    key = {
        "type": "service_account",
        "client_email": "epistole@project.iam.gserviceaccount.com",
        "private_key": private_key,
        "token_uri": TOKEN_URI,
    }
    path.write_text(json.dumps(key))
    return gmail.ServiceAccount(path, subject="reports@example.com")


@pytest.fixture
def authorized_user(tmp_path: Path) -> gmail.AuthorizedUser:
    path = tmp_path / "authorized-user.json"
    consent = {
        "type": "authorized_user",
        "client_id": "epistole",
        "client_secret": "hunter2",
        "refresh_token": "refresh",
    }
    path.write_text(json.dumps(consent))
    return gmail.AuthorizedUser(path)


class AccessToken(NamedTuple):
    """The shape `azure.core.credentials.AccessToken` defines."""

    token: str
    expires_on: int


class Credential:
    """A `TokenCredential` that returns `foreign-1`, `foreign-2`, and so on, and records the scopes of each call."""

    def __init__(self) -> None:
        self.scopes: list[tuple[str, ...]] = []

    def get_token(self, *scopes: str) -> AccessToken:
        self.scopes.append(scopes)
        return AccessToken(f"foreign-{len(self.scopes)}", int(time.time()) + 3600)


def backend(
    credential: gmail.ServiceAccount | gmail.AuthorizedUser | TokenCredential,
) -> GmailBackend:
    return GmailBackend(from_address="reports@example.com", credential=credential)


def message(*recipients: str) -> Message:
    """Build a message addressed to `recipients`, or to one default recipient."""
    built = Message(text="Weekly numbers").subject("Weekly numbers")
    return built.to(*recipients) if recipients else built.to("ada@example.com")


def raw(request: httpx2.Request) -> bytes:
    """Return the RFC 5322 bytes a send request carries."""
    return base64.urlsafe_b64decode(json.loads(request.content)["raw"])


def error(
    status: int, reason: str | None = None, *, headers: dict[str, str] | None = None
) -> httpx2.Response:
    """Build a Gmail error reply in Google's envelope, with `reason` as its one `errors[].reason`."""
    errors = [{"domain": "global", "reason": reason}] if reason else []
    body = {"error": {"code": status, "message": "Refused.", "errors": errors}}
    return httpx2.Response(status, json=body, headers=headers)


# --- Sending -----------------------------------------------------------------


def test_a_send_posts_the_message_as_base64url_raw(
    google: Google, service_account: gmail.ServiceAccount
):
    result = backend(service_account).send(message().bcc("cleo@example.com"))

    [request] = google.sent()
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer token-1"
    assert f"Message-ID: {result.message_id}".encode() in raw(request)
    assert b"Bcc: cleo@example.com" in raw(request)
    assert result.refused == {}


# --- Pre-checks --------------------------------------------------------------


def test_more_than_500_recipients_is_rejected_before_writing(
    google: Google, service_account: gmail.ServiceAccount
):
    recipients = [f"r{n}@example.com" for n in range(501)]

    with backend(service_account).connect() as connection:
        with pytest.raises(RejectedError, match="501") as caught:
            connection.send(message(*recipients))

        connection.send(message(*recipients[:500]))

    assert caught.value.__cause__ is None
    assert len(google.sent()) == 1


def test_a_message_over_35_mib_once_encoded_is_rejected_before_writing(
    google: Google, service_account: gmail.ServiceAccount
):
    # 27,000,000 bytes is under 35 MiB, but base64 in 76-character lines makes it 36,947,368.
    attached = message().attach(bytes(27_000_000), filename="large.bin")

    with pytest.raises(RejectedError) as caught:
        backend(service_account).send(attached)

    assert caught.value.__cause__ is None
    assert google.sent() == []


def test_the_size_check_measures_the_bytes_sent_rather_than_estimating(
    google: Google, service_account: gmail.ServiceAccount
):
    # Short ASCII lines go out as 7-bit, so 30 MB of text stays under 35 MiB. A base64 estimate would reject it.
    text = ("x" * 77 + "\n") * 384_615

    backend(service_account).send(Message(text=text).to("ada@example.com"))

    assert len(raw(google.sent()[0])) > len(text)


# --- Credentials -------------------------------------------------------------


def test_a_service_account_requests_gmail_send_as_its_subject(
    google: Google, service_account: gmail.ServiceAccount
):
    backend(service_account).connect()

    [request] = google.requests
    assertion = parse_qs(request.content.decode())["assertion"][0]
    claims = json.loads(base64.urlsafe_b64decode(assertion.split(".")[1] + "=="))
    assert claims["scope"] == SCOPE
    assert claims["sub"] == "reports@example.com"


def test_an_authorized_user_refreshes_for_gmail_send(
    google: Google, authorized_user: gmail.AuthorizedUser
):
    backend(authorized_user).send(message())

    form = parse_qs(google.requests[0].content.decode())
    assert form["grant_type"] == ["refresh_token"]
    assert form["scope"] == [SCOPE]
    assert google.sent()[0].headers["Authorization"] == "Bearer token-1"


def test_get_token_is_called_with_gmail_send_before_each_request(
    google: Google,
):
    credential = Credential()

    with backend(credential).connect() as connection:
        connection.send(message())
        connection.send(message())

    assert credential.scopes == [(SCOPE,)] * 3
    assert [one.headers["Authorization"] for one in google.sent()] == [
        "Bearer foreign-2",
        "Bearer foreign-3",
    ]


def test_connect_reads_the_key_file_and_the_constructor_does_not(
    google: Google, tmp_path: Path
):
    missing = backend(gmail.ServiceAccount(tmp_path / "missing.json", "a@example.com"))

    with pytest.raises(FileNotFoundError):
        missing.connect()

    assert all(one.is_closed for one in google.clients)


@pytest.mark.parametrize(
    "credential",
    ["token", smtp.Password(username="reports", password="hunter2")],  # noqa: S106
)
def test_a_credential_of_another_type_raises(credential: object):
    with pytest.raises(TypeError, match=type(credential).__name__):
        backend(credential)  # pyrefly: ignore


@pytest.mark.parametrize("module", ["httpx2", "google.auth"])
def test_the_constructor_raises_naming_the_extra_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch, module: str
):
    monkeypatch.setitem(sys.modules, module, None)

    with pytest.raises(ImportError, match=r"epistole\[gmail\]"):
        backend(gmail.ServiceAccount(Path("key.json"), subject="reports@example.com"))


# --- Connecting --------------------------------------------------------------


def test_connect_gets_a_token_on_one_client_and_requests_no_mail_endpoint(
    google: Google, service_account: gmail.ServiceAccount
):
    with backend(service_account).connect() as connection:
        assert [str(one.url) for one in google.requests] == [TOKEN_URI]
        connection.send(message())
        connection.send(message())

    assert [str(one.url) for one in google.requests] == [TOKEN_URI, SEND, SEND]
    assert len(google.clients) == 1
    assert google.clients[0].is_closed


def test_every_request_times_out_after_60_seconds(
    google: Google, service_account: gmail.ServiceAccount
):
    backend(service_account).connect()

    assert google.clients[0].timeout == httpx2.Timeout(60)


# --- Refreshing on 401 -------------------------------------------------------


def test_a_401_refreshes_once_and_retries_the_request_once(
    google: Google, service_account: gmail.ServiceAccount
):
    google.replies[SEND] = [httpx2.Response(401)]

    backend(service_account).send(message())

    assert [str(one.url) for one in google.requests] == [
        TOKEN_URI,
        SEND,
        TOKEN_URI,
        SEND,
    ]
    assert google.sent()[1].headers["Authorization"] == "Bearer token-2"


def test_a_401_calls_get_token_again(google: Google):
    google.replies[SEND] = [httpx2.Response(401)]

    backend(Credential()).send(message())

    assert [one.headers["Authorization"] for one in google.sent()] == [
        "Bearer foreign-2",
        "Bearer foreign-3",
    ]


def test_a_second_401_on_the_same_request_is_an_authentication_error(
    google: Google, service_account: gmail.ServiceAccount
):
    google.replies[SEND] = [httpx2.Response(401), httpx2.Response(401)]
    configured = backend(service_account)

    with pytest.raises(AuthenticationError) as caught:
        configured.send(message())

    assert isinstance(caught.value.__cause__, httpx2.HTTPStatusError)
    assert caught.value.backend is configured
    assert len(google.sent()) == 2


def test_each_request_gets_its_own_401_retry(
    google: Google, service_account: gmail.ServiceAccount
):
    google.replies[SEND] = [
        httpx2.Response(401),
        httpx2.Response(200, json={"id": "1"}),
        httpx2.Response(401),
    ]

    with backend(service_account).connect() as connection:
        connection.send(message())
        connection.send(message())

    assert len(google.sent()) == 4


# --- Mapping -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        pytest.param(error(400, "invalidArgument"), RejectedError, id="400"),
        pytest.param(error(404, "notFound"), RejectedError, id="404"),
        pytest.param(error(403, "domainPolicy"), RejectedError, id="403 domainPolicy"),
        pytest.param(error(403, "authError"), AuthenticationError, id="403 authError"),
        pytest.param(
            error(403, "insufficientPermissions"),
            AuthenticationError,
            id="403 insufficientPermissions",
        ),
        pytest.param(error(403, "forbidden"), AuthenticationError, id="any other 403"),
        pytest.param(
            httpx2.Response(403, text="Forbidden"),
            AuthenticationError,
            id="403 outside Google's envelope",
        ),
        pytest.param(
            error(403, "rateLimitExceeded"), ThrottledError, id="403 rateLimitExceeded"
        ),
        pytest.param(
            error(403, "userRateLimitExceeded"),
            ThrottledError,
            id="403 userRateLimitExceeded",
        ),
        pytest.param(
            error(403, "dailyLimitExceeded"),
            ThrottledError,
            id="403 dailyLimitExceeded",
        ),
        pytest.param(error(429), ThrottledError, id="429"),
        pytest.param(
            error(400, "rateLimitExceeded"), RejectedError, id="400 qualified"
        ),
        pytest.param(error(500, "backendError"), ProviderError, id="500"),
        pytest.param(error(503), ProviderError, id="503"),
        pytest.param(error(413), ProviderError, id="a status no row matches"),
    ],
)
def test_a_reply_maps_to_its_row(
    google: Google,
    service_account: gmail.ServiceAccount,
    reply: httpx2.Response,
    expected: type[EpistoleError],
):
    google.replies[SEND] = [reply]
    configured = backend(service_account)

    with pytest.raises(EpistoleError) as caught:
        configured.send(message())

    assert type(caught.value) is expected
    assert isinstance(caught.value.__cause__, httpx2.HTTPStatusError)
    assert caught.value.backend is configured


@pytest.mark.parametrize(
    "failure", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("timed out")]
)
def test_a_network_failure_on_a_send_is_a_transport_error_that_closes_the_client(
    google: Google, service_account: gmail.ServiceAccount, failure: Exception
):
    google.replies[SEND] = [failure]
    configured = backend(service_account)

    with pytest.raises(TransportError) as caught:
        configured.send(message())

    assert caught.value.__cause__ is failure
    assert caught.value.backend is configured
    assert google.clients[0].is_closed


def test_a_refused_refresh_is_an_authentication_error_on_the_connect_line(
    google: Google, service_account: gmail.ServiceAccount
):
    google.replies[TOKEN_URI] = [
        httpx2.Response(400, json={"error": "invalid_grant", "error_description": "no"})
    ]
    configured = backend(service_account)

    with pytest.raises(AuthenticationError) as caught:
        configured.connect()

    assert isinstance(caught.value.__cause__, RefreshError)
    assert caught.value.backend is configured
    assert google.clients[0].is_closed


def test_a_network_failure_on_a_refresh_is_a_transport_error(
    google: Google, authorized_user: gmail.AuthorizedUser
):
    failure = httpx2.ConnectError("refused")
    google.replies[TOKEN_URI] = [failure]

    with pytest.raises(TransportError) as caught:
        backend(authorized_user).connect()

    assert caught.value.__cause__ is failure


@pytest.mark.parametrize(
    ("failure", "expected", "cause"),
    [
        pytest.param(
            httpx2.Response(400, json={"error": "invalid_grant"}),
            AuthenticationError,
            RefreshError,
            id="refused",
        ),
        pytest.param(
            httpx2.ConnectError("refused"),
            TransportError,
            httpx2.ConnectError,
            id="network failure",
        ),
    ],
)
def test_a_failed_refresh_after_a_401_maps_as_it_does_on_connect(
    google: Google,
    service_account: gmail.ServiceAccount,
    failure: Reply,
    expected: type[EpistoleError],
    cause: type[Exception],
):
    google.replies[SEND] = [httpx2.Response(401)]
    google.replies[TOKEN_URI] = [
        httpx2.Response(200, json={"access_token": "token-1", "expires_in": 3600}),
        failure,
    ]

    with backend(service_account).connect() as connection:
        with pytest.raises(expected) as caught:
            connection.send(message())

        assert type(caught.value.__cause__) is cause
        # Only a TransportError closes the connection (ADR-0005).
        assert google.clients[0].is_closed is (expected is TransportError)


def test_a_reply_that_does_not_decode_is_a_provider_error(
    google: Google, service_account: gmail.ServiceAccount
):
    google.replies[SEND] = [
        httpx2.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=httpx2.ByteStream(b"not gzip"),
        )
    ]

    with pytest.raises(ProviderError) as caught:
        backend(service_account).send(message())

    assert isinstance(caught.value.__cause__, httpx2.DecodingError)


# --- Retry-After -------------------------------------------------------------

IN_90_SECONDS = datetime.now(UTC) + timedelta(seconds=90)


@pytest.mark.parametrize(
    ("header", "low", "high"),
    [
        pytest.param("120", 120, 120, id="delay-seconds"),
        pytest.param(
            format_datetime(IN_90_SECONDS, usegmt=True), 0, 90, id="IMF-fixdate"
        ),
        pytest.param(
            IN_90_SECONDS.strftime("%A, %d-%b-%y %H:%M:%S GMT"), 0, 90, id="rfc850-date"
        ),
        pytest.param(
            IN_90_SECONDS.strftime("%a %b %d %H:%M:%S %Y"), 0, 90, id="asctime-date"
        ),
        pytest.param("Sun, 06 Nov 1994 08:49:37 GMT", 0, 0, id="a date in the past"),
    ],
)
def test_retry_after_is_seconds_in_either_rfc_9110_form(
    google: Google,
    service_account: gmail.ServiceAccount,
    header: str,
    low: float,
    high: float,
):
    google.replies[SEND] = [error(429, headers={"Retry-After": header})]

    with pytest.raises(ThrottledError) as caught:
        backend(service_account).send(message())

    assert caught.value.retry_after is not None
    assert low <= caught.value.retry_after <= high


@pytest.mark.parametrize("headers", [{}, {"Retry-After": "soon"}])
def test_retry_after_is_none_without_a_readable_header(
    google: Google, service_account: gmail.ServiceAccount, headers: dict[str, str]
):
    google.replies[SEND] = [error(403, "rateLimitExceeded", headers=headers)]

    with pytest.raises(ThrottledError) as caught:
        backend(service_account).send(message())

    assert caught.value.retry_after is None

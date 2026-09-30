import base64
import contextlib
import hmac
import json
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from email import message_from_bytes
from email.policy import default
from pathlib import Path
from smtplib import (
    SMTP,
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPDataError,
    SMTPException,
    SMTPHeloError,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPSenderRefused,
    SMTPServerDisconnected,
)
from typing import Any, NamedTuple
from urllib.parse import parse_qs

import httpx2
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from epistole import Message, Refusal, SMTPBackend, Submission, gmail, graph, smtp
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RecipientsRefusedError,
    RejectedError,
    SenderRefusedError,
    TransportError,
)


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


EXTENSIONS = ("SIZE 10485760", "8BITMIME", "SMTPUTF8", "AUTH PLAIN XOAUTH2")
STARTTLS = (*EXTENSIONS, "STARTTLS")
PASSWORD = smtp.Password(username="reports", password="hunter2")  # noqa: S106
WRONG = smtp.Password(username="reports", password="x")  # noqa: S106
AUTH = f"AUTH PLAIN {b64('\0reports\0hunter2')}"
XOAUTH2 = f"AUTH XOAUTH2 {b64('user=reports@example.com\1auth=Bearer token-1\1\1')}"
OUTLOOK = "https://outlook.office365.com/.default"
GMAIL = "https://mail.google.com/"
ACCEPTED = "235 2.7.0 accepted"
CHALLENGE = "<1896.697170952@postoffice.example.net>"
TENANT = "contoso.onmicrosoft.com"
MICROSOFT = f"https://login.microsoftonline.com/{TENANT}"

type Reply = str | bytes | None


class Server:
    """A scripted SMTP server on 127.0.0.1 that records each command and message it receives.

    `replies` maps a verb, `RCPT` plus an addr-spec, `greeting`, `response` for the line after a `334`, or `.` for the end of the data, to a reply that replaces the default. A `None` reply closes the socket unanswered, and a `421` reply closes it after replying. The server also closes it after replying to the verb `closes_after`. `tls` answers `STARTTLS`, or with `implicit` starts TLS on connect. `upgraded` replaces the extensions offered once `STARTTLS` has started TLS.
    """

    def __init__(
        self,
        replies: dict[str, Reply] | None = None,
        *,
        extensions: tuple[str, ...] = EXTENSIONS,
        upgraded: tuple[str, ...] | None = None,
        tls: ssl.SSLContext | None = None,
        implicit: bool = False,
        closes_after: str | None = None,
    ) -> None:
        self.replies = replies or {}
        self.extensions = extensions
        self.upgraded = upgraded
        self.tls = tls
        self.implicit = implicit
        self.closes_after = closes_after
        self.commands: list[str] = []
        self.messages: list[bytes] = []
        self.hung_up = threading.Event()
        """Set when the client closes its socket, so a test can wait for it."""
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port: int = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def verbs(self) -> list[str]:
        """Return the verb of each command received, uppercased, because `smtplib` writes most in lowercase."""
        return [command.partition(" ")[0].upper() for command in self.commands]

    def close(self) -> None:
        # Linux keeps a socket listening while a thread blocks in accept() on it, until shutdown() wakes that thread.
        with contextlib.suppress(OSError):
            self._listener.shutdown(socket.SHUT_RDWR)
        self._listener.close()

    def _accept(self) -> None:
        with contextlib.suppress(OSError):
            while True:
                sock, _ = self._listener.accept()
                threading.Thread(
                    target=self._session, args=(sock,), daemon=True
                ).start()

    def _session(self, sock: socket.socket) -> None:
        with contextlib.suppress(OSError):
            try:
                if self.implicit and self.tls is not None:
                    sock = self.tls.wrap_socket(sock, server_side=True)

                reader = sock.makefile("rb")
                extensions = self.extensions
                reply = self._reply(sock, "greeting", "220 fake ESMTP")
                while reply and not reply.startswith(b"421"):
                    line = reader.readline()
                    if not line:
                        self.hung_up.set()
                        return

                    command = line.decode().rstrip("\r\n")
                    self.commands.append(command)
                    # RFC 4954: the client sends a response after a 334, and a response has no verb.
                    verb = (
                        "response"
                        if reply.startswith(b"334")
                        else command.partition(" ")[0].upper()
                    )
                    reply = self._reply(sock, *self._answer(command, verb, extensions))
                    if verb == self.closes_after:
                        return

                    if verb == "STARTTLS" and reply.startswith(b"220") and self.tls:
                        sock = self.tls.wrap_socket(sock, server_side=True)
                        reader = sock.makefile("rb")
                        # RFC 3207: a server offers no STARTTLS once TLS is up.
                        extensions = (
                            tuple(one for one in extensions if one != "STARTTLS")
                            if self.upgraded is None
                            else self.upgraded
                        )
                    elif verb == "DATA" and reply.startswith(b"354"):
                        data = b""
                        while (line := reader.readline()) not in {b".\r\n", b""}:
                            data += line

                        self.messages.append(data)
                        reply = self._reply(sock, ".", "250 2.0.0 queued")
            finally:
                sock.close()

    def _answer(
        self, command: str, verb: str, extensions: tuple[str, ...]
    ) -> tuple[str, Reply]:
        """Return the key that picks the reply to `command`, and the reply to send when `replies` has none."""
        if verb == "EHLO":
            lines = ["fake", *extensions]
            return verb, "\r\n".join(
                f"250-{one}" for one in lines[:-1]
            ) + f"\r\n250 {lines[-1]}"

        if verb == "RCPT":
            address = command.partition("<")[2].partition(">")[0]
            return f"RCPT {address}", self.replies.get("RCPT", "250 2.1.5 ok")

        if verb == "AUTH":
            return (
                verb,
                ACCEPTED if command in {AUTH, XOAUTH2} else "535 5.7.8 rejected",
            )

        defaults = {
            "HELO": "250 fake",
            "STARTTLS": "220 2.0.0 ready" if self.tls else "502 5.5.1 unknown",
            "MAIL": "250 2.1.0 ok",
            "DATA": "354 go ahead",
            "RSET": "250 2.0.0 ok",
            "QUIT": "221 2.0.0 bye",
        }
        return verb, defaults.get(verb, "500 5.5.2 unknown")

    def _reply(self, sock: socket.socket, key: str, default: Reply) -> bytes:
        """Send the reply for `key` and return it, or return `b""` for a reply that closes the socket unanswered."""
        reply = self.replies.get(key, default)
        if reply is None:
            return b""

        encoded = reply if isinstance(reply, bytes) else reply.encode()
        sock.sendall(encoded + b"\r\n")
        return encoded


@pytest.fixture(scope="session")
def certificate(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    """Make a self-signed certificate for 127.0.0.1, and return the paths of it and its key."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("making a test certificate needs the openssl command")

    directory = tmp_path_factory.mktemp("tls")
    cert, key = str(directory / "cert.pem"), str(directory / "key.pem")
    options = "req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1"
    subprocess.run(  # noqa: S603
        [openssl, *options.split(), "-keyout", key, "-out", cert],
        check=True,
        capture_output=True,
    )
    return cert, key


@pytest.fixture
def tls(certificate: tuple[str, str]) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(*certificate)
    return context


@pytest.fixture
def trusted(certificate: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the client trust the test certificate, through the variable OpenSSL reads for its trust store."""
    monkeypatch.setenv("SSL_CERT_FILE", certificate[0])


@pytest.fixture
def serve() -> Iterator[Callable[..., Server]]:
    servers: list[Server] = []

    def start(replies: dict[str, Reply] | None = None, **options: Any) -> Server:
        servers.append(Server(replies, **options))
        return servers[-1]

    yield start
    for one in servers:
        one.close()


def backend(server: Server, **options: Any) -> SMTPBackend:
    """Build a plaintext backend that sends to `server`, unless `options` say otherwise."""
    defaults: dict[str, Any] = {
        "security": "none",
        "from_address": "reports@example.com",
    }
    return SMTPBackend("127.0.0.1", port=server.port, **defaults | options)


def message(*recipients: str) -> Message:
    """Build a message addressed to `recipients`, or to one default recipient."""
    built = Message(text="Weekly numbers").subject("Weekly numbers")
    return built.to(*recipients) if recipients else built.to("ada@example.com")


def submission(message: Message) -> Submission:
    """Wrap `message` as `Connection.send` would, with a fixed id and date."""
    return Submission(
        message=message,
        from_address="reports@example.com",
        message_id="<179021486392.66219.11904006491029159968@example.com>",
        date=datetime(2026, 9, 23, 21, 54, 23, tzinfo=UTC),
    )


class AccessToken(NamedTuple):
    """The shape `azure.core.credentials.AccessToken` defines."""

    token: str
    expires_on: int


class Credential:
    """A `TokenCredential` that returns `token-1` and records the scopes of each call."""

    def __init__(self) -> None:
        self.scopes: list[tuple[str, ...]] = []

    def get_token(self, *scopes: str) -> AccessToken:
        self.scopes.append(scopes)
        return AccessToken("token-1", int(time.time()) + 3600)


class Broken:
    """A `TokenCredential` whose `get_token` raises `error`."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_token(self, *_: str) -> AccessToken:
        raise self.error


class Issuer:
    """A fake of the token endpoints of Microsoft and Google, which issues `token-1` and records each request.

    Once `failure` is set, the issuer returns it for every token request, or raises it when it is an exception.
    """

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.clients: list[httpx2.Client] = []
        self.options: list[dict[str, Any]] = []
        self.failure: httpx2.Response | Exception | None = None

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.url.path.endswith("/openid-configuration"):
            return httpx2.Response(
                200,
                json={
                    "authorization_endpoint": f"{MICROSOFT}/oauth2/v2.0/authorize",
                    "token_endpoint": f"{MICROSOFT}/oauth2/v2.0/token",
                    "issuer": f"{MICROSOFT}/v2.0",
                },
            )

        if isinstance(self.failure, httpx2.Response):
            return self.failure

        if self.failure is not None:
            raise self.failure

        return httpx2.Response(
            200,
            json={
                "access_token": "token-1",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> Issuer:
    """Send every request of every `httpx2.Client` the backend builds to a fake issuer, keeping the options the backend set."""
    fake = Issuer()
    build = httpx2.Client

    def client(**options: Any) -> httpx2.Client:
        fake.options.append(options)
        fake.clients.append(build(transport=httpx2.MockTransport(fake), **options))
        return fake.clients[-1]

    monkeypatch.setattr(httpx2, "Client", client)
    # msal reads these to pick a managed identity endpoint other than a VM's.
    for name in ("IDENTITY_ENDPOINT", "MSI_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)

    return fake


@pytest.fixture
def secret() -> graph.ClientSecret:
    return graph.ClientSecret(TENANT, "epistole", "hunter2")


@pytest.fixture
def service_account(tmp_path: Path) -> gmail.ServiceAccount:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path = tmp_path / "service-account.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "client_email": "epistole@project.iam.gserviceaccount.com",
                "private_key": pem.decode(),
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
    )
    return gmail.ServiceAccount(path, subject="reports@example.com")


@pytest.fixture
def authorized_user(tmp_path: Path) -> gmail.AuthorizedUser:
    path = tmp_path / "authorized-user.json"
    path.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "epistole",
                "client_secret": "hunter2",
                "refresh_token": "refresh",
            }
        )
    )
    return gmail.AuthorizedUser(path)


@pytest.fixture
def user_with_saved_token(
    authorized_user: gmail.AuthorizedUser,
) -> gmail.AuthorizedUser:
    """Save an unexpired access token in `authorized_user`'s file, as `Credentials.to_json()` writes one."""
    consent = json.loads(authorized_user.path.read_text())
    consent |= {"token": "saved-token", "expiry": "2099-01-01T00:00:00Z"}
    authorized_user.path.write_text(json.dumps(consent))
    return authorized_user


# --- Sending -----------------------------------------------------------------


def test_an_anonymous_send_submits_the_message_and_quits(serve: Callable[..., Server]):
    server = serve()

    result = backend(server).send(message())

    assert result.refused == {}
    assert server.verbs() == ["EHLO", "MAIL", "RCPT", "DATA", "QUIT"]
    assert server.commands[1].startswith("mail from:<reports@example.com>")
    assert server.commands[2] == "rcpt to:<ada@example.com>"
    assert f"Message-ID: {result.message_id}".encode() in server.messages[0]


def test_each_line_break_goes_out_as_crlf_and_each_part_ends_with_one(
    serve: Callable[..., Server],
):
    server = serve()

    backend(server).send(
        Message(html="<p>Weekly</p>", text="Weekly\rnumbers").to("ada@example.com")
    )

    parts = message_from_bytes(server.messages[0], policy=default).iter_parts()
    assert [part.get_payload(decode=True) for part in parts] == [
        b"Weekly\r\nnumbers\r\n",
        b"<p>Weekly</p>\r\n",
    ]


def test_the_envelope_names_to_cc_and_bcc_in_order_and_the_message_hides_bcc(
    serve: Callable[..., Server],
):
    server = serve()

    backend(server).send(
        message("ada@example.com").cc("bob@example.com").bcc("Cleo <cleo@example.com>")
    )

    assert [one for one in server.commands if one.startswith("rcpt")] == [
        "rcpt to:<ada@example.com>",
        "rcpt to:<bob@example.com>",
        "rcpt to:<cleo@example.com>",
    ]
    assert b"cleo@example.com" not in server.messages[0]


def test_a_sender_header_does_not_change_the_envelope(serve: Callable[..., Server]):
    server = serve()

    backend(server).send(message().headers({"Sender": "eve@example.com"}))

    assert server.commands[1].startswith("mail from:<reports@example.com>")


def test_resent_to_and_resent_from_headers_are_written(serve: Callable[..., Server]):
    server = serve()

    backend(server).send(
        message().headers(
            {"Resent-To": "eve@example.com", "Resent-From": "ada@example.com"}
        )
    )

    assert b"Resent-To: eve@example.com" in server.messages[0]
    assert b"Resent-From: ada@example.com" in server.messages[0]


def test_mail_from_carries_the_size_when_the_server_offers_it(
    serve: Callable[..., Server],
):
    server = serve()

    backend(server).send(message())

    assert " size=" in server.commands[server.verbs().index("MAIL")]


@pytest.mark.parametrize("security", ["none", "tls"])
def test_every_socket_operation_times_out_after_60_seconds(
    serve: Callable[..., Server], tls: ssl.SSLContext, trusted: None, security: str
):
    server = serve(tls=tls, implicit=security == "tls")
    transport = backend(server, security=security)._open()
    assert isinstance(transport, smtp._SMTPTransport)

    sock = transport._smtp.sock
    assert sock is not None
    assert sock.gettimeout() == 60
    transport.close()


# --- Credentials -------------------------------------------------------------


def test_a_wrong_password_raises_on_the_connect_line(serve: Callable[..., Server]):
    server = serve()
    wrong = backend(server, credential=WRONG)

    with pytest.raises(AuthenticationError) as caught:
        wrong.connect()

    assert caught.value.backend is wrong
    assert "MAIL" not in server.verbs()
    assert server.hung_up.wait(5)


@pytest.mark.parametrize(
    ("offered", "replies", "commands"),
    [
        pytest.param("AUTH CRAM-MD5 LOGIN PLAIN", {}, [AUTH], id="PLAIN"),
        # Exchange Online offers LOGIN and no PLAIN.
        pytest.param(
            "AUTH CRAM-MD5 LOGIN XOAUTH2",
            {"AUTH": f"334 {b64('Password:')}", "response": ACCEPTED},
            [f"AUTH LOGIN {b64('reports')}", b64("hunter2")],
            id="LOGIN",
        ),
        pytest.param(
            "AUTH CRAM-MD5 NTLM",
            {"AUTH": f"334 {b64(CHALLENGE)}", "response": ACCEPTED},
            [
                "AUTH CRAM-MD5",
                b64(
                    f"reports {hmac.digest(b'hunter2', CHALLENGE.encode(), 'md5').hex()}"
                ),
            ],
            id="CRAM-MD5",
        ),
    ],
)
def test_a_password_authenticates_through_plain_then_login_then_cram_md5(
    serve: Callable[..., Server],
    offered: str,
    replies: dict[str, Reply],
    commands: list[str],
):
    server = serve(replies, extensions=(offered,))

    with backend(server, credential=PASSWORD).connect():
        assert server.commands[1:] == commands


def test_a_wrong_password_raises_authentication_error_when_the_server_then_closes(
    serve: Callable[..., Server],
):
    # Gmail closes its socket after some of its 535 replies.
    server = serve(extensions=("AUTH PLAIN LOGIN",), closes_after="AUTH")
    wrong = backend(server, credential=WRONG)

    with pytest.raises(AuthenticationError, match="535") as caught:
        wrong.connect()

    assert isinstance(caught.value.__cause__, SMTPAuthenticationError)
    assert server.verbs() == ["EHLO", "AUTH"]


@pytest.mark.parametrize(
    "extensions",
    [
        pytest.param(("8BITMIME",), id="no AUTH"),
        pytest.param(("AUTH GSSAPI NTLM",), id="no mechanism of the three"),
    ],
)
def test_a_password_sends_no_auth_to_a_server_that_offers_none_of_its_mechanisms(
    serve: Callable[..., Server], extensions: tuple[str, ...]
):
    server = serve(extensions=extensions)

    with pytest.raises(AuthenticationError, match="CRAM-MD5") as caught:
        backend(server, credential=PASSWORD).connect()

    assert caught.value.__cause__ is None
    assert "AUTH" not in server.verbs()
    assert server.hung_up.wait(5)


def test_a_password_stays_out_of_the_repr():
    assert "hunter2" not in repr(PASSWORD)


def test_oauth_authenticates_through_xoauth2_on_connect(
    serve: Callable[..., Server],
):
    server = serve()
    credential = Credential()
    oauth = smtp.OAuth(
        username="reports@example.com", credential=credential, scope=OUTLOOK
    )

    with backend(server, credential=oauth).connect():
        assert server.commands[-1] == XOAUTH2

    assert credential.scopes == [(OUTLOOK,)]


def test_a_rejected_token_raises_on_the_connect_line(serve: Callable[..., Server]):
    # Gmail sends a 334 challenge that holds its error for a rejected token, then 535 after an empty response.
    error = b64('{"status":"400","schemes":"Bearer"}')
    server = serve({"AUTH": f"334 {error}", "response": "535 5.7.8 not accepted"})
    oauth = smtp.OAuth(
        username="reports@example.com", credential=Credential(), scope=OUTLOOK
    )
    configured = backend(server, credential=oauth)

    with pytest.raises(AuthenticationError, match="535") as caught:
        configured.connect()

    assert isinstance(caught.value.__cause__, SMTPAuthenticationError)
    assert caught.value.backend is configured
    assert server.commands[-1] == ""
    assert server.hung_up.wait(5)


@pytest.mark.parametrize(
    ("extensions", "reply"),
    [
        # Postfix replies 503 when SASL is off, and smtplib's auth returns normally on it.
        pytest.param(("8BITMIME",), "503 5.5.1 not enabled", id="no AUTH"),
        pytest.param(("AUTH PLAIN LOGIN",), "504 5.7.4 unknown", id="no XOAUTH2"),
    ],
)
def test_oauth_sends_no_token_to_a_server_that_does_not_offer_xoauth2(
    serve: Callable[..., Server], extensions: tuple[str, ...], reply: str
):
    server = serve({"AUTH": reply}, extensions=extensions)
    oauth = smtp.OAuth(
        username="reports@example.com", credential=Credential(), scope=OUTLOOK
    )

    with pytest.raises(AuthenticationError, match="XOAUTH2") as caught:
        backend(server, credential=oauth).connect()

    assert caught.value.__cause__ is None
    assert "AUTH" not in server.verbs()
    assert server.hung_up.wait(5)


def test_oauth_over_a_graph_value_requests_the_exchange_online_scope(
    serve: Callable[..., Server], issuer: Issuer, secret: graph.ClientSecret
):
    server = serve()
    oauth = smtp.OAuth(username="reports@example.com", credential=secret)

    with backend(server, credential=oauth).connect():
        assert server.commands[-1] == XOAUTH2

    [token] = [one for one in issuer.requests if one.method == "POST"]
    assert parse_qs(token.content.decode())["scope"] == [OUTLOOK]
    assert all(one.is_closed for one in issuer.clients)


def test_oauth_over_a_managed_identity_requests_the_exchange_online_resource(
    serve: Callable[..., Server], issuer: Issuer
):
    server = serve()
    identity = graph.ManagedIdentity()
    oauth = smtp.OAuth(username="reports@example.com", credential=identity)

    with backend(server, credential=oauth).connect():
        assert server.commands[-1] == XOAUTH2

    [token] = issuer.requests
    query = parse_qs(token.url.query.decode())
    assert query["resource"] == ["https://outlook.office365.com"]
    assert "scope" not in query


def test_oauth_over_a_service_account_requests_the_gmail_smtp_scope(
    serve: Callable[..., Server],
    issuer: Issuer,
    service_account: gmail.ServiceAccount,
):
    server = serve()
    oauth = smtp.OAuth(username="reports@example.com", credential=service_account)

    with backend(server, credential=oauth).connect():
        assert server.commands[-1] == XOAUTH2

    [token] = issuer.requests
    assertion = parse_qs(token.content.decode())["assertion"][0]
    claims = json.loads(base64.urlsafe_b64decode(assertion.split(".")[1] + "=="))
    assert claims["scope"] == GMAIL
    assert all(one.is_closed for one in issuer.clients)


@pytest.mark.parametrize("fixture", ["authorized_user", "user_with_saved_token"])
def test_oauth_over_an_authorized_user_requests_the_gmail_smtp_scope(
    serve: Callable[..., Server],
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
):
    server = serve()
    oauth = smtp.OAuth(
        username="reports@example.com", credential=request.getfixturevalue(fixture)
    )

    with backend(server, credential=oauth).connect():
        assert server.commands[-1] == XOAUTH2

    [token] = issuer.requests
    assert parse_qs(token.content.decode())["scope"] == [GMAIL]


@pytest.mark.parametrize("fixture", ["secret", "service_account"])
def test_the_token_request_times_out_after_60_seconds(
    serve: Callable[..., Server],
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
):
    oauth = smtp.OAuth(
        username="reports@example.com", credential=request.getfixturevalue(fixture)
    )

    backend(serve(), credential=oauth).connect().close()

    assert [one.timeout for one in issuer.clients] == [httpx2.Timeout(60)]


@pytest.mark.parametrize("fixture", ["secret", "service_account"])
def test_the_token_client_takes_proxy_and_ca_settings_from_the_environment(
    serve: Callable[..., Server],
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
):
    # httpx2 reads both by default. MockTransport ignores verify=, so this checks that the client takes no other argument.
    oauth = smtp.OAuth(
        username="reports@example.com", credential=request.getfixturevalue(fixture)
    )

    backend(serve(), credential=oauth).connect().close()

    assert issuer.options == [{"timeout": 60}]


@pytest.mark.parametrize(
    ("credential", "module", "extra"),
    [
        pytest.param(
            graph.ClientSecret(TENANT, "epistole", "hunter2"),
            "msal",
            "graph",
            id="graph value without msal",
        ),
        pytest.param(
            graph.ManagedIdentity(), "httpx2", "graph", id="graph value without httpx2"
        ),
        pytest.param(
            gmail.AuthorizedUser(Path("authorized-user.json")),
            "google.auth",
            "gmail",
            id="gmail value without google-auth",
        ),
    ],
)
def test_the_constructor_raises_naming_the_extra_the_wrapped_credential_needs(
    monkeypatch: pytest.MonkeyPatch,
    credential: graph.ClientSecret | graph.ManagedIdentity | gmail.AuthorizedUser,
    module: str,
    extra: str,
):
    monkeypatch.setitem(sys.modules, module, None)
    oauth = smtp.OAuth(username="reports@example.com", credential=credential)

    with pytest.raises(ImportError, match=rf"epistole\[{extra}\]"):
        SMTPBackend("127.0.0.1", from_address="reports@example.com", credential=oauth)


def test_oauth_over_get_token_needs_no_extra(
    monkeypatch: pytest.MonkeyPatch, serve: Callable[..., Server]
):
    for module in ("httpx2", "msal", "google.auth"):
        monkeypatch.setitem(sys.modules, module, None)

    server = serve()
    oauth = smtp.OAuth(
        username="reports@example.com", credential=Credential(), scope=OUTLOOK
    )

    backend(server, credential=oauth).send(message())

    assert len(server.messages) == 1


def test_a_missing_key_file_stays_a_file_not_found_error(
    serve: Callable[..., Server], issuer: Issuer, tmp_path: Path
):
    missing = gmail.AuthorizedUser(tmp_path / "missing.json")
    oauth = smtp.OAuth(username="reports@example.com", credential=missing)

    with pytest.raises(FileNotFoundError):
        backend(serve(), credential=oauth).connect()

    assert all(one.is_closed for one in issuer.clients)


def test_an_error_from_get_token_stays_unmapped(serve: Callable[..., Server]):
    error = TypeError("get_token failed")
    oauth = smtp.OAuth(
        username="reports@example.com", credential=Broken(error), scope=OUTLOOK
    )

    with pytest.raises(TypeError) as caught:
        backend(serve(), credential=oauth).connect()

    assert caught.value is error


@pytest.mark.parametrize("fixture", ["secret", "authorized_user"])
def test_a_network_failure_getting_the_token_is_a_transport_error(
    serve: Callable[..., Server],
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
):
    issuer.failure = failure = httpx2.ConnectError("refused")
    oauth = smtp.OAuth(
        username="reports@example.com", credential=request.getfixturevalue(fixture)
    )
    configured = backend(serve(), credential=oauth)

    with pytest.raises(TransportError) as caught:
        configured.connect()

    assert caught.value.__cause__ is failure
    assert caught.value.backend is configured


@pytest.mark.parametrize(
    ("fixture", "status"), [("service_account", 503), ("secret", 429)]
)
def test_a_429_or_5xx_from_the_token_endpoint_is_one_request_and_a_provider_error(
    serve: Callable[..., Server],
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    status: int,
):
    issuer.failure = httpx2.Response(status)
    oauth = smtp.OAuth(
        username="reports@example.com", credential=request.getfixturevalue(fixture)
    )
    configured = backend(serve(), credential=oauth)

    with pytest.raises(ProviderError) as caught:
        configured.connect()

    assert len([one for one in issuer.requests if one.url.path.endswith("/token")]) == 1
    assert isinstance(caught.value.__cause__, httpx2.HTTPStatusError)
    assert caught.value.backend is configured


@pytest.mark.parametrize("fixture", ["service_account", "secret"])
def test_a_token_reply_the_library_cannot_read_is_a_provider_error(
    serve: Callable[..., Server],
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
):
    issuer.failure = httpx2.Response(200, content=b"[]")
    oauth = smtp.OAuth(
        username="reports@example.com", credential=request.getfixturevalue(fixture)
    )
    configured = backend(serve(), credential=oauth)

    with pytest.raises(ProviderError) as caught:
        configured.connect()

    assert isinstance(caught.value.__cause__, (AttributeError, TypeError))
    assert caught.value.backend is configured


@pytest.mark.parametrize(
    "credential",
    [
        graph.ClientSecret(TENANT, "epistole", "hunter2"),
        graph.Certificate(TENANT, "epistole", pfx=Path("app.pfx")),
        graph.ManagedIdentity(),
        gmail.ServiceAccount(Path("key.json"), subject="reports@example.com"),
        gmail.AuthorizedUser(Path("authorized-user.json")),
    ],
    ids=lambda credential: type(credential).__name__,
)
def test_oauth_takes_every_graph_and_gmail_value(
    credential: graph.ClientSecret
    | graph.Certificate
    | graph.ManagedIdentity
    | gmail.ServiceAccount
    | gmail.AuthorizedUser,
):
    oauth = smtp.OAuth(username="reports@example.com", credential=credential)

    SMTPBackend("127.0.0.1", from_address="reports@example.com", credential=oauth)


@pytest.mark.parametrize(
    ("credential", "scope"),
    [
        pytest.param(Credential(), None, id="get_token without scope"),
        pytest.param(
            graph.ClientSecret(TENANT, "epistole", "hunter2"),
            OUTLOOK,
            id="graph value with scope",
        ),
        pytest.param(
            gmail.AuthorizedUser(Path("authorized-user.json")),
            GMAIL,
            id="gmail value with scope",
        ),
    ],
)
def test_oauth_takes_a_scope_with_get_token_and_only_then(
    credential: object, scope: str | None
):
    with pytest.raises(TypeError, match="scope="):
        smtp.OAuth(username="reports@example.com", credential=credential, scope=scope)  # pyrefly: ignore


@pytest.mark.parametrize("credential", ["token", PASSWORD], ids=["str", "Password"])
def test_oauth_over_a_credential_of_another_type_raises(credential: object):
    with pytest.raises(TypeError, match=type(credential).__name__):
        smtp.OAuth(username="reports@example.com", credential=credential, scope=OUTLOOK)  # pyrefly: ignore


# --- Security ----------------------------------------------------------------


def test_starttls_upgrades_before_it_authenticates(
    serve: Callable[..., Server], tls: ssl.SSLContext, trusted: None
):
    server = serve(extensions=STARTTLS, tls=tls)

    backend(server, security="starttls", credential=PASSWORD).send(message())

    assert server.verbs() == [
        "EHLO",
        "STARTTLS",
        "EHLO",
        "AUTH",
        "MAIL",
        "RCPT",
        "DATA",
        "QUIT",
    ]


def test_oauth_reads_the_mechanisms_offered_after_starttls(
    serve: Callable[..., Server], tls: ssl.SSLContext, trusted: None
):
    # Office 365 offers AUTH only once TLS is up.
    server = serve(
        extensions=("8BITMIME", "STARTTLS"),
        upgraded=("8BITMIME", "AUTH XOAUTH2"),
        tls=tls,
    )
    oauth = smtp.OAuth(
        username="reports@example.com", credential=Credential(), scope=OUTLOOK
    )

    with backend(server, security="starttls", credential=oauth).connect():
        assert server.commands[-1] == XOAUTH2


def test_starttls_raises_when_the_server_does_not_offer_it(
    serve: Callable[..., Server],
):
    server = serve()

    with pytest.raises(TransportError, match="STARTTLS") as caught:
        backend(server, security="starttls", credential=PASSWORD).connect()

    assert caught.value.__cause__ is None
    assert server.verbs() == ["EHLO"]
    assert server.hung_up.wait(5)


def test_starttls_checks_the_certificate(
    serve: Callable[..., Server], tls: ssl.SSLContext
):
    server = serve(extensions=STARTTLS, tls=tls)

    with pytest.raises(TransportError) as caught:
        backend(server, security="starttls", credential=PASSWORD).connect()

    assert isinstance(caught.value.__cause__, ssl.SSLCertVerificationError)
    assert "AUTH" not in server.verbs()


def test_security_none_never_upgrades_even_when_offered(
    serve: Callable[..., Server], tls: ssl.SSLContext
):
    server = serve(extensions=STARTTLS, tls=tls)

    backend(server, security="none", credential=PASSWORD).send(message())

    assert "STARTTLS" not in server.verbs()


def test_tls_starts_tls_on_connect(
    serve: Callable[..., Server], tls: ssl.SSLContext, trusted: None
):
    server = serve(tls=tls, implicit=True)

    backend(server, security="tls", credential=PASSWORD).send(message())

    assert server.verbs() == ["EHLO", "AUTH", "MAIL", "RCPT", "DATA", "QUIT"]


def test_tls_checks_the_certificate(serve: Callable[..., Server], tls: ssl.SSLContext):
    server = serve(tls=tls, implicit=True)

    with pytest.raises(TransportError) as caught:
        backend(server, security="tls").connect()

    assert isinstance(caught.value.__cause__, ssl.SSLCertVerificationError)


def test_a_credential_of_another_type_raises():
    with pytest.raises(TypeError, match="str"):
        SMTPBackend(
            "127.0.0.1",
            from_address="reports@example.com",
            credential="hunter2",  # pyrefly: ignore
        )


def test_an_unknown_security_raises():
    with pytest.raises(ValueError, match="'ssl'"):
        SMTPBackend("127.0.0.1", security="ssl", from_address="reports@example.com")  # pyrefly: ignore


def test_a_security_that_is_not_a_str_raises_value_error():
    with pytest.raises(ValueError, match=r"\['tls'\]"):
        SMTPBackend("127.0.0.1", security=["tls"], from_address="reports@example.com")  # pyrefly: ignore


# --- Refusals ----------------------------------------------------------------


def test_a_partial_refusal_is_returned_as_data(serve: Callable[..., Server]):
    server = serve({"RCPT bob@example.com": "550 5.1.1 No such user"})

    result = backend(server).send(message("ada@example.com", "Bob <bob@example.com>"))

    assert result.refused == {
        "Bob <bob@example.com>": Refusal(550, "5.1.1 No such user")
    }
    assert len(server.messages) == 1


def test_a_refusal_reason_decodes_as_utf_8_with_replacement(
    serve: Callable[..., Server],
):
    server = serve({"RCPT bob@example.com": b"550 5.1.1 caf\xe9 inconnu"})

    result = backend(server).send(message("ada@example.com", "bob@example.com"))

    assert result.refused["bob@example.com"].reason == "5.1.1 caf\ufffd inconnu"


def test_every_recipient_refused_raises_and_leaves_the_connection_open(
    serve: Callable[..., Server],
):
    server = serve({"RCPT": "550 5.1.1 No such user"})

    with backend(server).connect() as connection:
        with pytest.raises(RecipientsRefusedError) as caught:
            connection.send(message("ada@example.com", "bob@example.com"))

        server.replies.pop("RCPT")
        connection.send(message())

    assert caught.value.refused == {
        "ada@example.com": Refusal(550, "5.1.1 No such user"),
        "bob@example.com": Refusal(550, "5.1.1 No such user"),
    }
    assert len(server.messages) == 1


def test_every_recipient_refused_raises_when_two_share_an_addr_spec(
    serve: Callable[..., Server],
):
    # Postfix replies 554 to DATA after refusing every RCPT TO.
    server = serve(
        {"RCPT": "550 5.1.1 No such user", "DATA": "554 5.5.1 no recipients"}
    )

    with pytest.raises(RecipientsRefusedError) as caught:
        backend(server).send(
            message("ada@example.com").cc("Ada Lovelace <ada@example.com>")
        )

    assert caught.value.refused == {
        "ada@example.com": Refusal(550, "5.1.1 No such user")
    }
    assert server.verbs().count("RCPT") == 1


# --- Mapping -----------------------------------------------------------------

CLOSING = "421 4.3.2 closing"


@pytest.mark.parametrize(
    ("server_options", "backend_options", "native", "expected"),
    [
        pytest.param(
            {"replies": {"MAIL": CLOSING}},
            {},
            SMTPSenderRefused,
            TransportError,
            id="421 at MAIL FROM",
        ),
        pytest.param(
            {"replies": {"RCPT": CLOSING}},
            {},
            SMTPRecipientsRefused,
            TransportError,
            id="421 at RCPT TO",
        ),
        pytest.param(
            {"replies": {".": CLOSING}},
            {},
            SMTPDataError,
            TransportError,
            id="421 after DATA",
        ),
        pytest.param(
            {"replies": {"AUTH": CLOSING}},
            {"credential": PASSWORD},
            SMTPAuthenticationError,
            TransportError,
            id="421 at AUTH",
        ),
        pytest.param(
            {"replies": {"MAIL": "552 5.3.4 message too big"}},
            {},
            SMTPSenderRefused,
            RejectedError,
            id="552 at MAIL FROM",
        ),
        pytest.param(
            {"replies": {"MAIL": "553 5.7.1 not yours"}},
            {},
            SMTPSenderRefused,
            SenderRefusedError,
            id="another code at MAIL FROM",
        ),
        pytest.param(
            {"replies": {"MAIL": "451 4.7.1 try again later"}},
            {},
            SMTPSenderRefused,
            SenderRefusedError,
            id="4yz at MAIL FROM",
        ),
        pytest.param(
            {"replies": {"AUTH": "535 5.7.8 rejected"}},
            {"credential": PASSWORD},
            SMTPAuthenticationError,
            AuthenticationError,
            id="SMTPAuthenticationError",
        ),
        pytest.param(
            {"replies": {"greeting": "554 5.7.1 go away"}},
            {},
            SMTPConnectError,
            TransportError,
            id="SMTPConnectError",
        ),
        pytest.param(
            {"replies": {"EHLO": "500 5.5.1 no", "HELO": "500 5.5.1 no"}},
            {},
            SMTPHeloError,
            TransportError,
            id="SMTPHeloError",
        ),
        pytest.param(
            {"replies": {"MAIL": None}},
            {},
            SMTPServerDisconnected,
            TransportError,
            id="SMTPServerDisconnected",
        ),
        pytest.param(
            {"replies": {".": "554 5.7.1 looks like spam"}},
            {},
            SMTPDataError,
            RejectedError,
            id="5yz after DATA",
        ),
        pytest.param(
            {"replies": {".": "451 4.3.0 try later"}},
            {},
            SMTPDataError,
            ProviderError,
            id="4yz after DATA",
        ),
        pytest.param(
            {"replies": {"STARTTLS": "501 5.5.4 syntax"}, "extensions": STARTTLS},
            {"security": "starttls"},
            SMTPResponseException,
            RejectedError,
            id="another 5yz reply",
        ),
        pytest.param(
            {"replies": {"STARTTLS": "454 4.7.0 not now"}, "extensions": STARTTLS},
            {"security": "starttls"},
            SMTPResponseException,
            ProviderError,
            id="another 4yz reply",
        ),
        pytest.param(
            # smtplib's auth raises one for a server that keeps sending challenges.
            {"replies": {"AUTH": "334 ", "response": "334 "}},
            {"credential": PASSWORD},
            SMTPException,
            AuthenticationError,
            id="a bare SMTPException from auth",
        ),
        pytest.param(
            {"replies": {"DATA": "250 2.0.0 ok"}},
            {},
            SMTPDataError,
            ProviderError,
            id="a reply no row matches",
        ),
    ],
)
def test_a_native_failure_maps_to_its_row(
    serve: Callable[..., Server],
    server_options: dict[str, object],
    backend_options: dict[str, object],
    native: type[Exception],
    expected: type[EpistoleError],
):
    server = serve(**server_options)
    configured = backend(server, **backend_options)

    with pytest.raises(EpistoleError) as caught:
        configured.send(message())

    assert type(caught.value) is expected
    assert type(caught.value.__cause__) is native
    assert caught.value.backend is configured


def test_a_421_at_rcpt_after_an_earlier_refusal_is_a_transport_error(
    serve: Callable[..., Server],
):
    server = serve(
        {
            "RCPT ada@example.com": "550 5.1.1 No such user",
            "RCPT bob@example.com": CLOSING,
        }
    )

    with pytest.raises(TransportError, match="421") as caught:
        backend(server).send(message("ada@example.com", "bob@example.com"))

    assert type(caught.value.__cause__) is SMTPRecipientsRefused


def test_a_bare_smtp_exception_from_send_message_is_a_provider_error(
    serve: Callable[..., Server], monkeypatch: pytest.MonkeyPatch
):
    # smtplib raises a bare SMTPException only from login and auth, so this injects one.
    def fail(*_: object, **__: object) -> None:
        raise SMTPException

    monkeypatch.setattr(SMTP, "send_message", fail)

    with pytest.raises(ProviderError) as caught:
        backend(serve()).send(message())

    assert type(caught.value.__cause__) is SMTPException


def test_the_transport_raises_its_error_with_backend_unset(
    serve: Callable[..., Server],
):
    transport = backend(serve({".": "554 5.7.1 looks like spam"}))._open()

    with pytest.raises(RejectedError) as caught:
        transport.submit(submission(message()))

    assert caught.value.backend is None
    transport.close()


def test_a_server_that_is_not_listening_is_a_transport_error(
    serve: Callable[..., Server],
):
    server = serve()
    server.close()

    with pytest.raises(TransportError) as caught:
        backend(server).connect()

    assert isinstance(caught.value.__cause__, ConnectionRefusedError)


# --- Non-ASCII ---------------------------------------------------------------

NON_ASCII = "用户@例子.广告"


@pytest.mark.parametrize(
    "sent",
    [
        pytest.param(message(NON_ASCII), id="to"),
        pytest.param(message().reply_to(NON_ASCII), id="reply_to"),
        pytest.param(message().headers({"Sender": NON_ASCII}), id="custom header"),
    ],
)
def test_a_non_ascii_address_puts_smtputf8_in_mail_from_once(
    serve: Callable[..., Server], sent: Message
):
    server = serve()

    backend(server).send(sent)

    mail = server.commands[server.verbs().index("MAIL")]
    assert mail.count("SMTPUTF8") == 1
    assert mail.count("BODY=8BITMIME") == 1
    assert NON_ASCII.encode() in server.messages[0]


def test_a_non_ascii_body_under_ascii_headers_goes_out_in_7_bits(
    serve: Callable[..., Server],
):
    server = serve()

    backend(server).send(Message(text="Café au lait").to("ada@example.com"))

    mail = server.commands[server.verbs().index("MAIL")]
    assert "BODY=8BITMIME" not in mail
    assert "SMTPUTF8" not in mail
    assert server.messages[0].isascii()


@pytest.mark.parametrize(
    "sent",
    [
        pytest.param(message(NON_ASCII), id="to"),
        pytest.param(message().reply_to(NON_ASCII), id="reply_to"),
        pytest.param(message().headers({"Sender": NON_ASCII}), id="custom header"),
    ],
)
@pytest.mark.parametrize(
    "replies", [{}, {"EHLO": "502 5.5.1 no"}], ids=["EHLO", "HELO"]
)
def test_a_non_ascii_address_without_smtputf8_is_rejected_before_mail_from(
    serve: Callable[..., Server], sent: Message, replies: dict[str, Reply]
):
    server = serve(replies, extensions=("8BITMIME",))

    with pytest.raises(RejectedError, match="SMTPUTF8") as caught:
        backend(server).send(sent)

    assert caught.value.__cause__ is None
    assert "MAIL" not in server.verbs()

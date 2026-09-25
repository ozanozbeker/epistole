import base64
import contextlib
import json
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from smtplib import (
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPDataError,
    SMTPException,
    SMTPHeloError,
    SMTPNotSupportedError,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPSenderRefused,
    SMTPServerDisconnected,
)
from types import NoneType
from typing import Any, NamedTuple
from urllib.parse import parse_qs

import httpx2
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from epistole import Message, Refusal, SMTPBackend, gmail, graph, smtp
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RecipientsRefusedError,
    RejectedError,
    SenderRefusedError,
    TransportError,
)

EXTENSIONS = ("SIZE 10485760", "8BITMIME", "SMTPUTF8", "AUTH PLAIN XOAUTH2")
STARTTLS = (*EXTENSIONS, "STARTTLS")
PASSWORD = smtp.Password(username="reports", password="hunter2")  # noqa: S106
AUTH = f"AUTH PLAIN {base64.b64encode(b'\0reports\0hunter2').decode()}"
XOAUTH2 = f"AUTH XOAUTH2 {base64.b64encode(b'user=reports@example.com\1auth=Bearer token-1\1\1').decode()}"
OUTLOOK = "https://outlook.office365.com/.default"
GMAIL = "https://mail.google.com/"
TENANT = "contoso.onmicrosoft.com"
MICROSOFT = f"https://login.microsoftonline.com/{TENANT}"

type Reply = str | bytes | None


class Server:
    """A scripted SMTP server on 127.0.0.1 that records each command and message it receives.

    `replies` maps a verb, `RCPT` plus an addr-spec, `greeting`, or `.` for the end of the data, to a reply that replaces the default. A `None` reply closes the socket unanswered, and a `421` reply closes it after replying. `tls` answers `STARTTLS`, or with `implicit` starts TLS on connect.
    """

    def __init__(
        self,
        replies: dict[str, Reply] | None = None,
        *,
        extensions: tuple[str, ...] = EXTENSIONS,
        tls: ssl.SSLContext | None = None,
        implicit: bool = False,
    ) -> None:
        self.replies = replies or {}
        self.extensions = extensions
        self.tls = tls
        self.implicit = implicit
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
                    verb = command.partition(" ")[0].upper()
                    reply = self._reply(sock, *self._answer(command, verb, extensions))
                    if verb == "STARTTLS" and reply.startswith(b"220") and self.tls:
                        sock = self.tls.wrap_socket(sock, server_side=True)
                        reader = sock.makefile("rb")
                        # RFC 3207: a server offers no STARTTLS once TLS is up.
                        extensions = tuple(
                            one for one in extensions if one != "STARTTLS"
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
                "235 2.7.0 accepted"
                if command in {AUTH, XOAUTH2}
                else "535 5.7.8 rejected",
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


class Issuer:
    """A fake of the token endpoints of Microsoft and Google, which issues `token-1` and records each request.

    Once `failure` is set, every request raises it.
    """

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.clients: list[httpx2.Client] = []
        self.failure: Exception | None = None

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure

        if request.url.path.endswith("/openid-configuration"):
            return httpx2.Response(
                200,
                json={
                    "authorization_endpoint": f"{MICROSOFT}/oauth2/v2.0/authorize",
                    "token_endpoint": f"{MICROSOFT}/oauth2/v2.0/token",
                    "issuer": f"{MICROSOFT}/v2.0",
                },
            )

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


# --- Sending -----------------------------------------------------------------


def test_an_anonymous_send_submits_the_message_and_quits(serve: Callable[..., Server]):
    server = serve()

    result = backend(server).send(message())

    assert result.refused == {}
    assert server.verbs() == ["EHLO", "MAIL", "RCPT", "DATA", "QUIT"]
    assert server.commands[1].startswith("mail from:<reports@example.com>")
    assert server.commands[2] == "rcpt to:<ada@example.com>"
    assert f"Message-ID: {result.message_id}".encode() in server.messages[0]


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


# --- Credentials -------------------------------------------------------------


def test_a_password_logs_in_on_connect(serve: Callable[..., Server]):
    server = serve()

    with backend(server, credential=PASSWORD).connect():
        assert server.commands[-1] == AUTH


def test_a_wrong_password_raises_on_the_connect_line(serve: Callable[..., Server]):
    server = serve()
    wrong = backend(server, credential=smtp.Password(username="reports", password="x"))  # noqa: S106

    with pytest.raises(AuthenticationError) as caught:
        wrong.connect()

    assert caught.value.backend is wrong
    assert "MAIL" not in server.verbs()
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
    error = base64.b64encode(b'{"status":"400","schemes":"Bearer"}').decode()
    server = serve({"AUTH": f"334 {error}", "": "535 5.7.8 not accepted"})
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


def test_oauth_over_an_authorized_user_requests_the_gmail_smtp_scope(
    serve: Callable[..., Server],
    issuer: Issuer,
    authorized_user: gmail.AuthorizedUser,
):
    server = serve()
    oauth = smtp.OAuth(username="reports@example.com", credential=authorized_user)

    with backend(server, credential=oauth).connect():
        assert server.commands[-1] == XOAUTH2

    [token] = issuer.requests
    assert parse_qs(token.content.decode())["scope"] == [GMAIL]


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
            {"replies": {"AUTH": "535 5.7.8 rejected"}},
            {"credential": PASSWORD},
            SMTPAuthenticationError,
            AuthenticationError,
            id="SMTPAuthenticationError",
        ),
        pytest.param(
            {"extensions": ("8BITMIME",)},
            {"credential": PASSWORD},
            SMTPNotSupportedError,
            AuthenticationError,
            id="no AUTH at login",
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
            {"extensions": ("AUTH GSSAPI",)},
            {"credential": PASSWORD},
            SMTPException,
            AuthenticationError,
            id="a bare SMTPException from login",
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


@pytest.mark.parametrize("method", ["to", "reply_to"])
def test_a_non_ascii_address_puts_smtputf8_in_mail_from_once(
    serve: Callable[..., Server], method: str
):
    server = serve()

    backend(server).send(getattr(message(), method)(NON_ASCII))

    mail = server.commands[server.verbs().index("MAIL")]
    assert mail.count("SMTPUTF8") == 1
    assert mail.count("BODY=8BITMIME") == 1
    assert NON_ASCII.encode() in server.messages[0]


# smtplib checks a non-ASCII envelope itself, and Epistole checks the Reply-To case.
@pytest.mark.parametrize(
    ("method", "cause"), [("to", SMTPNotSupportedError), ("reply_to", NoneType)]
)
@pytest.mark.parametrize(
    "replies", [{}, {"EHLO": "502 5.5.1 no"}], ids=["EHLO", "HELO"]
)
def test_a_non_ascii_address_without_smtputf8_is_rejected_before_mail_from(
    serve: Callable[..., Server],
    method: str,
    cause: type[BaseException | None],
    replies: dict[str, Reply],
):
    server = serve(replies, extensions=("8BITMIME",))

    with pytest.raises(RejectedError) as caught:
        backend(server).send(getattr(message(), method)(NON_ASCII))

    assert type(caught.value.__cause__) is cause
    assert "MAIL" not in server.verbs()

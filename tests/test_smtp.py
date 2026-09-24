import base64
import contextlib
import shutil
import socket
import ssl
import subprocess
import threading
from collections.abc import Callable, Iterator
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
from typing import Any

import pytest

from epistole import Message, Refusal, SMTPBackend, smtp
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RecipientsRefusedError,
    RejectedError,
    SenderRefusedError,
    TransportError,
)

EXTENSIONS = ("SIZE 10485760", "8BITMIME", "SMTPUTF8", "AUTH PLAIN")
STARTTLS = (*EXTENSIONS, "STARTTLS")
PASSWORD = smtp.Password(username="reports", password="hunter2")  # noqa: S106
AUTH = f"AUTH PLAIN {base64.b64encode(b'\0reports\0hunter2').decode()}"

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
                "235 2.7.0 accepted" if command == AUTH else "535 5.7.8 rejected",
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

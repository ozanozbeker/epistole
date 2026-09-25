import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import parse_qs

import httpx2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from msal.exceptions import MsalServiceError

from epistole import (
    Address,
    GraphBackend,
    Message,
    Submission,
    TokenCredential,
    gmail,
    graph,
)
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RejectedError,
    SenderRefusedError,
    ThrottledError,
    TransportError,
)

PDF = b"%PDF-1.7 weekly numbers"
PNG = b"\x89PNG\r\n\x1a\n logo"

TENANT = "contoso.onmicrosoft.com"
DISCOVERY = (
    f"https://login.microsoftonline.com/{TENANT}/v2.0/.well-known/openid-configuration"
)
TOKEN_URI = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
IMDS = "http://169.254.169.254/metadata/identity/oauth2/token"
MAILBOX = "https://graph.microsoft.com/v1.0/users/reports@example.com"
SEND_MAIL = f"{MAILBOX}/sendMail"
DRAFTS = f"{MAILBOX}/messages"
DRAFT = f"{DRAFTS}/draft-1"
UPLOAD = "https://outlook.office.com/api/v2.0/Users('reports@example.com')/Messages('draft-1')/AttachmentSessions('session-1')"
AUDIENCE = "https://graph.microsoft.com"
SCOPE = "https://graph.microsoft.com/.default"

type Reply = httpx2.Response | Exception


def url(request: httpx2.Request) -> str:
    """Return the URL of `request` without its query."""
    return str(request.url).partition("?")[0]


class Microsoft:
    """A fake of Microsoft's identity platform and Graph, which every `httpx2.Client` the backend builds sends to.

    `replies` maps a URL to the replies it serves first, in order. An exception among them is raised rather than returned. After those, a token endpoint issues `token-1`, `token-2`, and so on, and every mail endpoint accepts. The draft it creates is `DRAFT`, and the upload session is `UPLOAD`.
    """

    def __init__(self) -> None:
        self.replies: dict[str, list[Reply]] = {}
        self.requests: list[httpx2.Request] = []
        self.clients: list[httpx2.Client] = []
        self._issued = 0

    def sent(self) -> list[httpx2.Request]:
        """Return each `sendMail` request."""
        return [one for one in self.requests if url(one).endswith("/sendMail")]

    def calls(self) -> list[tuple[str, str]]:
        """Return the method and URL of each request to a mail endpoint."""
        return [
            (one.method, url(one))
            for one in self.requests
            if url(one) not in {DISCOVERY, TOKEN_URI, IMDS}
        ]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        where = url(request)
        if self.replies.get(where):
            reply = self.replies[where].pop(0)
            if isinstance(reply, Exception):
                raise reply

            return reply

        if where == DISCOVERY:
            return httpx2.Response(
                200,
                json={
                    "authorization_endpoint": f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize",
                    "token_endpoint": TOKEN_URI,
                    "issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0",
                },
            )

        if where in {TOKEN_URI, IMDS}:
            self._issued += 1
            return httpx2.Response(
                200,
                json={
                    "access_token": f"token-{self._issued}",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )

        created = {
            DRAFTS: {"id": "draft-1"},
            f"{DRAFT}/attachments/createUploadSession": {
                "uploadUrl": f"{UPLOAD}?authtoken=eyJ0"
            },
        }.get(where)
        if created is not None:
            return httpx2.Response(201, json=created)

        if where.endswith("/sendMail") or where.startswith((DRAFT, UPLOAD)):
            return httpx2.Response(202)

        return httpx2.Response(404)


@pytest.fixture
def microsoft(monkeypatch: pytest.MonkeyPatch) -> Microsoft:
    """Send every request of every `httpx2.Client` the backend builds to a fake Microsoft, keeping the options the backend set."""
    fake = Microsoft()
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


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def private_key(rsa_key: rsa.RSAPrivateKey) -> str:
    return rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def pfx(tmp_path: Path, rsa_key: rsa.RSAPrivateKey) -> Path:
    """Write a PKCS #12 file holding the key and a self-signed certificate, encrypted with `hunter2`."""
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "epistole")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(rsa_key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(rsa_key, hashes.SHA256())
    )
    path = tmp_path / "epistole.pfx"
    path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"epistole",
            rsa_key,
            certificate,
            None,
            serialization.BestAvailableEncryption(b"hunter2"),
        )
    )
    return path


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
    credential: graph.ClientSecret
    | graph.Certificate
    | graph.ManagedIdentity
    | TokenCredential,
    from_address: str = "Reports <reports@example.com>",
) -> GraphBackend:
    return GraphBackend(from_address=from_address, credential=credential)


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


def error(
    status: int, code: str | None = None, *, headers: dict[str, str] | None = None
) -> httpx2.Response:
    """Build a Graph error reply in Graph's envelope, with `code` as its `error.code`."""
    body = {"error": {"code": code or "UnknownError", "message": "Refused."}}
    return httpx2.Response(status, json=body, headers=headers)


# --- Sending -----------------------------------------------------------------


def test_a_send_posts_one_sendmail_request_to_the_from_mailbox(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    result = backend(secret).send(message())

    [request] = microsoft.sent()
    assert request.method == "POST"
    assert str(request.url) == SEND_MAIL
    assert request.headers["Authorization"] == "Bearer token-1"
    assert json.loads(request.content) == {
        "message": {
            "from": {
                "emailAddress": {"address": "reports@example.com", "name": "Reports"}
            },
            "toRecipients": [{"emailAddress": {"address": "ada@example.com"}}],
            "subject": "Weekly numbers",
            "body": {"contentType": "text", "content": "Weekly numbers"},
            "internetMessageId": result.message_id,
        }
    }
    assert result.refused == {}


def test_the_mailbox_is_the_from_address_percent_encoded_into_the_path(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    backend(secret, from_address='"a/b?c#d%"@example.com').send(message())

    [request] = microsoft.sent()
    assert (
        request.url.raw_path
        == b"/v1.0/users/%22a%2Fb%3Fc%23d%25%22@example.com/sendMail"
    )


def test_a_display_name_goes_out_as_text_rather_than_as_encoded_words(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    # Address() writes a non-ASCII display name as RFC 2047 encoded-words.
    configured = backend(
        secret, from_address=Address("Zoë Reports", "reports@example.com")
    )

    configured.send(message(Address("Zoë Lovelace", "zoe@example.com")))

    fields = json.loads(microsoft.sent()[0].content)["message"]
    assert fields["from"]["emailAddress"]["name"] == "Zoë Reports"
    assert fields["toRecipients"][0]["emailAddress"]["name"] == "Zoë Lovelace"


def test_html_goes_out_alone_beside_every_address_header_and_attachment(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    html = '<p>Weekly numbers</p><img src="cid:logo.png" alt="Logo">'
    sent = (
        Message(html=html, text="Ignored by Graph")
        .to(Address("Ada Lovelace", "ada@example.com"))
        .cc("cleo@example.com")
        .bcc("bo@example.com", "di@example.com")
        .reply_to("desk@example.com")
        .headers({"X-Campaign-Id": "autumn"})
        .attach(PDF, filename="numbers.pdf")
        .embed(PNG, filename="logo.png")
    )

    backend(secret).send(sent)

    fields = json.loads(microsoft.sent()[0].content)["message"]
    del fields["from"], fields["internetMessageId"]
    assert fields == {
        "toRecipients": [
            {"emailAddress": {"address": "ada@example.com", "name": "Ada Lovelace"}}
        ],
        "ccRecipients": [{"emailAddress": {"address": "cleo@example.com"}}],
        "bccRecipients": [
            {"emailAddress": {"address": "bo@example.com"}},
            {"emailAddress": {"address": "di@example.com"}},
        ],
        "replyTo": [{"emailAddress": {"address": "desk@example.com"}}],
        "body": {"contentType": "html", "content": html},
        "internetMessageHeaders": [{"name": "X-Campaign-Id", "value": "autumn"}],
        "attachments": [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": "numbers.pdf",
                "contentType": "application/pdf",
                "contentBytes": "JVBERi0xLjcgd2Vla2x5IG51bWJlcnM=",
            },
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": "logo.png",
                "contentType": "image/png",
                "contentBytes": "iVBORw0KGgogbG9nbw==",
                "isInline": True,
                "contentId": "logo.png",
            },
        ],
    }


# --- Pre-checks --------------------------------------------------------------


def test_more_than_500_recipients_is_rejected_before_writing(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    recipients = [f"r{n}@example.com" for n in range(501)]

    with backend(secret).connect() as connection:
        with pytest.raises(RejectedError, match="501") as caught:
            connection.send(message(*recipients))

        connection.send(message(*recipients[:500]))

    assert caught.value.__cause__ is None
    assert len(microsoft.sent()) == 1


def test_a_custom_header_not_starting_with_x_is_rejected_naming_it(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    headers = {"x-mailer": "epistole", "List-Unsubscribe": "<mailto:u@example.com>"}

    with backend(secret).connect() as connection:
        with pytest.raises(RejectedError, match="List-Unsubscribe") as caught:
            connection.send(message().headers(headers))

        connection.send(message().headers({"X-Campaign-Id": "autumn"}))

    assert caught.value.__cause__ is None
    assert len(microsoft.sent()) == 1


def test_an_attachment_over_150_000_000_bytes_is_rejected_before_writing(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    archive = message().attach(bytes(150_000_001), filename="archive.zip")

    with pytest.raises(RejectedError, match="150,000,001") as caught:
        backend(secret).send(archive)

    assert caught.value.__cause__ is None
    assert microsoft.calls() == []


def test_a_body_of_4_000_000_bytes_or_more_goes_out_through_a_draft(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    # Connection.send sets a Message-ID whose length varies, so this pins one on a submission.
    transport = backend(secret)._open()
    attached = message().attach(bytes(2_990_000), filename="numbers.bin")
    transport.submit(submission(attached))
    short = 3_999_999 - len(microsoft.sent()[0].content)

    transport.submit(submission(attached.subject("Weekly numbers" + "x" * short)))
    transport.submit(submission(attached.subject("Weekly numbers" + "x" * (short + 1))))

    assert len(microsoft.sent()[1].content) == 3_999_999
    assert microsoft.calls() == [
        ("POST", SEND_MAIL),
        ("POST", SEND_MAIL),
        ("POST", DRAFTS),
        ("POST", f"{DRAFT}/attachments"),
        ("POST", f"{DRAFT}/send"),
    ]


def test_a_draft_is_created_without_attachments_then_each_is_added_in_order(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    html = '<p>Weekly numbers</p><img src="cid:logo.png" alt="Logo">'
    sent = (
        Message(html=html)
        .to("ada@example.com")
        .subject("Weekly numbers")
        .headers({"X-Campaign-Id": "autumn"})
        .attach(bytes(2_000_000), filename="january.bin")
        .attach(PDF, filename="numbers.pdf")
        .attach(bytes(2_000_000), filename="february.bin")
        .embed(PNG, filename="logo.png")
    )

    result = backend(secret).send(sent)

    assert microsoft.calls() == [
        ("POST", DRAFTS),
        *[("POST", f"{DRAFT}/attachments")] * 4,
        ("POST", f"{DRAFT}/send"),
    ]
    [created] = [one for one in microsoft.requests if url(one) == DRAFTS]
    assert json.loads(created.content) == {
        "from": {"emailAddress": {"address": "reports@example.com", "name": "Reports"}},
        "toRecipients": [{"emailAddress": {"address": "ada@example.com"}}],
        "subject": "Weekly numbers",
        "body": {"contentType": "html", "content": html},
        "internetMessageId": result.message_id,
        "internetMessageHeaders": [{"name": "X-Campaign-Id", "value": "autumn"}],
    }
    added = [
        json.loads(one.content)
        for one in microsoft.requests
        if url(one) == f"{DRAFT}/attachments"
    ]
    assert [one["name"] for one in added] == [
        "january.bin",
        "numbers.pdf",
        "february.bin",
        "logo.png",
    ]
    assert added[-1] == {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": "logo.png",
        "contentType": "image/png",
        "contentBytes": "iVBORw0KGgogbG9nbw==",
        "isInline": True,
        "contentId": "logo.png",
    }


def test_an_attachment_of_3_000_000_bytes_or_more_goes_up_in_puts_without_the_bearer(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    sent = (
        message()
        .attach(bytes(2_999_999), filename="january.bin")
        .attach(bytes(6_000_001), filename="february.bin")
        .embed(bytes(3_000_000), filename="chart.png")
    )

    backend(secret).send(sent)

    assert microsoft.calls() == [
        ("POST", DRAFTS),
        ("POST", f"{DRAFT}/attachments"),
        ("POST", f"{DRAFT}/attachments/createUploadSession"),
        *[("PUT", UPLOAD)] * 3,
        ("POST", f"{DRAFT}/attachments/createUploadSession"),
        ("PUT", UPLOAD),
        ("POST", f"{DRAFT}/send"),
    ]
    sessions = [
        json.loads(one.content)
        for one in microsoft.requests
        if url(one).endswith("/createUploadSession")
    ]
    assert sessions == [
        {
            "AttachmentItem": {
                "attachmentType": "file",
                "name": "february.bin",
                "size": 6_000_001,
                "contentType": "application/octet-stream",
            }
        },
        {
            "AttachmentItem": {
                "attachmentType": "file",
                "name": "chart.png",
                "size": 3_000_000,
                "contentType": "image/png",
                "isInline": True,
                "contentId": "chart.png",
            }
        },
    ]
    puts = [one for one in microsoft.requests if one.method == "PUT"]
    assert [one.headers["Content-Range"] for one in puts] == [
        "bytes 0-2999999/6000001",
        "bytes 3000000-5999999/6000001",
        "bytes 6000000-6000000/6000001",
        "bytes 0-2999999/3000000",
    ]
    assert [len(one.content) for one in puts] == [3_000_000, 3_000_000, 1, 3_000_000]
    for put in puts:
        assert str(put.url) == f"{UPLOAD}?authtoken=eyJ0"
        assert put.headers["Content-Type"] == "application/octet-stream"
        assert "Authorization" not in put.headers


def test_a_401_on_an_upload_put_is_an_authentication_error_without_a_retry(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    microsoft.replies[UPLOAD] = [httpx2.Response(401)]

    with pytest.raises(AuthenticationError) as caught:
        backend(secret).send(message().attach(bytes(4_000_000), filename="big.bin"))

    assert isinstance(caught.value.__cause__, httpx2.HTTPStatusError)
    assert microsoft.calls().count(("PUT", UPLOAD)) == 1
    assert [url(one) for one in microsoft.requests].count(TOKEN_URI) == 1


@pytest.mark.parametrize(
    ("where", "deleted"),
    [
        pytest.param(
            f"{DRAFT}/attachments/createUploadSession",
            [(DRAFT, True)],
            id="creating the session",
        ),
        pytest.param(UPLOAD, [(UPLOAD, False), (DRAFT, True)], id="uploading"),
        pytest.param(f"{DRAFT}/send", [(DRAFT, True)], id="sending"),
    ],
)
def test_a_failure_after_the_draft_exists_deletes_the_open_session_then_the_draft(
    microsoft: Microsoft,
    secret: graph.ClientSecret,
    where: str,
    deleted: list[tuple[str, bool]],
):
    failure = httpx2.ConnectError("refused")
    microsoft.replies[where] = [failure]

    with backend(secret).connect() as connection:
        with pytest.raises(TransportError) as caught:
            connection.send(message().attach(bytes(4_000_000), filename="big.bin"))

        assert microsoft.clients[0].is_closed

    assert caught.value.__cause__ is failure
    # Only the draft's DELETE carries the bearer, because the upload URL holds its own token.
    assert [
        (url(one), "Authorization" in one.headers)
        for one in microsoft.requests
        if one.method == "DELETE"
    ] == deleted


def test_a_failed_delete_does_not_replace_the_original_error(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    microsoft.replies[UPLOAD] = [
        error(503, "ServiceNotAvailable"),
        httpx2.ConnectError("refused"),
    ]
    microsoft.replies[DRAFT] = [error(500, "InternalServerError")]

    with pytest.raises(ProviderError, match="503") as caught:
        backend(secret).send(message().attach(bytes(4_000_000), filename="big.bin"))

    assert isinstance(caught.value.__cause__, httpx2.HTTPStatusError)
    assert microsoft.calls()[-2:] == [("DELETE", UPLOAD), ("DELETE", DRAFT)]


def test_a_403_on_creating_the_draft_is_an_authentication_error_that_deletes_nothing(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    # An app without Mail.ReadWrite gets this before any draft exists (ADR-0012).
    microsoft.replies[DRAFTS] = [error(403, "ErrorAccessDenied")]

    with pytest.raises(AuthenticationError):
        backend(secret).send(message().attach(bytes(4_000_000), filename="big.bin"))

    assert microsoft.calls() == [("POST", DRAFTS)]


def test_a_401_partway_through_a_draft_re_sends_only_the_request_that_got_it(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    microsoft.replies[f"{DRAFT}/attachments"] = [httpx2.Response(401)]
    sent = (
        message()
        .attach(bytes(2_000_000), filename="january.bin")
        .attach(bytes(2_000_000), filename="february.bin")
    )

    backend(secret).send(sent)

    assert [
        (url(one), one.headers["Authorization"])
        for one in microsoft.requests
        if one.url.host == "graph.microsoft.com"
    ] == [
        (DRAFTS, "Bearer token-1"),
        (f"{DRAFT}/attachments", "Bearer token-1"),
        (f"{DRAFT}/attachments", "Bearer token-2"),
        (f"{DRAFT}/attachments", "Bearer token-2"),
        (f"{DRAFT}/send", "Bearer token-2"),
    ]


@pytest.mark.parametrize(
    ("where", "deleted"),
    [
        pytest.param(DRAFTS, [], id="draft"),
        pytest.param(
            f"{DRAFT}/attachments/createUploadSession", [DRAFT], id="upload session"
        ),
    ],
)
def test_a_reply_without_the_draft_id_or_upload_url_is_a_provider_error(
    microsoft: Microsoft, secret: graph.ClientSecret, where: str, deleted: list[str]
):
    microsoft.replies[where] = [httpx2.Response(201, json={})]

    with pytest.raises(ProviderError, match="Graph's reply"):
        backend(secret).send(message().attach(bytes(4_000_000), filename="big.bin"))

    assert [url(one) for one in microsoft.requests if one.method == "DELETE"] == deleted


# --- Credentials -------------------------------------------------------------


def test_a_client_secret_requests_the_default_scope(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    backend(secret).connect()

    [token] = [one for one in microsoft.requests if url(one) == TOKEN_URI]
    form = parse_qs(token.content.decode())
    assert form["grant_type"] == ["client_credentials"]
    assert form["client_secret"] == ["hunter2"]
    assert form["scope"] == [SCOPE]


@pytest.mark.parametrize("form", ["pfx", "private_key"])
def test_a_certificate_signs_an_assertion_for_the_default_scope(
    microsoft: Microsoft, pfx: Path, private_key: str, form: str
):
    certificate = (
        graph.Certificate(TENANT, "epistole", pfx=pfx, passphrase="hunter2")  # noqa: S106
        if form == "pfx"
        else graph.Certificate(
            TENANT, "epistole", private_key=private_key, thumbprint="a1b2c3d4" * 5
        )
    )

    backend(certificate).connect()

    [token] = [one for one in microsoft.requests if url(one) == TOKEN_URI]
    sent = parse_qs(token.content.decode())
    assert sent["client_assertion_type"] == [
        "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    ]
    assert "client_assertion" in sent
    assert "client_secret" not in sent
    assert sent["scope"] == [SCOPE]


@pytest.mark.parametrize(("client_id", "expected"), [(None, None), ("7f3c", ["7f3c"])])
def test_a_managed_identity_requests_the_graph_resource(
    microsoft: Microsoft, client_id: str | None, expected: list[str] | None
):
    backend(graph.ManagedIdentity(client_id)).send(message())

    [token] = [one for one in microsoft.requests if url(one) == IMDS]
    query = parse_qs(token.url.query.decode())
    assert query["resource"] == [AUDIENCE]
    assert query.get("client_id") == expected
    assert "scope" not in query
    assert microsoft.sent()[0].headers["Authorization"] == "Bearer token-1"


def test_get_token_is_called_with_the_default_scope_before_each_request(
    microsoft: Microsoft,
):
    credential = Credential()

    with backend(credential).connect() as connection:
        connection.send(message())
        connection.send(message())

    assert credential.scopes == [(SCOPE,)] * 3
    assert [one.headers["Authorization"] for one in microsoft.sent()] == [
        "Bearer foreign-2",
        "Bearer foreign-3",
    ]


def test_connect_reads_the_pfx_and_the_constructor_does_not(
    microsoft: Microsoft, tmp_path: Path
):
    missing = backend(
        graph.Certificate(TENANT, "epistole", pfx=tmp_path / "missing.pfx")
    )

    with pytest.raises(FileNotFoundError):
        missing.connect()

    assert all(one.is_closed for one in microsoft.clients)


@pytest.mark.parametrize(
    "form",
    [
        pytest.param({}, id="neither form"),
        pytest.param(
            {"pfx": Path("app.pfx"), "private_key": "key", "thumbprint": "a1"},
            id="both forms",
        ),
        pytest.param({"private_key": "key"}, id="private_key alone"),
        pytest.param({"thumbprint": "a1"}, id="thumbprint alone"),
        pytest.param(
            {"passphrase": "hunter2", "private_key": "key", "thumbprint": "a1"},
            id="passphrase without pfx",
        ),
    ],
)
def test_a_certificate_takes_exactly_one_complete_form(form: dict[str, Any]):
    with pytest.raises(TypeError, match="pfx"):
        graph.Certificate(TENANT, "epistole", **form)


@pytest.mark.parametrize(
    "credential",
    [
        graph.ClientSecret(TENANT, "epistole", "hunter2"),
        graph.Certificate(
            TENANT,
            "epistole",
            pfx=Path("app.pfx"),
            passphrase="hunter2",  # noqa: S106
        ),
        graph.Certificate(TENANT, "epistole", private_key="hunter2", thumbprint="a1"),
    ],
    ids=["client secret", "pfx", "private key"],
)
def test_a_secret_stays_out_of_the_repr(
    credential: graph.ClientSecret | graph.Certificate,
):
    assert "hunter2" not in repr(credential)


@pytest.mark.parametrize(
    "credential",
    ["token", gmail.AuthorizedUser(Path("authorized-user.json"))],
    ids=["str", "gmail.AuthorizedUser"],
)
def test_a_credential_of_another_type_raises(credential: object):
    with pytest.raises(TypeError, match=type(credential).__name__):
        backend(credential)  # pyrefly: ignore


@pytest.mark.parametrize("module", ["httpx2", "msal"])
def test_the_constructor_raises_naming_the_extra_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch, secret: graph.ClientSecret, module: str
):
    monkeypatch.setitem(sys.modules, module, None)

    with pytest.raises(ImportError, match=r"epistole\[graph\]"):
        backend(secret)


# --- Connecting --------------------------------------------------------------


def test_connect_gets_a_token_on_one_client_and_requests_no_mail_endpoint(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    with backend(secret).connect() as connection:
        assert [url(one) for one in microsoft.requests] == [DISCOVERY, TOKEN_URI]
        connection.send(message())
        connection.send(message())

    assert [url(one) for one in microsoft.requests] == [
        DISCOVERY,
        TOKEN_URI,
        SEND_MAIL,
        SEND_MAIL,
    ]
    assert len(microsoft.clients) == 1
    assert microsoft.clients[0].is_closed


def test_a_rejected_credential_is_an_authentication_error_on_the_connect_line(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    microsoft.replies[TOKEN_URI] = [
        httpx2.Response(
            401,
            json={
                "error": "invalid_client",
                "error_description": "AADSTS7000215: Invalid client secret provided.",
            },
        )
    ]
    configured = backend(secret)

    with pytest.raises(AuthenticationError, match="AADSTS7000215") as caught:
        configured.connect()

    # msal returns its error as a dict and raises nothing, so there is no cause.
    assert caught.value.__cause__ is None
    assert [url(one) for one in microsoft.requests] == [DISCOVERY, TOKEN_URI]
    assert caught.value.backend is configured
    assert microsoft.clients[0].is_closed


@pytest.mark.parametrize("where", [DISCOVERY, TOKEN_URI], ids=["discovery", "token"])
def test_a_network_failure_on_connect_is_a_transport_error(
    microsoft: Microsoft, secret: graph.ClientSecret, where: str
):
    failure = httpx2.ConnectError("refused")
    microsoft.replies[where] = [failure]

    with pytest.raises(TransportError) as caught:
        backend(secret).connect()

    assert caught.value.__cause__ is failure
    assert microsoft.clients[0].is_closed


@pytest.mark.parametrize("where", [DISCOVERY, TOKEN_URI], ids=["discovery", "token"])
def test_a_5xx_from_the_identity_platform_is_a_provider_error(
    microsoft: Microsoft, secret: graph.ClientSecret, where: str
):
    microsoft.replies[where] = [httpx2.Response(503)]

    with pytest.raises(ProviderError) as caught:
        backend(secret).connect()

    assert isinstance(caught.value.__cause__, MsalServiceError)
    assert microsoft.clients[0].is_closed


@pytest.mark.parametrize("kind", ["client secret", "managed identity"])
def test_a_token_reply_that_is_not_json_is_a_provider_error(
    microsoft: Microsoft, secret: graph.ClientSecret, kind: str
):
    where, credential = (
        (TOKEN_URI, secret)
        if kind == "client secret"
        else (IMDS, graph.ManagedIdentity())
    )
    microsoft.replies[where] = [httpx2.Response(200, text="<html>Sign in</html>")]

    with pytest.raises(ProviderError) as caught:
        backend(credential).connect()

    assert isinstance(caught.value.__cause__, json.JSONDecodeError)
    assert microsoft.clients[0].is_closed


# --- Refreshing on 401 -------------------------------------------------------


@pytest.mark.parametrize("kind", ["client secret", "managed identity"])
def test_a_401_gets_a_new_token_and_retries_the_request_once(
    microsoft: Microsoft, secret: graph.ClientSecret, kind: str
):
    microsoft.replies[SEND_MAIL] = [httpx2.Response(401)]
    credential = secret if kind == "client secret" else graph.ManagedIdentity()

    backend(credential).send(message())

    assert [one.headers["Authorization"] for one in microsoft.sent()] == [
        "Bearer token-1",
        "Bearer token-2",
    ]


def test_a_second_401_on_the_same_request_is_an_authentication_error(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    microsoft.replies[SEND_MAIL] = [httpx2.Response(401), httpx2.Response(401)]
    configured = backend(secret)

    with pytest.raises(AuthenticationError) as caught:
        configured.send(message())

    assert isinstance(caught.value.__cause__, httpx2.HTTPStatusError)
    assert caught.value.backend is configured
    assert len(microsoft.sent()) == 2


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        pytest.param(
            httpx2.Response(400, json={"error": "invalid_client"}),
            AuthenticationError,
            id="rejected",
        ),
        pytest.param(
            httpx2.ConnectError("refused"), TransportError, id="network failure"
        ),
    ],
)
def test_a_failed_token_request_after_a_401_maps_as_it_does_on_connect(
    microsoft: Microsoft,
    secret: graph.ClientSecret,
    failure: Reply,
    expected: type[EpistoleError],
):
    microsoft.replies[SEND_MAIL] = [httpx2.Response(401)]
    microsoft.replies[TOKEN_URI] = [
        httpx2.Response(200, json={"access_token": "token-1", "expires_in": 3600}),
        failure,
    ]

    with backend(secret).connect() as connection:
        with pytest.raises(expected):
            connection.send(message())

        # Only a TransportError closes the connection (ADR-0005).
        assert microsoft.clients[0].is_closed is (expected is TransportError)


# --- Mapping -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        pytest.param(error(400, "ErrorInvalidRecipients"), RejectedError, id="400"),
        pytest.param(
            error(400, "ErrorMimeContentInvalidBase64String"),
            RejectedError,
            id="400 ErrorMimeContentInvalidBase64String",
        ),
        pytest.param(error(404, "ErrorItemNotFound"), RejectedError, id="404"),
        pytest.param(error(413, "RequestEntityTooLarge"), RejectedError, id="413"),
        pytest.param(error(415, "UnsupportedMediaType"), RejectedError, id="415"),
        pytest.param(
            error(403, "ErrorSendAsDenied"),
            SenderRefusedError,
            id="403 ErrorSendAsDenied",
        ),
        pytest.param(
            error(403, "ErrorAccessDenied"), AuthenticationError, id="any other 403"
        ),
        pytest.param(
            httpx2.Response(403, text="Forbidden"),
            AuthenticationError,
            id="403 outside Graph's envelope",
        ),
        pytest.param(error(429, "TooManyRequests"), ThrottledError, id="429"),
        pytest.param(
            error(400, "ErrorSendAsDenied"), RejectedError, id="400 qualified"
        ),
        pytest.param(error(409, "ErrorIrresolvableConflict"), ProviderError, id="409"),
        pytest.param(error(500, "InternalServerError"), ProviderError, id="500"),
        pytest.param(error(503, "ServiceNotAvailable"), ProviderError, id="503"),
        pytest.param(error(504, "GatewayTimeout"), ProviderError, id="504"),
        pytest.param(error(509, "BandwidthLimitExceeded"), ProviderError, id="509"),
        pytest.param(error(418), ProviderError, id="a status no row matches"),
    ],
)
def test_a_reply_maps_to_its_row(
    microsoft: Microsoft,
    secret: graph.ClientSecret,
    reply: httpx2.Response,
    expected: type[EpistoleError],
):
    microsoft.replies[SEND_MAIL] = [reply]
    configured = backend(secret)

    with pytest.raises(EpistoleError) as caught:
        configured.send(message())

    assert type(caught.value) is expected
    assert isinstance(caught.value.__cause__, httpx2.HTTPStatusError)
    assert caught.value.backend is configured


def test_a_429_carries_its_retry_after(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    microsoft.replies[SEND_MAIL] = [
        error(429, "TooManyRequests", headers={"Retry-After": "10"})
    ]

    with pytest.raises(ThrottledError) as caught:
        backend(secret).send(message())

    assert caught.value.retry_after == 10


@pytest.mark.parametrize(
    "failure", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("timed out")]
)
def test_a_network_failure_on_a_send_is_a_transport_error_that_closes_the_connection(
    microsoft: Microsoft, secret: graph.ClientSecret, failure: Exception
):
    microsoft.replies[SEND_MAIL] = [failure]
    configured = backend(secret)

    with configured.connect() as connection:
        with pytest.raises(TransportError) as caught:
            connection.send(message())

        assert microsoft.clients[0].is_closed

    assert caught.value.__cause__ is failure
    assert caught.value.backend is configured


def test_a_reply_that_does_not_decode_is_a_provider_error(
    microsoft: Microsoft, secret: graph.ClientSecret
):
    microsoft.replies[SEND_MAIL] = [
        httpx2.Response(
            202,
            headers={"Content-Encoding": "gzip"},
            stream=httpx2.ByteStream(b"not gzip"),
        )
    ]

    with pytest.raises(ProviderError) as caught:
        backend(secret).send(message())

    assert isinstance(caught.value.__cause__, httpx2.DecodingError)

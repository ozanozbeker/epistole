import base64
import json
import re
import sys
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, NamedTuple
from urllib.parse import parse_qs

import httpx2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from google.auth.exceptions import GoogleAuthError, MalformedError

from epistole import _msal, _tokens, gmail, graph
from epistole._tokens import Purpose
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    TransportError,
)

GOOGLE = "https://oauth2.googleapis.com/token"
TENANT = "contoso.onmicrosoft.com"
DISCOVERY = (
    f"https://login.microsoftonline.com/{TENANT}/v2.0/.well-known/openid-configuration"
)
MICROSOFT = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
IMDS = "http://169.254.169.254/metadata/identity/oauth2/token"
APP_SERVICE = "http://localhost:8081/msi/token"
OPENID_CONFIGURATION = {
    "authorization_endpoint": f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize",
    "token_endpoint": MICROSOFT,
    "issuer": f"https://login.microsoftonline.com/{TENANT}/v2.0",
}

GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SMTP = "https://mail.google.com/"
GRAPH = "https://graph.microsoft.com"
OUTLOOK = "https://outlook.office365.com"

UNAVAILABLE = {
    "error": "temporarily_unavailable",
    "error_description": "Try again later.",
}

DEEP = b"[" * 1_000_000 + b"]" * 1_000_000
"""JSON nested too deeply for `json`, which raises `RecursionError` reading it (ADR-0009). 3.14.7 bounds the depth by the C stack, so it parses 100,000 levels on Linux x86-64 and raises on macOS arm64."""

ISSUERS: dict[str, tuple[Purpose, str]] = {
    "service_account": ("gmail", GOOGLE),
    "authorized_user": ("gmail", GOOGLE),
    "user_with_saved_token": ("gmail", GOOGLE),
    "secret": ("graph", MICROSOFT),
    "certificate": ("graph", MICROSOFT),
    "managed_identity": ("graph", IMDS),
}
"""The purpose each credential fixture gets its tokens for here, and the endpoint it requests them from."""

type Reply = httpx2.Response | Exception


def url(request: httpx2.Request) -> str:
    """Return the URL of `request` without its query."""
    return str(request.url).partition("?")[0]


class Issuer:
    """A fake of the token endpoints of Google and Microsoft, which issues `token-1`, `token-2`, and so on.

    `replies` maps a URL to the replies it serves first, in order. An exception among them is raised rather than returned. `client` sends to the fake, as the client `RESTTransport.connect` passes to `tokens` does.
    """

    def __init__(self) -> None:
        self.replies: dict[str, list[Reply]] = {}
        self.requests: list[httpx2.Request] = []
        self.client = httpx2.Client(transport=httpx2.MockTransport(self))
        self._issued = 0

    def tokens(self) -> list[httpx2.Request]:
        """Return each token request, leaving out msal's discovery request."""
        return [one for one in self.requests if url(one) in {GOOGLE, MICROSOFT, IMDS}]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        where = url(request)
        if self.replies.get(where):
            reply = self.replies[where].pop(0)
            if isinstance(reply, Exception):
                raise reply

            return reply

        if where == DISCOVERY:
            return httpx2.Response(200, json=OPENID_CONFIGURATION)

        if where in {GOOGLE, MICROSOFT, IMDS}:
            self._issued += 1
            return httpx2.Response(
                200,
                json={
                    "access_token": f"token-{self._issued}",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )

        return httpx2.Response(404)


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> Iterator[Issuer]:
    # msal reads these to pick a managed identity endpoint other than a VM's.
    for name in ("IDENTITY_ENDPOINT", "MSI_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)

    fake = Issuer()
    with fake.client:
        yield fake


@pytest.fixture
def clients(issuer: Issuer, monkeypatch: pytest.MonkeyPatch) -> list[httpx2.Client]:
    """Send every request of every `httpx2.Client` that `token` builds to `issuer`, and return those clients."""
    built: list[httpx2.Client] = []
    build = httpx2.Client

    def client(**options: Any) -> httpx2.Client:
        built.append(build(transport=httpx2.MockTransport(issuer), **options))
        return built[-1]

    monkeypatch.setattr(httpx2, "Client", client)
    return built


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
def service_account(tmp_path: Path, private_key: str) -> gmail.ServiceAccount:
    path = tmp_path / "service-account.json"
    key = {
        "type": "service_account",
        "client_email": "epistole@project.iam.gserviceaccount.com",
        "private_key": private_key,
        "token_uri": GOOGLE,
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


@pytest.fixture
def user_with_saved_token(
    authorized_user: gmail.AuthorizedUser,
) -> gmail.AuthorizedUser:
    """Save an unexpired access token in `authorized_user`'s file, as `Credentials.to_json()` writes one."""
    consent = json.loads(authorized_user.path.read_text())
    consent |= {"token": "saved-token", "expiry": "2099-01-01T00:00:00Z"}
    authorized_user.path.write_text(json.dumps(consent))
    return authorized_user


@pytest.fixture
def secret() -> graph.ClientSecret:
    return graph.ClientSecret(TENANT, "epistole", "hunter2")


@pytest.fixture
def certificate(private_key: str) -> graph.Certificate:
    return graph.Certificate(
        TENANT, "epistole", private_key=private_key, thumbprint="a1b2c3d4" * 5
    )


@pytest.fixture
def pfx(tmp_path: Path, rsa_key: rsa.RSAPrivateKey) -> Path:
    """Write a PKCS #12 file holding the key and a self-signed certificate, encrypted with `hunter2`."""
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "epistole")])
    now = datetime.now(UTC)
    signed = (
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
            signed,
            None,
            serialization.BestAvailableEncryption(b"hunter2"),
        )
    )
    return path


@pytest.fixture
def pfx_certificate(pfx: Path) -> graph.Certificate:
    return graph.Certificate(TENANT, "epistole", pfx=pfx, passphrase="hunter2")  # noqa: S106


@pytest.fixture
def managed_identity() -> graph.ManagedIdentity:
    return graph.ManagedIdentity()


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


class Broken:
    """A `TokenCredential` whose `get_token` raises `error`."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_token(self, *_: str) -> AccessToken:
        raise self.error


@pytest.fixture
def foreign() -> Credential:
    return Credential()


def first_token(issuer: Issuer, request: pytest.FixtureRequest, fixture: str) -> str:
    """Build the tokens of the credential `fixture` names, for its purpose in `ISSUERS`, and return the first token."""
    purpose, _ = ISSUERS[fixture]
    credential = request.getfixturevalue(fixture)
    return _tokens.tokens(credential, purpose, issuer.client).token()


def get(credential: Broken, purpose: Purpose, issuer: Issuer) -> str:
    """Return a token as the backend for `purpose` gets one: through `tokens` for a REST backend, and through `token` for SMTP."""
    if purpose == "smtp":
        return _tokens.token(credential, purpose, scope=f"{OUTLOOK}/.default")

    return _tokens.tokens(credential, purpose, issuer.client).token()


def named(fixture: str) -> str:
    """Return the issuer of the credential `fixture` names, as token messages name it."""
    return "Google" if ISSUERS[fixture][1] == GOOGLE else "Microsoft"


def replied(fixture: str, label: str, description: str) -> str:
    """Return the message for a token reply outside 2xx to the credential `fixture` names."""
    return f"{named(fixture)} replied {label} to a token request: {description}"


def granted(request: httpx2.Request) -> str:
    """Return the scope a token request carries, or the resource a managed identity requests."""
    if url(request) == IMDS:
        return parse_qs(request.url.query.decode())["resource"][0]

    form = parse_qs(request.content.decode())
    if "assertion" in form:
        return claims(form["assertion"][0])["scope"]

    return form["scope"][0]


def claims(jwt: str) -> dict[str, Any]:
    """Return the claims of `jwt`, without checking its signature."""
    return json.loads(base64.urlsafe_b64decode(jwt.split(".")[1] + "=="))


# --- Contract ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "purpose"),
    [
        *((fixture, ISSUERS[fixture][0]) for fixture in ISSUERS),
        ("foreign", "gmail"),
        ("foreign", "graph"),
    ],
)
def test_token_reuses_a_fresh_token_and_refresh_gets_exactly_one_new_one(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    purpose: Purpose,
):
    credential = request.getfixturevalue(fixture)
    tokens = _tokens.tokens(credential, purpose, issuer.client)

    def gets() -> int:
        if isinstance(credential, Credential):
            return len(credential.scopes)

        return len(issuer.tokens())

    first = tokens.token()
    if not isinstance(credential, Credential):
        # ForeignTokens.token calls get_token each time, so only an issued credential reuses its token.
        assert tokens.token() == first
        assert gets() == 1

    before = gets()
    assert tokens.refresh() != first
    assert gets() == before + 1


FAILURES = [
    *(
        pytest.param(
            lambda status=status: httpx2.Response(status, json=UNAVAILABLE),
            id=str(status),
        )
        for status in (202, 400, 403, 404, 429, 503)
    ),
    *(
        pytest.param(lambda body=body: httpx2.Response(200, content=body), id=name)
        for name, body in {
            "empty": b"",
            "a proxy login page": b"<html>proxy login</html>",
            "an array": b"[]",
            "null": b"null",
            "not UTF-8": b"\xff\xfe",
            "nested too deeply": DEEP,
            "expires_in not a number": b'{"access_token": "t", "token_type": "Bearer", "expires_in": "soon"}',
            "no access token": b'{"token_type": "Bearer", "expires_in": 3600}',
        }.items()
    ),
    pytest.param(
        lambda: httpx2.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=httpx2.ByteStream(b"not gzip"),
        ),
        id="not gzip",
    ),
    pytest.param(lambda: httpx2.ConnectError("refused"), id="ConnectError"),
    pytest.param(lambda: httpx2.ReadTimeout("timed out"), id="ReadTimeout"),
]
"""Token replies and network failures, each built afresh, because a response's stream reads once."""


@pytest.mark.parametrize("fixture", list(ISSUERS))
@pytest.mark.parametrize("method", ["token", "refresh"])
@pytest.mark.parametrize("failure", FAILURES)
def test_every_error_after_a_token_request_is_an_epistole_error(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    method: Literal["token", "refresh"],
    failure: Callable[[], Reply],
):
    purpose, where = ISSUERS[fixture]
    tokens = _tokens.tokens(request.getfixturevalue(fixture), purpose, issuer.client)
    if method == "refresh":
        tokens.token()

    issuer.replies[where] = [failure()]

    with pytest.raises(EpistoleError):
        tokens.token() if method == "token" else tokens.refresh()


@pytest.mark.parametrize("purpose", ["gmail", "graph", "smtp"])
@pytest.mark.parametrize(
    "error",
    [
        TypeError("get_token failed"),
        RuntimeError("get_token failed"),
        json.JSONDecodeError("get_token failed", "", 0),
        GoogleAuthError("get_token failed"),
        httpx2.HTTPStatusError(
            "401",
            request=httpx2.Request("POST", "https://login.example.com/token"),
            response=httpx2.Response(401),
        ),
        httpx2.ConnectError("refused"),
    ],
    ids=lambda error: type(error).__name__,
)
def test_an_error_from_get_token_stays_unmapped(
    issuer: Issuer, purpose: Purpose, error: Exception
):
    with pytest.raises(type(error)) as caught:
        get(Broken(error), purpose, issuer)

    assert caught.value is error


# --- Scopes ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "purpose", "scope"),
    [
        ("service_account", "gmail", GMAIL_SEND),
        ("service_account", "smtp", GMAIL_SMTP),
        ("authorized_user", "gmail", GMAIL_SEND),
        ("authorized_user", "smtp", GMAIL_SMTP),
        ("secret", "graph", f"{GRAPH}/.default"),
        ("secret", "smtp", f"{OUTLOOK}/.default"),
        ("certificate", "graph", f"{GRAPH}/.default"),
        ("certificate", "smtp", f"{OUTLOOK}/.default"),
        ("managed_identity", "graph", GRAPH),
        ("managed_identity", "smtp", OUTLOOK),
    ],
)
def test_a_token_request_carries_the_scope_of_its_issuer_and_purpose(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    purpose: Purpose,
    scope: str,
):
    _tokens.tokens(request.getfixturevalue(fixture), purpose, issuer.client).token()

    [token] = issuer.tokens()
    assert granted(token) == scope


@pytest.mark.parametrize(
    ("purpose", "scope"), [("gmail", GMAIL_SEND), ("graph", f"{GRAPH}/.default")]
)
def test_get_token_receives_the_scope_of_its_purpose(
    issuer: Issuer, foreign: Credential, purpose: Purpose, scope: str
):
    _tokens.tokens(foreign, purpose, issuer.client).token()

    assert foreign.scopes == [(scope,)]


def test_token_passes_the_callers_scope_to_get_token_and_opens_no_client(
    clients: list[httpx2.Client], foreign: Credential
):
    scope = "https://example.com/smtp"

    assert _tokens.token(foreign, "smtp", scope=scope) == "foreign-1"
    assert foreign.scopes == [(scope,)]
    assert clients == []


def test_a_service_account_signs_its_subject_into_the_assertion(
    issuer: Issuer, service_account: gmail.ServiceAccount
):
    _tokens.tokens(service_account, "gmail", issuer.client).token()

    [token] = issuer.tokens()
    assertion = parse_qs(token.content.decode())["assertion"][0]
    assert claims(assertion)["sub"] == "reports@example.com"


@pytest.mark.parametrize("fixture", ["authorized_user", "user_with_saved_token"])
def test_an_authorized_user_refreshes_on_its_first_token_and_never_writes_its_file(
    issuer: Issuer, request: pytest.FixtureRequest, fixture: str
):
    credential: gmail.AuthorizedUser = request.getfixturevalue(fixture)
    saved = credential.path.read_bytes()

    assert _tokens.tokens(credential, "gmail", issuer.client).token() == "token-1"

    [token] = issuer.tokens()
    assert parse_qs(token.content.decode())["grant_type"] == ["refresh_token"]
    assert credential.path.read_bytes() == saved


def test_a_client_secret_sends_its_secret_for_a_client_credentials_grant(
    issuer: Issuer, secret: graph.ClientSecret
):
    _tokens.tokens(secret, "graph", issuer.client).token()

    [token] = issuer.tokens()
    form = parse_qs(token.content.decode())
    assert form["grant_type"] == ["client_credentials"]
    assert form["client_secret"] == ["hunter2"]


@pytest.mark.parametrize("fixture", ["certificate", "pfx_certificate"])
def test_a_certificate_signs_an_assertion_rather_than_send_a_secret(
    issuer: Issuer, request: pytest.FixtureRequest, fixture: str
):
    _tokens.tokens(request.getfixturevalue(fixture), "graph", issuer.client).token()

    [token] = issuer.tokens()
    form = parse_qs(token.content.decode())
    assert form["client_assertion_type"] == [
        "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    ]
    assert "client_assertion" in form
    assert "client_secret" not in form


@pytest.mark.parametrize(("client_id", "expected"), [(None, None), ("7f3c", ["7f3c"])])
def test_a_managed_identity_requests_a_resource_for_its_client_id(
    issuer: Issuer,
    client_id: str | None,
    expected: list[str] | None,
):
    _tokens.tokens(graph.ManagedIdentity(client_id), "graph", issuer.client).token()

    [token] = issuer.tokens()
    query = parse_qs(token.url.query.decode())
    assert query.get("client_id") == expected
    assert "scope" not in query


# --- Mapping -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "where", "status"),
    [
        *(
            (fixture, GOOGLE, status)
            for fixture in (
                "service_account",
                "authorized_user",
                "user_with_saved_token",
            )
            for status in (202, 408, 429, 500, 502, 503, 504)
        ),
        *(
            (fixture, MICROSOFT, status)
            for fixture in ("secret", "certificate")
            for status in (429, 500, 502, 503, 504)
        ),
        *(("secret", DISCOVERY, status) for status in (429, 503)),
        *(("managed_identity", IMDS, status) for status in (404, 410, 429, 500, 503)),
    ],
)
def test_a_token_status_that_does_not_reject_the_credential_is_one_request_and_a_provider_error(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    where: str,
    status: int,
):
    # google-auth retries on this error whatever the status, and sleeps before the retry, unless the adapter raises (ADR-0009).
    issuer.replies[where] = [
        httpx2.Response(status, headers={"Retry-After": "30"}, json=UNAVAILABLE)
    ]

    with pytest.raises(ProviderError) as caught:
        first_token(issuer, request, fixture)

    assert str(caught.value) == replied(
        fixture, f"{status} temporarily_unavailable", "Try again later."
    )
    cause = caught.value.__cause__
    assert type(cause) is httpx2.HTTPStatusError
    assert cause.response.status_code == status
    assert cause.response.headers["Retry-After"] == "30"
    assert [url(one) for one in issuer.requests].count(where) == 1


@pytest.mark.parametrize("code", ["invalid_client", "temporarily_unavailable"])
@pytest.mark.parametrize("status", [400, 401, 403])
@pytest.mark.parametrize(
    "fixture",
    ["service_account", "authorized_user", "secret", "certificate", "managed_identity"],
)
def test_a_token_status_of_400_401_or_403_is_an_authentication_error(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    status: int,
    code: str,
):
    _, where = ISSUERS[fixture]
    body = {"error": code, "error_description": "Rejected."}
    issuer.replies[where] = [httpx2.Response(status, json=body)]

    with pytest.raises(AuthenticationError) as caught:
        first_token(issuer, request, fixture)

    assert len(issuer.tokens()) == 1
    assert str(caught.value) == replied(fixture, f"{status} {code}", "Rejected.")
    if where == GOOGLE:
        assert type(caught.value.__cause__) is httpx2.HTTPStatusError
    else:
        # msal returns its error as a dict and raises nothing, so there is no cause.
        assert caught.value.__cause__ is None


@pytest.mark.parametrize("method", ["token", "refresh"])
@pytest.mark.parametrize(
    "access_token",
    [{}, {"access_token": None}, {"access_token": ""}, {"access_token": 123}],
    ids=["missing", "null", "empty", "a number"],
)
@pytest.mark.parametrize(
    "fixture", ["service_account", "authorized_user", "secret", "managed_identity"]
)
def test_a_200_token_reply_without_an_access_token_is_a_provider_error(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    access_token: dict[str, object],
    method: Literal["token", "refresh"],
):
    purpose, where = ISSUERS[fixture]
    tokens = _tokens.tokens(request.getfixturevalue(fixture), purpose, issuer.client)
    if method == "refresh":
        tokens.token()

    body = {"token_type": "Bearer", "expires_in": 3600} | access_token
    issuer.replies[where] = [httpx2.Response(200, json=body)]

    with pytest.raises(ProviderError) as caught:
        tokens.token() if method == "token" else tokens.refresh()

    assert str(caught.value) == f"{named(fixture)}'s token reply holds no access token."
    # google-auth and msal each keep some such tokens, so the next call must request a new one.
    before = len(issuer.tokens())
    assert tokens.token().startswith("token-")
    assert len(issuer.tokens()) == before + 1


@pytest.mark.parametrize("fixture", ["secret", "managed_identity"])
def test_a_rejected_token_reply_without_an_error_names_its_status(
    issuer: Issuer, request: pytest.FixtureRequest, fixture: str
):
    _, where = ISSUERS[fixture]
    issuer.replies[where] = [httpx2.Response(400, json={"error_description": "x"})]

    with pytest.raises(AuthenticationError) as caught:
        first_token(issuer, request, fixture)

    assert str(caught.value) == "Microsoft replied 400 to a token request: x"


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (400, "Unable to load the proper Managed Identity."),
        (401, "X-IDENTITY-HEADER is invalid."),
    ],
)
def test_a_rejected_app_service_identity_keeps_its_message(
    issuer: Issuer, monkeypatch: pytest.MonkeyPatch, status: int, message: str
):
    monkeypatch.setenv("IDENTITY_ENDPOINT", APP_SERVICE)
    monkeypatch.setenv("IDENTITY_HEADER", "header")
    body = {"statusCode": status, "message": message}
    issuer.replies[APP_SERVICE] = [httpx2.Response(status, json=body)]

    with pytest.raises(AuthenticationError) as caught:
        _tokens.tokens(graph.ManagedIdentity(), "graph", issuer.client).token()

    # msal names every App Service error invalid_scope.
    assert (
        str(caught.value)
        == f"Microsoft replied {status} invalid_scope to a token request: {status}, {message}"
    )


def test_a_reply_after_a_rejected_one_clears_it(issuer: Issuer):
    # Azure Arc replies 401 to its first request, and that reply never names a later failure.
    client = _msal._HttpClient(issuer.client)
    issuer.replies[IMDS] = [httpx2.Response(401), httpx2.Response(200, json={})]

    client.get(IMDS)
    assert client.rejected is not None
    client.get(IMDS)
    assert client.rejected is None


def test_a_google_auth_error_before_any_token_reply_keeps_its_text(
    issuer: Issuer, authorized_user: gmail.AuthorizedUser
):
    consent = json.loads(Path(authorized_user.path).read_text()) | {
        "refresh_token": None
    }
    Path(authorized_user.path).write_text(json.dumps(consent))

    with pytest.raises(AuthenticationError) as caught:
        _tokens.tokens(authorized_user, "gmail", issuer.client).token()

    assert str(caught.value).startswith(
        "the credential could not get an access token: The credentials do not contain"
    )
    assert issuer.tokens() == []


@pytest.mark.parametrize("fixture", ["secret", "managed_identity"])
def test_an_error_in_a_200_token_reply_is_an_authentication_error_without_a_status(
    issuer: Issuer, request: pytest.FixtureRequest, fixture: str
):
    _, where = ISSUERS[fixture]
    body = {"error": "invalid_client", "error_description": "Rejected."}
    issuer.replies[where] = [httpx2.Response(200, json=body)]

    with pytest.raises(AuthenticationError) as caught:
        first_token(issuer, request, fixture)

    assert (
        str(caught.value)
        == "the credential could not get an access token: invalid_client: Rejected."
    )
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("fixture", "reply", "raised"),
    [
        pytest.param(
            "service_account",
            httpx2.Response(503, content=b""),
            ProviderError,
            id="Google empty",
        ),
        pytest.param(
            "service_account",
            httpx2.Response(400, content=DEEP),
            AuthenticationError,
            id="Google nested too deeply",
        ),
        pytest.param(
            "secret",
            httpx2.Response(429, content=b""),
            ProviderError,
            id="Microsoft empty",
        ),
        pytest.param(
            "managed_identity",
            httpx2.Response(503, content=DEEP),
            ProviderError,
            id="IMDS nested too deeply",
        ),
    ],
)
def test_a_token_error_that_is_not_json_maps_by_its_status_and_reason_phrase(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    reply: httpx2.Response,
    raised: type[EpistoleError],
):
    _, where = ISSUERS[fixture]
    issuer.replies[where] = [reply]

    with pytest.raises(raised) as caught:
        first_token(issuer, request, fixture)

    assert type(caught.value) is raised
    assert str(caught.value) == replied(
        fixture, str(reply.status_code), reply.reason_phrase
    )


GOOGLE_UNREADABLE = {
    "a proxy login page": (b"<html>proxy login</html>", TypeError),
    "empty": (b"", TypeError),
    "an array": (b"[]", TypeError),
    "a string": (b'"token"', TypeError),
    "null": (b"null", TypeError),
    "a number": (b"123", TypeError),
    "not UTF-8": (b"\xff\xfe", UnicodeDecodeError),
    "expires_in not a number": (
        b'{"access_token": "t", "expires_in": "soon"}',
        ValueError,
    ),
    "expires_in a decimal string": (
        b'{"access_token": "t", "expires_in": "3600.5"}',
        ValueError,
    ),
    "expires_in an array": (b'{"access_token": "t", "expires_in": [1]}', TypeError),
    "expires_in out of range": (
        b'{"access_token": "t", "expires_in": "99999999999999"}',
        OverflowError,
    ),
    "nested too deeply": (DEEP, RecursionError),
}
"""200 replies `google-auth` cannot read, and the class it raises reading each."""

MSAL_UNREADABLE = {
    "not JSON": (b"<html>Sign in</html>", (json.JSONDecodeError,)),
    "an array": (b"[]", (AttributeError, TypeError)),
    "a string": (b'"token"', (AttributeError, TypeError)),
    "null": (b"null", (AttributeError, TypeError)),
    "a number": (b"123", (AttributeError, TypeError)),
    "expires_in not a number": (
        b'{"access_token": "t", "token_type": "Bearer", "expires_in": "soon"}',
        (ValueError,),
    ),
    "expires_in a decimal string": (
        b'{"access_token": "t", "token_type": "Bearer", "expires_in": "3600.5"}',
        (ValueError,),
    ),
    "expires_in an array": (
        b'{"access_token": "t", "token_type": "Bearer", "expires_in": [1]}',
        (TypeError,),
    ),
    "expires_in infinite": (
        b'{"access_token": "t", "token_type": "Bearer", "expires_in": 1e400}',
        (OverflowError,),
    ),
    "nested too deeply": (DEEP, (RecursionError,)),
}
"""200 replies `msal` cannot read, and the classes it raises reading each, which differ between a confidential client and a managed identity."""


@pytest.mark.parametrize(
    ("fixture", "reply", "causes"),
    [
        *(
            pytest.param(
                fixture,
                httpx2.Response(200, content=body),
                (cause,),
                id=f"{fixture} {name}",
            )
            for fixture in ("service_account", "authorized_user")
            for name, (body, cause) in GOOGLE_UNREADABLE.items()
        ),
        *(
            pytest.param(
                "authorized_user",
                httpx2.Response(
                    200,
                    json={"access_token": "t", "expires_in": 3600, "scope": scope},
                ),
                (AttributeError,),
                id=f"authorized_user scope {name}",
            )
            for name, scope in {"null": None, "an array": [GMAIL_SEND]}.items()
        ),
        *(
            pytest.param(
                fixture,
                httpx2.Response(200, content=body),
                causes,
                id=f"{fixture} {name}",
            )
            for fixture in ("secret", "managed_identity")
            for name, (body, causes) in MSAL_UNREADABLE.items()
        ),
        pytest.param(
            "secret",
            httpx2.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "id_token": "a"}
            ),
            (IndexError,),
            id="secret id_token not a JWT",
        ),
        pytest.param(
            "secret",
            httpx2.Response(400, content=b"[]"),
            (AttributeError,),
            id="secret 400 an array",
        ),
        pytest.param(
            "secret",
            httpx2.Response(400, content=DEEP),
            (RecursionError,),
            id="secret 400 nested too deeply",
        ),
    ],
)
def test_a_token_reply_the_library_cannot_read_is_a_provider_error(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    reply: httpx2.Response,
    causes: tuple[type[Exception], ...],
):
    _, where = ISSUERS[fixture]
    issuer.replies[where] = [reply]

    with pytest.raises(ProviderError) as caught:
        first_token(issuer, request, fixture)

    assert type(caught.value.__cause__) in causes


@pytest.mark.parametrize(
    ("fixture", "vendor"), [("service_account", "Google"), ("secret", "Microsoft")]
)
def test_a_token_reply_that_does_not_decode_is_a_provider_error(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    vendor: str,
):
    _, where = ISSUERS[fixture]
    issuer.replies[where] = [
        httpx2.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=httpx2.ByteStream(b"not gzip"),
        )
    ]

    with pytest.raises(
        ProviderError, match=rf"^{vendor}'s token reply could not be read: "
    ) as caught:
        first_token(issuer, request, fixture)

    assert isinstance(caught.value.__cause__, httpx2.DecodingError)


@pytest.mark.parametrize(
    ("fixture", "where", "text"),
    [
        ("service_account", GOOGLE, "the token request to Google failed: refused"),
        ("authorized_user", GOOGLE, "the token request to Google failed: refused"),
        ("secret", DISCOVERY, "the token request to Microsoft failed: refused"),
        ("secret", MICROSOFT, "the token request to Microsoft failed: refused"),
        ("managed_identity", IMDS, "the token request to Microsoft failed: refused"),
    ],
)
def test_a_network_failure_on_a_token_request_is_a_transport_error(
    issuer: Issuer,
    request: pytest.FixtureRequest,
    fixture: str,
    where: str,
    text: str,
):
    failure = httpx2.ConnectError("refused")
    issuer.replies[where] = [failure]

    with pytest.raises(TransportError) as caught:
        first_token(issuer, request, fixture)

    assert str(caught.value) == text
    assert caught.value.__cause__ is failure


def rewritten(
    credential: gmail.ServiceAccount, **changes: object
) -> gmail.ServiceAccount:
    """Write `changes` into the key file of `credential`, where `None` removes a field, and return it."""
    key = json.loads(credential.path.read_text()) | changes
    credential.path.write_text(
        json.dumps({name: value for name, value in key.items() if value is not None})
    )
    return credential


@pytest.fixture
def spoiled(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    service_account: gmail.ServiceAccount,
    pfx: Path,
    rsa_key: rsa.RSAPrivateKey,
) -> _tokens.Credential:
    """Return a credential whose key or file is wrong in the way `request.param` names."""
    garbage = tmp_path / "garbage.pfx"
    garbage.write_bytes(b"not a PKCS #12 file")
    spoil: dict[str, Callable[[], _tokens.Credential]] = {
        "token_uri not a string": lambda: rewritten(service_account, token_uri=123),
        "no client_email": lambda: rewritten(service_account, client_email=None),
        "no key file": lambda: gmail.ServiceAccount(
            tmp_path / "missing.json", "a@example.com"
        ),
        "no consent file": lambda: gmail.AuthorizedUser(tmp_path / "missing.json"),
        "no pfx": lambda: graph.Certificate(
            TENANT, "epistole", pfx=tmp_path / "missing.pfx"
        ),
        "pfx with the wrong passphrase": lambda: graph.Certificate(
            TENANT,
            "epistole",
            pfx=pfx,
            passphrase="wrong",  # noqa: S106
        ),
        "pfx not PKCS #12": lambda: graph.Certificate(TENANT, "epistole", pfx=garbage),
        "private key encrypted": lambda: graph.Certificate(
            TENANT,
            "epistole",
            private_key=rsa_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(b"hunter2"),
            ).decode(),
            thumbprint="a1b2c3d4" * 5,
        ),
    }
    return spoil[request.param]()


@pytest.mark.parametrize(
    ("spoiled", "raised", "text"),
    [
        ("token_uri not a string", TypeError, "url"),
        ("no client_email", MalformedError, "client_email"),
        ("no key file", FileNotFoundError, None),
        ("no consent file", FileNotFoundError, None),
        ("no pfx", FileNotFoundError, None),
        ("pfx with the wrong passphrase", ValueError, "PKCS12"),
        ("pfx not PKCS #12", ValueError, "PKCS12"),
        ("private key encrypted", TypeError, "encrypted"),
    ],
    indirect=["spoiled"],
)
def test_an_error_raised_before_any_token_reply_stays_unmapped(
    issuer: Issuer,
    spoiled: _tokens.Credential,
    raised: type[Exception],
    text: str | None,
):
    purpose: Purpose = "graph" if isinstance(spoiled, graph.Certificate) else "gmail"

    with pytest.raises(raised, match=text) as caught:
        _tokens.tokens(spoiled, purpose, issuer.client).token()

    assert type(caught.value) is raised
    assert issuer.tokens() == []


def test_token_closes_its_client_before_it_returns_or_raises(
    issuer: Issuer, clients: list[httpx2.Client], secret: graph.ClientSecret
):
    _tokens.token(secret, "smtp")
    issuer.replies[MICROSOFT] = [httpx2.Response(503)]
    with pytest.raises(ProviderError):
        _tokens.token(secret, "smtp")

    assert len(clients) == 2
    assert all(one.is_closed for one in clients)


# --- Extras ------------------------------------------------------------------

SERVICE_ACCOUNT = gmail.ServiceAccount(Path("key.json"), subject="reports@example.com")
CLIENT_SECRET = graph.ClientSecret(TENANT, "epistole", "hunter2")
GMAIL_EXTRA = (
    "httpx2 and google-auth, so install the extra: pip install 'epistole[gmail]'"
)
GRAPH_EXTRA = "httpx2 and msal, so install the extra: pip install 'epistole[graph]'"


@pytest.mark.parametrize(
    ("credential", "purpose", "module", "message"),
    [
        pytest.param(
            SERVICE_ACCOUNT,
            "gmail",
            "httpx2",
            f"GmailBackend needs {GMAIL_EXTRA}",
            id="gmail without httpx2",
        ),
        pytest.param(
            SERVICE_ACCOUNT,
            "gmail",
            "google.auth",
            f"GmailBackend needs {GMAIL_EXTRA}",
            id="gmail without google-auth",
        ),
        pytest.param(
            Credential(),
            "gmail",
            "google.auth",
            f"GmailBackend needs {GMAIL_EXTRA}",
            id="gmail over get_token without google-auth",
        ),
        pytest.param(
            CLIENT_SECRET,
            "graph",
            "httpx2",
            f"GraphBackend needs {GRAPH_EXTRA}",
            id="graph without httpx2",
        ),
        pytest.param(
            CLIENT_SECRET,
            "graph",
            "msal",
            f"GraphBackend needs {GRAPH_EXTRA}",
            id="graph without msal",
        ),
        pytest.param(
            CLIENT_SECRET,
            "smtp",
            "msal",
            f"OAuth over a graph.ClientSecret needs {GRAPH_EXTRA}",
            id="smtp over a graph value without msal",
        ),
        pytest.param(
            graph.ManagedIdentity(),
            "smtp",
            "httpx2",
            f"OAuth over a graph.ManagedIdentity needs {GRAPH_EXTRA}",
            id="smtp over a graph value without httpx2",
        ),
        pytest.param(
            gmail.AuthorizedUser(Path("authorized-user.json")),
            "smtp",
            "google.auth",
            f"OAuth over a gmail.AuthorizedUser needs {GMAIL_EXTRA}",
            id="smtp over a gmail value without google-auth",
        ),
    ],
)
def test_require_names_the_extra_a_credential_needs_for_its_purpose(
    monkeypatch: pytest.MonkeyPatch,
    credential: _tokens.Credential,
    purpose: Purpose,
    module: str,
    message: str,
):
    monkeypatch.setitem(sys.modules, module, None)

    with pytest.raises(ImportError, match=f"^{re.escape(message)}$"):
        _tokens.require(credential, purpose)

import base64
import contextlib
import dataclasses
import inspect
import io
import re
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from functools import partial
from pathlib import Path
from typing import override

import pytest

from epistole import (
    Backend,
    Connection,
    ConsoleBackend,
    GmailBackend,
    GraphBackend,
    MemoryBackend,
    Message,
    Refusal,
    SendResult,
    SMTPBackend,
    Submission,
    Transport,
    gmail,
    graph,
    smtp,
)
from epistole.exceptions import (
    EpistoleError,
    ProviderError,
    RecipientsRefusedError,
    TransportError,
)

REFUSED = Refusal(550, "No such mailbox")
SERVICE_ACCOUNT = gmail.ServiceAccount(Path("key.json"), subject="reports@example.com")
TENANT = "contoso.onmicrosoft.com"
SECRET = graph.ClientSecret(TENANT, "epistole", "hunter2")


def message(*recipients: str) -> Message:
    """Build a message addressed to `recipients`, or to one default recipient."""
    built = Message(text="Weekly numbers").subject("Weekly numbers")
    return built.to(*recipients) if recipients else built.to("ada@example.com")


class FakeTransport:
    """A fake transport returns or raises whatever the test sets on it."""

    def __init__(
        self,
        *,
        refusals: Mapping[str, Refusal] | None = None,
        error: EpistoleError | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.refusals = refusals if refusals is not None else {}
        self.error = error
        self.close_error = close_error
        self.submitted: list[Submission] = []
        self.closes = 0

    def submit(self, submission: Submission, /) -> Mapping[str, Refusal]:
        self.submitted.append(submission)
        if self.error is not None:
            raise self.error

        return self.refusals

    def close(self) -> None:
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error


class FakeBackend(Backend):
    """A fake backend opens one transport the test holds a reference to."""

    def __init__(
        self,
        transport: FakeTransport | None = None,
        *,
        from_address: str = "reports@example.com",
        open_error: EpistoleError | None = None,
    ) -> None:
        super().__init__(from_address=from_address)
        self.transport = transport if transport is not None else FakeTransport()
        self.open_error = open_error
        self.opens = 0

    @override
    def _open(self) -> Transport:
        self.opens += 1
        if self.open_error is not None:
            raise self.open_error

        return self.transport


@pytest.fixture
def india_standard_time() -> Iterator[None]:
    """Set this process's local zone to UTC+05:30 for one test."""
    # POSIX writes the offset west of UTC, so -5:30 is UTC+05:30. The string needs no tz database.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", "IST-5:30")
        time.tzset()
        yield

    time.tzset()


# --- Backend -----------------------------------------------------------------

BACKENDS = pytest.mark.parametrize(
    "build",
    [
        MemoryBackend,
        ConsoleBackend,
        partial(SMTPBackend, "smtp.example.com"),
        partial(GmailBackend, credential=SERVICE_ACCOUNT),
        partial(GraphBackend, credential=SECRET),
    ],
    ids=[
        "MemoryBackend",
        "ConsoleBackend",
        "SMTPBackend",
        "GmailBackend",
        "GraphBackend",
    ],
)


@BACKENDS
@pytest.mark.parametrize(
    "address",
    [
        "garbage",
        '"Reports\nBcc: eve@example.com" <reports@example.com>',
        f"reports{chr(0xD800)}@example.com",
        f"reports{chr(0xDCFF)}@example.com",
    ],
)
def test_a_backend_checks_its_from_address(build: Callable[..., Backend], address: str):
    with pytest.raises(ValueError, match=re.escape(repr(address))):
        build(from_address=address)


@BACKENDS
@pytest.mark.parametrize("value", [5, b"x"], ids=["int", "bytes"])
def test_a_from_address_that_is_not_a_str_raises_type_error_naming_it(
    build: Callable[..., Backend], value: object
):
    with pytest.raises(TypeError, match="from_address="):
        build(from_address=value)


@pytest.mark.parametrize("backend", [SMTPBackend, GmailBackend, GraphBackend])
def test_from_address_is_keyword_only(backend: type[Backend]):
    parameter = inspect.signature(backend).parameters["from_address"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize(
    ("credential", "field"),
    [
        (smtp.Password("reports", "hunter2"), "password"),
        (smtp.OAuth("reports@example.com", SECRET), "credential"),
        (SERVICE_ACCOUNT, "subject"),
        (gmail.AuthorizedUser(Path("consent.json")), "path"),
        (SECRET, "client_secret"),
        (graph.Certificate(TENANT, "epistole", pfx=Path("app.pfx")), "pfx"),
        (graph.ManagedIdentity(), "client_id"),
    ],
    ids=[
        "Password",
        "OAuth",
        "ServiceAccount",
        "AuthorizedUser",
        "ClientSecret",
        "Certificate",
        "ManagedIdentity",
    ],
)
def test_a_credential_is_frozen(credential: object, field: str):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(credential, field, None)


@BACKENDS
def test_from_address_cannot_be_assigned(build: Callable[..., Backend]):
    backend = build(from_address="reports@example.com")

    with pytest.raises(AttributeError):
        backend.from_address = "garbage"  # pyrefly: ignore

    assert backend.from_address != "garbage"


@pytest.mark.parametrize("double", [MemoryBackend, ConsoleBackend])
def test_a_double_defaults_its_from_address(double: Callable[[], Backend]):
    assert double().from_address == "epistole@example.invalid"


def test_a_backend_is_not_a_context_manager():
    backend = MemoryBackend()

    with pytest.raises(TypeError, match="context manager"), backend:  # pyrefly: ignore
        pass


def test_send_opens_a_connection_sends_and_closes_it():
    backend = FakeBackend()

    backend.send(message())

    assert backend.opens == 1
    assert len(backend.transport.submitted) == 1
    assert backend.transport.closes == 1


def test_send_returns_the_message_id_and_date_the_submission_carried():
    backend = MemoryBackend()

    result = backend.send(message())

    submission = backend.submissions[0]
    assert isinstance(result, SendResult)
    assert result.message_id == submission.message_id
    assert result.date == submission.date


def test_connect_hands_back_a_connection():
    with FakeBackend().connect() as connection:
        assert isinstance(connection, Connection)


def test_connect_sets_the_backend_on_an_error_from_open():
    backend = FakeBackend(open_error=TransportError("no socket"))

    with pytest.raises(TransportError) as caught:
        backend.connect()

    assert caught.value.backend is backend


# --- Connection --------------------------------------------------------------


def test_enter_hands_back_the_same_connection():
    connection = FakeBackend().connect()

    with connection as entered:
        assert entered is connection


def test_a_connection_names_the_backend_that_opened_it():
    backend = FakeBackend()

    assert backend.connect().backend is backend


def test_a_connection_carries_many_sends():
    backend = MemoryBackend()

    with backend.connect() as connection:
        connection.send(message())
        connection.send(message())
        connection.send(message())

    assert len(backend.submissions) == 3


def test_leaving_the_with_closes_the_connection():
    backend = FakeBackend()

    with backend.connect():
        assert backend.transport.closes == 0

    assert backend.transport.closes == 1


@pytest.mark.parametrize(
    "sent",
    [message(), Message(text="Weekly numbers")],
    ids=["complete", "no recipient"],
)
def test_send_after_close_raises(sent: Message):
    connection = FakeBackend().connect()
    connection.close()

    with pytest.raises(ValueError, match="closed"):
        connection.send(sent)


def test_re_entry_after_close_raises():
    connection = FakeBackend().connect()
    connection.close()

    with pytest.raises(ValueError, match="closed"), connection:
        pass


def test_close_is_idempotent():
    backend = FakeBackend()
    connection = backend.connect()

    connection.close()
    connection.close()

    assert backend.transport.closes == 1


def test_close_never_raises():
    backend = FakeBackend(FakeTransport(close_error=OSError("socket is gone")))

    backend.connect().close()

    assert backend.transport.closes == 1


def test_the_with_body_error_is_not_masked_by_a_failing_close():
    backend = FakeBackend(FakeTransport(close_error=OSError("socket is gone")))

    from_the_body = RuntimeError("the with body failed")

    with pytest.raises(RuntimeError, match="the with body failed"), backend.connect():
        raise from_the_body


def test_send_needs_at_least_one_recipient():
    with (
        FakeBackend().connect() as connection,
        pytest.raises(ValueError, match="recipient"),
    ):
        connection.send(Message(text="Weekly numbers"))


def test_a_message_with_no_recipient_never_reaches_the_transport():
    backend = FakeBackend()

    with backend.connect() as connection, pytest.raises(ValueError, match="recipient"):
        connection.send(Message(text="Weekly numbers"))

    assert backend.transport.submitted == []


@pytest.mark.parametrize(
    "html",
    [
        '<p>Weekly numbers</p><img src="cid:chart.png">',
        '<IMG SRC=" CID:chart.png ">',
        '<img src=" \tcid:chart.png">',
        '<!--><img src="cid:chart.png"><!-- -->',
        '<img src="cid:logo.png"><img src="cid:chart.png">',
    ],
)
def test_send_needs_an_inline_image_for_every_cid_an_img_names(html: str):
    backend = FakeBackend()
    built = Message(html=html).embed(b"\x89PNG", cid="logo.png").to("ada@example.com")

    with (
        backend.connect() as connection,
        pytest.raises(ValueError, match=re.escape("matches cid:chart.png, which")),
    ):
        connection.send(built)

    assert backend.transport.submitted == []


@pytest.mark.parametrize(
    "built",
    [
        Message(html='<img src="cid:logo.png">').embed(b"\x89PNG", cid="logo.png"),
        Message(markdown="![Q3](<cid:Q3 chart.png>)").embed(
            b"\x89PNG", cid="Q3 chart.png"
        ),
        Message(html='<!-- <img src="cid:logo.png"> -->'),
        Message(html='<td style="background: url(cid:logo.png)">'),
        # A URL parser strips only U+0000 to U+0020, so this src is a relative URL.
        Message(html='<img src="\u00a0cid:logo.png">'),
    ],
    ids=[
        "embedded",
        "percent-encoded",
        "in a comment",
        "outside an img",
        "after a no-break space",
    ],
)
def test_a_cid_that_resolves_or_that_no_img_names_sends(built: Message):
    backend = MemoryBackend()

    backend.send(built.to("ada@example.com"))

    assert len(backend.submissions) == 1


# --- Submission --------------------------------------------------------------


def test_a_submission_carries_the_message_the_caller_built():
    backend = MemoryBackend()
    built = message()

    backend.send(built)

    assert backend.submissions[0].message == built


def test_a_submission_carries_the_backends_from_address():
    backend = MemoryBackend(from_address="reports@example.com")

    backend.send(message())

    assert backend.submissions[0].from_address == "reports@example.com"


def test_the_message_id_takes_its_domain_from_the_from_address():
    backend = MemoryBackend(from_address="Reports <reports@epistole.invalid>")

    result = backend.send(message())

    assert result.message_id.startswith("<")
    assert result.message_id.endswith("@epistole.invalid>")


def test_the_date_is_timezone_aware():
    assert MemoryBackend().send(message()).date.utcoffset() is not None


@pytest.mark.skipif(
    not hasattr(time, "tzset"),
    reason="the fixture changes the local zone through time.tzset, which exists only on Unix",
)
def test_the_date_carries_the_sending_machines_offset(india_standard_time: None):
    # On a machine in UTC, datetime.now(UTC) gives the same offset, so the fixture sets another zone.
    date = MemoryBackend().send(message()).date

    assert date.utcoffset() == timedelta(hours=5, minutes=30)


def test_sending_one_message_twice_makes_two_ids():
    backend = MemoryBackend()
    built = message()

    first = backend.send(built)
    second = backend.send(built)

    assert first.message_id != second.message_id


def test_the_transport_receives_the_submission():
    backend = FakeBackend()

    result = backend.send(message())

    submission = backend.transport.submitted[0]
    assert isinstance(submission, Submission)
    assert submission.message_id == result.message_id
    assert submission.from_address == "reports@example.com"


# --- MemoryBackend -----------------------------------------------------------


def test_submissions_start_empty():
    assert MemoryBackend().submissions == []


def test_submissions_survive_every_connection():
    backend = MemoryBackend()

    with backend.connect() as connection:
        connection.send(message())

    with backend.connect() as connection:
        connection.send(message())

    backend.send(message())

    assert len(backend.submissions) == 3


def test_submissions_is_the_same_list_throughout():
    backend = MemoryBackend()
    submissions = backend.submissions

    backend.send(message())

    assert backend.submissions is submissions


def test_submissions_cannot_be_assigned():
    backend = MemoryBackend()

    with pytest.raises(AttributeError):
        backend.submissions = []  # pyrefly: ignore


def test_clear_empties_the_list_an_open_connection_appends_to():
    backend = MemoryBackend()

    with backend.connect() as connection:
        connection.send(message())
        backend.submissions.clear()
        connection.send(message())

    assert len(backend.submissions) == 1


def test_a_refusal_does_not_stop_the_recipients_that_were_accepted():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    result = backend.send(message("ada@example.com", "bob@example.com"))

    assert result.refused == {"ada@example.com": REFUSED}
    assert len(backend.submissions) == 1


def test_nothing_is_refused_when_refuse_names_nobody():
    assert MemoryBackend().send(message()).refused == {}


def test_refuse_matches_a_recipients_addr_spec():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    result = backend.send(
        message("Ada Lovelace <ada@example.com>", "bob@example.com"),
    )

    assert result.refused == {"Ada Lovelace <ada@example.com>": REFUSED}


def test_refused_is_re_keyed_to_the_callers_own_recipient_string():
    backend = MemoryBackend(refuse={"Ada Lovelace <ada@example.com>": REFUSED})

    result = backend.send(message("ada@example.com", "bob@example.com"))

    assert result.refused == {"ada@example.com": REFUSED}


def test_two_recipients_sharing_an_addr_spec_resolve_to_the_first():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    result = backend.send(
        message("ada@example.com", "Ada Lovelace <ada@example.com>", "bob@example.com"),
    )

    assert result.refused == {"ada@example.com": REFUSED}


def test_refuse_reaches_a_cc_and_a_bcc():
    backend = MemoryBackend(refuse={"bob@example.com": REFUSED})

    result = backend.send(
        message("ada@example.com").cc("bob@example.com").bcc("cleo@example.com"),
    )

    assert result.refused == {"bob@example.com": REFUSED}


@pytest.mark.parametrize(
    "address",
    ["garbage", f"ada{chr(0xD800)}@example.com", f"ada{chr(0xDCFF)}@example.com"],
)
def test_refuse_checks_the_addresses_it_was_given(address: str):
    with pytest.raises(ValueError, match=re.escape(repr(address))):
        MemoryBackend(refuse={address: REFUSED})


@pytest.mark.parametrize("key", [5, b"x"], ids=["int", "bytes"])
def test_a_refuse_key_that_is_not_a_str_raises_type_error_naming_refuse(key: object):
    with pytest.raises(TypeError, match="refuse="):
        MemoryBackend(refuse={key: REFUSED})  # pyrefly: ignore


# --- ConsoleBackend ----------------------------------------------------------


def test_a_supplied_stream_receives_the_rendering(capsys: pytest.CaptureFixture[str]):
    stream = io.StringIO()

    ConsoleBackend(stream=stream).send(message())

    assert "Weekly numbers" in stream.getvalue()
    assert capsys.readouterr().out == ""


def test_stream_none_binds_stdout_at_write_time():
    connection = ConsoleBackend().connect()
    stdout = io.StringIO()

    with connection, contextlib.redirect_stdout(stdout):
        connection.send(message())

    assert "Weekly numbers" in stdout.getvalue()


def test_a_file_stream_holds_the_rendering_when_the_send_returns(tmp_path: Path):
    path = tmp_path / "sent.txt"

    with path.open("w", encoding="utf-8") as stream:
        ConsoleBackend(stream=stream).send(message())

        assert "Weekly numbers" in path.read_text(encoding="utf-8")


def test_the_rendering_leaves_out_what_the_message_does_not_hold():
    stream = io.StringIO()

    result = ConsoleBackend(stream=stream).send(
        Message(text="Weekly numbers").to("ada@example.com")
    )

    assert stream.getvalue() == (
        "From: epistole@example.invalid\n"
        "To: ada@example.com\n"
        f"Message-ID: {result.message_id}\n"
        f"Date: {format_datetime(result.date)}\n"
        "\n"
        "Weekly numbers\n"
        f"{'-' * 79}\n"
    )


def test_the_rendering_holds_every_part_of_the_submission():
    stream = io.StringIO()
    backend = ConsoleBackend(from_address="reports@example.com", stream=stream)

    result = backend.send(
        Message(html='<p>Café</p><img src="cid:logo">', text="Weekly numbers")
        .to("ada@example.com", "Bob <bob@example.com>")
        .cc("cleo@example.com")
        .bcc("dan@example.com")
        .reply_to("help@example.com")
        .subject("Weekly numbers")
        .headers({"List-Unsubscribe": "<mailto:stop@example.com>", "X-Id": "autumn"})
        .attach(bytes(2048), filename="weekly.pdf")
        .attach(b"%PDF", filename="monthly.pdf")
        .embed(b"\x89PNG", filename="logo.png", cid="logo")
    )

    assert stream.getvalue() == (
        "From: reports@example.com\n"
        "To: ada@example.com, Bob <bob@example.com>\n"
        "Cc: cleo@example.com\n"
        "Bcc: dan@example.com\n"
        "Reply-To: help@example.com\n"
        "List-Unsubscribe: <mailto:stop@example.com>\n"
        "X-Id: autumn\n"
        f"Message-ID: {result.message_id}\n"
        f"Date: {format_datetime(result.date)}\n"
        "Subject: Weekly numbers\n"
        "HTML: 32 bytes\n"
        "Attachment: weekly.pdf (application/pdf, 2,048 bytes)\n"
        "Attachment: monthly.pdf (application/pdf, 4 bytes)\n"
        "Inline image: cid:logo (logo.png, image/png, 4 bytes)\n"
        "\n"
        "Weekly numbers\n"
        f"{'-' * 79}\n"
    )


def test_the_rendering_is_never_the_bytes_a_backend_sends():
    stream = io.StringIO()
    pdf = b"%PDF-1.7 weekly numbers"

    ConsoleBackend(stream=stream).send(
        Message(html="<p>Café</p>")
        .to("Zoë <zoe@example.com>")
        .subject("Café numbers")
        .attach(pdf, filename="weekly.pdf")
    )

    rendered = stream.getvalue()
    assert "To: Zoë <zoe@example.com>\n" in rendered
    assert "Subject: Café numbers\n" in rendered
    assert "<p>" not in rendered
    assert base64.b64encode(pdf).decode() not in rendered


# --- Every recipient refused -------------------------------------------------


def test_every_recipient_refused_raises():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    with pytest.raises(RecipientsRefusedError) as caught:
        backend.send(message("ada@example.com"))

    assert caught.value.refused == {"ada@example.com": REFUSED}


def test_every_recipient_refused_records_nothing():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    with pytest.raises(RecipientsRefusedError):
        backend.send(message("ada@example.com"))

    assert backend.submissions == []


def test_every_recipient_refused_has_no_cause():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    with pytest.raises(RecipientsRefusedError) as caught:
        backend.send(message("ada@example.com"))

    assert caught.value.__cause__ is None


def test_every_recipient_refused_names_the_backend():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    with pytest.raises(RecipientsRefusedError) as caught:
        backend.send(message("ada@example.com"))

    assert caught.value.backend is backend


def test_a_transport_never_raises_the_full_refusal_itself():
    refusals = {"ada@example.com": REFUSED}
    backend = FakeBackend(FakeTransport(refusals=refusals))

    with pytest.raises(RecipientsRefusedError):
        backend.send(message("ada@example.com"))


def test_the_full_refusal_check_reads_every_recipient():
    backend = MemoryBackend(refuse={"ada@example.com": REFUSED})

    with pytest.raises(RecipientsRefusedError) as caught:
        backend.send(message("ada@example.com", "Ada Lovelace <ada@example.com>"))

    assert caught.value.refused == {"ada@example.com": REFUSED}


# --- Errors on the way out ---------------------------------------------------


def test_send_sets_the_backend_on_an_error_from_the_transport():
    backend = FakeBackend(FakeTransport(error=ProviderError("service returned 503")))

    with pytest.raises(ProviderError) as caught:
        backend.send(message())

    assert caught.value.backend is backend


def test_a_transport_error_closes_the_connection():
    backend = FakeBackend(FakeTransport(error=TransportError("socket is gone")))
    connection = backend.connect()

    with pytest.raises(TransportError):
        connection.send(message())

    assert backend.transport.closes == 1
    with pytest.raises(ValueError, match="closed"):
        connection.send(message())


def test_every_other_error_leaves_the_connection_open():
    backend = FakeBackend(FakeTransport(error=ProviderError("service returned 503")))
    connection = backend.connect()

    with pytest.raises(ProviderError):
        connection.send(message())

    assert backend.transport.closes == 0
    backend.transport.error = None
    connection.send(message())


# --- Non-ASCII domains -------------------------------------------------------


def test_a_non_ascii_domain_is_idna_encoded_into_the_message_id():
    backend = MemoryBackend(from_address="用户@例子.广告")

    result = backend.send(message())

    assert result.message_id.endswith("@xn--fsqu00a.xn--4rr70v>")
    assert result.message_id.isascii()


def test_an_ascii_domain_is_left_alone():
    backend = MemoryBackend(from_address="reports@EXAMPLE.com")

    assert backend.send(message()).message_id.endswith("@EXAMPLE.com>")


def test_a_generated_message_id_serializes_to_bytes():
    backend = MemoryBackend(from_address="用户@例子.广告")

    result = backend.send(message())

    built = EmailMessage()
    built["Message-ID"] = result.message_id
    built["To"] = "ada@example.com"
    built.set_content("Weekly numbers")

    assert result.message_id.encode() in built.as_bytes()


@pytest.mark.parametrize(
    "domain",
    [f"{'例' * 64}.com", "例子..广告"],
    ids=["label over 63 characters", "empty label"],
)
def test_a_domain_the_codec_cannot_encode_raises(domain: str):
    backend = MemoryBackend(from_address=f"ada@{domain}")

    with pytest.raises(ValueError, match="Message-ID"):
        backend.send(message())


# The IDNA codec reads U+3002 as a dot, so the last domain ends with an empty label too.
@pytest.mark.parametrize(
    "domain",
    ["example..com", ".example.com", "example.com.", "例子.广告.", "例子。广告。"],
)
def test_a_domain_with_an_empty_label_raises_at_send(domain: str):
    backend = MemoryBackend(from_address=f"ada@{domain}")

    with pytest.raises(ValueError, match="Message-ID"):
        backend.send(message())

    assert backend.submissions == []


def test_an_ascii_label_of_64_characters_sends():
    domain = f"{'a' * 64}.example.com"
    backend = MemoryBackend(from_address=f"ada@{domain}")

    assert backend.send(message()).message_id.endswith(f"@{domain}>")

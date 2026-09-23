from collections.abc import Mapping
from email.message import EmailMessage
from typing import override

import pytest

from epistole import (
    Backend,
    Connection,
    MemoryBackend,
    Message,
    Refusal,
    SendResult,
    Submission,
    Transport,
)
from epistole.exceptions import (
    EpistoleError,
    ProviderError,
    RecipientsRefusedError,
    TransportError,
)

REFUSED = Refusal(550, "No such mailbox")


def message(*recipients: str) -> Message:
    """Build a message addressed to `recipients`, or to one default recipient."""
    built = Message(text="Weekly numbers").subject("Weekly numbers")
    return built.to(*recipients) if recipients else built.to("ada@example.com")


class FakeTransport:
    """A transport that answers with whatever the test set on it."""

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
    """A backend that opens one transport the test holds a reference to."""

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


# --- Backend -----------------------------------------------------------------


def test_a_backend_checks_its_from_address():
    with pytest.raises(ValueError, match="garbage"):
        MemoryBackend(from_address="garbage")


def test_a_double_defaults_its_from_address():
    assert MemoryBackend().from_address == "epistole@example.invalid"


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


def test_send_returns_the_stamps_the_submission_carried():
    backend = MemoryBackend()

    result = backend.send(message())

    submission = backend.submissions[0]
    assert isinstance(result, SendResult)
    assert result.message_id == submission.message_id
    assert result.date == submission.date


def test_connect_hands_back_a_connection():
    with FakeBackend().connect() as connection:
        assert isinstance(connection, Connection)


def test_connect_stamps_the_backend_on_an_error_from_open():
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


def test_send_after_close_raises():
    connection = FakeBackend().connect()
    connection.close()

    with pytest.raises(ValueError, match="closed"):
        connection.send(message())


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


def test_refuse_checks_the_addresses_it_was_given():
    with pytest.raises(ValueError, match="garbage"):
        MemoryBackend(refuse={"garbage": REFUSED})


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


def test_send_stamps_the_backend_on_an_error_from_the_transport():
    backend = FakeBackend(FakeTransport(error=ProviderError("service is unwell")))

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
    backend = FakeBackend(FakeTransport(error=ProviderError("service is unwell")))
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


def test_a_stamped_message_id_writes_to_the_wire():
    backend = MemoryBackend(from_address="用户@例子.广告")

    result = backend.send(message())

    built = EmailMessage()
    built["Message-ID"] = result.message_id
    built["To"] = "ada@example.com"
    built.set_content("Weekly numbers")

    assert result.message_id.encode() in built.as_bytes()


def test_a_domain_the_codec_refuses_raises():
    backend = MemoryBackend(from_address=f"ada@{'例' * 64}.com")

    with pytest.raises(ValueError, match="Message-ID"):
        backend.send(message())

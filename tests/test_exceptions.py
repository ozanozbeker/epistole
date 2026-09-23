import copy
import inspect
import pickle
from typing import Any

import pytest

from epistole import MemoryBackend, Message, Refusal
from epistole.exceptions import (
    AuthenticationError,
    EpistoleError,
    ProviderError,
    RecipientsRefusedError,
    RejectedError,
    SenderRefusedError,
    ThrottledError,
    TransportError,
)

LEAVES = (
    AuthenticationError,
    ProviderError,
    RecipientsRefusedError,
    RejectedError,
    SenderRefusedError,
    ThrottledError,
    TransportError,
)

# `build` passes these keyword-only extras so it can construct every leaf.
EXTRAS: dict[type[EpistoleError], dict[str, Any]] = {
    RecipientsRefusedError: {"refused": {"ada@example.com": Refusal(550, "no")}},
    ThrottledError: {"retry_after": 30.0},
}


def build(leaf: type[EpistoleError], **overrides: Any) -> EpistoleError:
    return leaf("boom", **(EXTRAS.get(leaf, {}) | overrides))


def test_there_are_seven_leaves():
    assert len(LEAVES) == 7
    assert len(set(LEAVES)) == 7


@pytest.mark.parametrize("leaf", LEAVES)
def test_a_leaf_is_an_epistole_error(leaf: type[EpistoleError]):
    assert issubclass(leaf, EpistoleError)
    assert leaf.__mro__[1] is EpistoleError


def test_the_base_is_an_exception():
    assert issubclass(EpistoleError, Exception)


@pytest.mark.parametrize("leaf", LEAVES)
def test_a_leaf_takes_its_message_positionally(leaf: type[EpistoleError]):
    error = build(leaf)

    assert str(error) == "boom"
    assert error.args == ("boom",)


@pytest.mark.parametrize("leaf", [*LEAVES, EpistoleError])
def test_the_message_is_positional_only_and_the_extras_are_keyword_only(
    leaf: type[EpistoleError],
):
    parameters = inspect.signature(leaf).parameters

    assert parameters["message"].kind is inspect.Parameter.POSITIONAL_ONLY
    for name, parameter in parameters.items():
        if name != "message":
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("leaf", LEAVES)
def test_a_leaf_starts_with_no_backend(leaf: type[EpistoleError]):
    assert build(leaf).backend is None


@pytest.mark.parametrize("leaf", LEAVES)
def test_backend_is_a_plain_mutable_attribute(leaf: type[EpistoleError]):
    backend = MemoryBackend()
    error = build(leaf)

    error.backend = backend

    assert error.backend is backend


@pytest.mark.parametrize("leaf", LEAVES)
def test_a_leaf_takes_a_backend_at_construction(leaf: type[EpistoleError]):
    backend = MemoryBackend()

    assert build(leaf, backend=backend).backend is backend


def test_recipients_refused_carries_its_refusals():
    refused = {"ada@example.com": Refusal(550, "No such mailbox")}

    error = RecipientsRefusedError("boom", refused=refused)

    assert error.refused == refused


def test_recipients_refused_needs_its_refusals():
    with pytest.raises(TypeError):
        RecipientsRefusedError("boom")  # pyrefly: ignore


def test_throttled_defaults_its_retry_after():
    assert ThrottledError("boom").retry_after is None


def test_throttled_carries_the_seconds_it_was_given():
    assert ThrottledError("boom", retry_after=30.0).retry_after == 30.0


@pytest.mark.parametrize("leaf", LEAVES)
def test_an_error_survives_a_pickle_roundtrip(leaf: type[EpistoleError]):
    error = build(leaf, backend=MemoryBackend())

    back = pickle.loads(pickle.dumps(error))  # noqa: S301

    assert type(back) is leaf
    assert str(back) == "boom"
    assert back.args == ("boom",)
    assert back.__dict__.keys() == error.__dict__.keys()


def test_pickling_keeps_the_refusals():
    refused = {"ada@example.com": Refusal(550, "No such mailbox")}

    back = pickle.loads(pickle.dumps(RecipientsRefusedError("boom", refused=refused)))  # noqa: S301

    assert back.refused == refused


def test_pickling_keeps_the_retry_after():
    back = pickle.loads(pickle.dumps(ThrottledError("boom", retry_after=30.0)))  # noqa: S301

    assert back.retry_after == 30.0


@pytest.mark.parametrize("leaf", LEAVES)
def test_an_error_survives_a_deepcopy(leaf: type[EpistoleError]):
    error = build(leaf)

    assert type(copy.deepcopy(error)) is leaf


def test_an_error_raised_by_a_send_survives_the_roundtrip():
    refusal = Refusal(550, "No such mailbox")
    backend = MemoryBackend(refuse={"ada@example.com": refusal})

    with pytest.raises(RecipientsRefusedError) as caught:
        backend.send(Message(text="Weekly numbers").to("ada@example.com"))

    back = pickle.loads(pickle.dumps(caught.value))  # noqa: S301
    assert back.refused == {"ada@example.com": refusal}
    assert isinstance(back.backend, MemoryBackend)

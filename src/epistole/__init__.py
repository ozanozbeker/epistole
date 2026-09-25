from epistole import exceptions
from epistole._address import Address
from epistole._backend import (
    AccessToken,
    Backend,
    Connection,
    Submission,
    TokenCredential,
    Transport,
)
from epistole._doubles import ConsoleBackend, MemoryBackend
from epistole._message import Attachment, Message
from epistole._result import Refusal, SendResult
from epistole._text import html_to_text
from epistole.gmail import GmailBackend
from epistole.graph import GraphBackend
from epistole.smtp import SMTPBackend

__all__ = [
    "AccessToken",
    "Address",
    "Attachment",
    "Backend",
    "Connection",
    "ConsoleBackend",
    "GmailBackend",
    "GraphBackend",
    "MemoryBackend",
    "Message",
    "Refusal",
    "SMTPBackend",
    "SendResult",
    "Submission",
    "TokenCredential",
    "Transport",
    "exceptions",
    "html_to_text",
]

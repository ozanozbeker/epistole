from epistole import exceptions
from epistole._address import Address
from epistole._backend import Backend, Connection, Submission, Transport
from epistole._doubles import ConsoleBackend, MemoryBackend
from epistole._message import Attachment, Message
from epistole._result import Refusal, SendResult
from epistole._text import html_to_text
from epistole.smtp import SMTPBackend

__all__ = [
    "Address",
    "Attachment",
    "Backend",
    "Connection",
    "ConsoleBackend",
    "MemoryBackend",
    "Message",
    "Refusal",
    "SMTPBackend",
    "SendResult",
    "Submission",
    "Transport",
    "exceptions",
    "html_to_text",
]

# Epistole

Epistole takes a message you have already composed as HTML and sends it through whichever backend you have configured.
The interface is the same each time.
Supported backends are SMTP, Microsoft Graph, and Google.
The design allows more.
Switching providers means changing configuration, not rewriting your code.

This is an early project and the API is not yet stable.

> **Epistole** (ἐπιστολή, epistolē) is the Greek word for a letter or written message sent from one person to another.

## Install

```sh
uv add epistole
```

## Example

```python
from pathlib import Path
from epistole import Message, SMTPBackend, smtp

backend = SMTPBackend(
    host="mail.corp.example",
    port=587,
    from_address="reports@corp.example",
    credential=smtp.Password(username="reports", password=...),
)

backend.send(
    Message(html=Path("kpis.html").read_text(encoding="utf-8"))
    .subject("Daily KPIs")
    .to("boss@corp.example")
)
```

The backend opens a connection, authenticates, submits, and closes, all inside that one call.
With a wrong password, that line raises `AuthenticationError`.

The [user guide](https://ozanozbeker.com/epistole/user-guide/sending.html) walks through sending, writing HTML for email, choosing a backend and the tested mail services.
The [API reference](https://ozanozbeker.com/epistole/reference/) lists every public name.

## Credit

Epistole is inspired by [blastula](https://github.com/rstudio/blastula), an R package for composing and sending email.
It is not a port.
Its API does not copy blastula's.

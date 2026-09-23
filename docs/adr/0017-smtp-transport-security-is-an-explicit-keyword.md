# SMTP transport security is an explicit keyword, never inferred from the port

`SMTPBackend` takes `security: Literal["starttls", "tls", "none"]`, default `"starttls"`, next to `host` and `port=587`.
`"starttls"` requires the upgrade and raises `TransportError` when the server does not offer it.
`"tls"` is implicit TLS on connect.
`"none"` is plaintext.
There is no opportunistic mode and no inference from the port.
Decided on [#29](https://github.com/ozanozbeker/epistole/issues/29), which found the surface undecided while merging the ADRs into `docs/spec.md`.

## Why

Inferring the mode from the port is the same kind of guess ADR-0011 rejected for scope.
465 is implicit TLS by convention, but 587 with STARTTLS, 25 with STARTTLS, and 2525 with anything all exist.
A wrong guess sends a `Password` in the clear.
A boolean `starttls=` cannot express implicit TLS, which Gmail's SMTP page and most relay providers document on 465.
Opportunistic STARTTLS upgrades if the server offers it and continues if not.
That is the one failure a mail library must not make silent, because the credential goes over plaintext and nothing raises.

A `Literal` rather than an enum saves the caller an import, and a type checker still rejects a typo.

## Considered options

- **Infer the mode from the port.**
  Rejected above.
- **Take `starttls: bool`.**
  Rejected above: it cannot express implicit TLS.
- **Default to opportunistic STARTTLS.**
  Rejected above: it sends the credential in plaintext without any error.
- **Take an `ssl.SSLContext` argument.**
  It can be added later.
  ADR-0009 kept the HTTP backends free of transport settings in v1, and the same applies here.

## Consequences

- A relay that offers no STARTTLS needs `security="none"` written at the constructor, where a reviewer sees it.
- "STARTTLS not offered" joins ADR-0004's SMTP `TransportError` row.
- Timeout is fixed at 60 s, matching ADR-0009.

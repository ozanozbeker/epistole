# SMTP transport security is an explicit keyword, never inferred from the port

`SMTPBackend` takes `security: Literal["starttls", "tls", "none"]`, default `"starttls"`, next to `host` and `port=587`.
`"starttls"` requires the upgrade and raises `TransportError` when the server does not offer it; `"tls"` is implicit TLS on connect; `"none"` is plaintext.
There is no opportunistic mode and no inference from the port.
Decided on [#29](https://github.com/ozanozbeker/epistole/issues/29), which found the surface undecided while collapsing the ADRs into `docs/spec.md`.

## Why

Inferring the mode from the port is the guess ADR-0011 refused for scope: 465 is implicit TLS by convention, but 587 with STARTTLS, 25 with STARTTLS, and 2525 with anything all exist, and a wrong guess sends a `Password` in the clear.
A boolean `starttls=` cannot spell implicit TLS, which Gmail's SMTP page and most relay providers document on 465.
Opportunistic STARTTLS, upgrade if offered and continue if not, is the one failure a mail library must not make quiet, because the credential goes over plaintext and nothing raises.

A `Literal` over an enum costs the caller no import and a type checker still rejects a typo.

## Considered options

- **Infer from port.** Rejected above.
- **`starttls: bool`.** Rejected above: no implicit TLS.
- **Opportunistic default.** Rejected above: silent plaintext credential.
- **An `ssl.SSLContext` argument.** Additive later; ADR-0009 kept the HTTP backends free of transport knobs in v1 and the same applies here.

## Consequences

- A relay that offers no STARTTLS needs `security="none"` written at the constructor, where a reviewer sees it.
- "STARTTLS not offered" joins ADR-0004's SMTP `TransportError` row.
- Timeout is fixed at 60 s, matching ADR-0009.

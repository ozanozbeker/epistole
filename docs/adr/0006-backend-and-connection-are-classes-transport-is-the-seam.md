# Backend and Connection are Epistole classes; Transport is the seam

[#9](https://github.com/ozanozbeker/epistole/issues/9) made `Backend` a one-method Protocol and put the verb on the message, `Message.send(over=...)`. [#14](https://github.com/ozanozbeker/epistole/issues/14) reverses both.
`Backend` is an abstract base class with `send`, `connect`, and one abstract `_open() -> Transport`; `Connection` is a concrete class Epistole owns; `Transport` is the only Protocol, with `submit` and `close`, and it is the whole of what a third-party backend writes.
The verb is `backend.send(message)` and `connection.send(message)`, and a `Message` cannot send.
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): `submit` takes a `Submission` and returns refusals alone, so the same argument that gave stamping one home gives the send result one too (ADR-0015).

## Why

SQLAlchemy 2.0 is the shape users know, and its `Connection` is one concrete class: `execute` compiles and dispatches once, and a `Dialect` at the bottom does the per-database call.
Under #9 and #13 every backend implemented `Connection`, so the work `send` must do for every backend, checking addressing and stamping `Message-ID` and `Date`, had no home that all backends shared.
A third-party backend that forgot it would send mail with no `Message-ID`.
Owning `Connection` gives that work one home, and `Transport.submit` becomes the one call that touches a wire, which is why `submit` exists as a separate verb from `send`.

Putting the verb on the backend and connection, not the message, is 2.0's other rule: `stmt.execute()` was removed as implicit execution.
`backend.send()` stays as a one-shot because the audience sends one report far more often than a loop, and because it costs nothing once `Backend` is a class.

The base class reverses #9's structural typing.
That choice paid for the `over=` union, which is gone; a backend author importing Epistole is normal, as Django backends import Django.

## Rules

- `Backend.send(message)` is `with self.connect() as c: return c.send(message)`, written once on the base.
- `Connection.send` raises `ValueError` when closed, checks the message, builds the `Submission`, calls `transport.submit`, builds the `SendResult` from both, and on `TransportError` closes itself and re-raises (ADR-0005, ADR-0015).
- `Transport` is `submit(submission, /) -> Mapping[str, Refusal]` and `close() -> None`, positional-only so a third-party `submit(self, sub)` still matches (ADR-0015).
- The abstract surface of `Backend` is `_open()` alone; adding an abstract method later breaks every subclass, so nothing else is abstract.
- Concrete transports, `SMTPTransport` and the rest, are not exported from `epistole`; users never construct one.

## Considered options

- **Keep `Message.send(over=...)`.**
  Preparation lives next to the invariants it checks, and polars' `write_database(connection=)` has the shape.
  Rejected because it is the implicit execution 2.0 removed, and the audience reaches for `connection.send` first.
- **`Connection` as a Protocol each backend implements fully.**
  Copies the stamping into every backend and guards nothing.
- **`Backend` as a Protocol with `connect` only, one-shot on a mixin.**
  A `Backend` type that does not declare `send` leaves the 99 percent path untyped.
- **A separate `Connectable` Protocol and an `over=` union.**
  #13's shape; a connection structurally "was" a backend, which the glossary contradicts.

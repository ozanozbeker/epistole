# `Backend` and `Connection` are Epistole classes, and `Transport` is the only Protocol

[#9](https://github.com/ozanozbeker/epistole/issues/9) made `Backend` a one-method Protocol and put the verb on the message, `Message.send(over=...)`.
[#14](https://github.com/ozanozbeker/epistole/issues/14) reverses both.
`Backend` is an abstract base class with `send`, `connect`, and one abstract `_open() -> Transport`.
`Connection` is a concrete class Epistole owns.
`Transport` is the only Protocol, with `submit` and `close`.
A third-party backend implements it and nothing else.
The verb is `backend.send(message)` and `connection.send(message)`.
A `Message` cannot send.
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): `submit` takes a `Submission` and returns refusals alone.
So the send result gets one place for the same reason setting `Message-ID` and `Date` did (ADR-0015).

## Why

SQLAlchemy 2.0 is the shape users know.
Its `Connection` is one concrete class.
`execute` compiles and dispatches once, and a `Dialect` at the bottom makes the per-database call.
Under #9 and #13, every backend implemented `Connection`.
`send` must check addressing and set `Message-ID` and `Date` for every backend.
That work had no place that all backends shared.
A third-party backend that left it out would send mail with no `Message-ID`.
Owning `Connection` puts that work in one place.
`Transport.submit` becomes the one call that writes to the network, so `submit` is a separate verb from `send`.

Putting the verb on the backend and connection, not the message, is 2.0's other rule: 2.0 removed `stmt.execute()` as implicit execution.
`backend.send()` stays as a one-shot because the audience sends one report far more often than a loop.
It also takes no extra work once `Backend` is a class.

The base class reverses #9's structural typing.
That choice existed to support the `over=` union, which is gone.
A backend author importing Epistole is normal, as Django backends import Django.

## Rules

- `Backend.send(message)` is `with self.connect() as c: return c.send(message)`, written once on the base.
- `Connection.send` raises `ValueError` when closed.
  Otherwise it checks the message, builds the `Submission`, calls `transport.submit`, and builds the `SendResult` from both.
  On `TransportError`, it closes itself and re-raises (ADR-0005, ADR-0015).
- `Transport` is `submit(submission, /) -> Mapping[str, Refusal]` and `close() -> None`.
  The parameter is positional-only, so a third-party `submit(self, sub)` still matches (ADR-0015).
- The abstract surface of `Backend` is `_open()` alone.
  Adding an abstract method later breaks every subclass, so nothing else is abstract.
- `epistole` does not export the concrete transports, `SMTPTransport` and the rest.
  Users never construct one.

## Considered options

- **Keep `Message.send(over=...)`.**
  Preparation is defined next to the invariants it checks.
  polars' `write_database(connection=)` has the shape.
  Rejected because it is the implicit execution 2.0 removed.
  The audience also looks for `connection.send` first.
- **Make `Connection` a Protocol that each backend implements fully.**
  It copies the code that sets `Message-ID` and `Date` into every backend.
  It enforces nothing.
- **Make `Backend` a Protocol with `connect` only, and put the one-shot on a mixin.**
  A `Backend` type that does not declare `send` leaves the 99 percent path untyped.
- **Add a separate `Connectable` Protocol and an `over=` union.**
  This was #13's shape.
  In it, a connection structurally "was" a backend, which the glossary contradicts.

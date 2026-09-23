# A backend opens connections and is not one

Django, redmail, and the first version of [#13](https://github.com/ozanozbeker/epistole/issues/13) make the backend its own context manager: `with SMTPBackend(...) as backend:` opens a socket that the same object later closes.
Epistole splits the two.
A backend is frozen configuration.
`backend.connect()` opens a connection.
Only the connection is a context manager.
Both define `send`.
`backend.send(message)` opens a connection for one message and closes it.
`connection.send(message)` reuses one.
This is SQLAlchemy's `Engine` and `Connection` shape.
Decided on [#13](https://github.com/ozanozbeker/epistole/issues/13).
The verb moved from the message to the backend and connection on [#14](https://github.com/ozanozbeker/epistole/issues/14) (ADR-0006).
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): the backend-held list is `MemoryBackend.submissions`.
`Connection.send` builds every send result from the `Submission` it built (ADR-0015).

## Why

A backend that is sometimes live and sometimes not needs a lock, a reentrancy rule, and a defined behaviour for a second `with` on the same instance.
Django has all three.
Splitting the objects removes each question.
Configuration is immutable, so threads can share it without a lock.
A connection belongs to one thread and one `with`, the same rule as a DB-API connection at `threadsafety = 1`.
Each `connect()` opens a new connection, so there is no second `with` to define.

The audience is analysts and data engineers sending reports, blastula's users, not a web framework with its own connection management.
So the connection has no lock.
Two threads on one SMTP socket serialize anyway.
Using Graph's four concurrent requests per mailbox takes four connections, not one shared.

## Rules

- **`connect()` takes no arguments and opens eagerly.**
  On SMTP, it opens the socket and runs TLS and AUTH.
  On Gmail and Graph, it acquires a token.
  So on every backend, `AuthenticationError` and `TransportError` are raised at the line that called `connect()`.
  The backend constructor takes everything about how to connect, as `create_engine` does.
  `__enter__` returns `self` and does nothing else.
  So redmail's return-`None` problem cannot occur.
- **A connection is one link, used once.**
  `send` or `__enter__` on a closed connection raises `ValueError`, not an `EpistoleError`, because it is a mistake in the calling code (ADR-0004).
  Reopening means calling `connect()` again.
- **`close()` is idempotent and never raises.
  `__exit__` calls it and never suppresses.**
  SMTP `QUIT` is best effort.
  `close()` suppresses the error from a dead socket, so the error from the `with` body propagates unchanged.
- **Only `TransportError` closes the connection.**
  A disconnect, an `OSError`, or SMTP `421` marks the connection closed, because the socket is gone.
  `RejectedError`, `SenderRefusedError`, `RecipientsRefusedError`, `ThrottledError`, `ProviderError`, and `AuthenticationError` leave it open, because `smtplib` leaves the socket open and a loop should continue with the next recipient.
- **`backend.send()` is `connect`, `send`, `close`.**
  The one-off send stays one line and opens one connection for it.
  SQLAlchemy 2.0 removed `Engine.execute`.
  Epistole keeps the one-shot because code that sends reports has no transaction to scope, and almost every call is one message.
- **Every backend has `connect()`, including Gmail, Graph, `MemoryBackend`, and `ConsoleBackend`.**
  The loop `with backend.connect() as c:` must work unchanged after a backend swap.
  On HTTP, the connection holds a token and, where the transport allows it, one keep-alive link.
  It refreshes the token through the caller's credential object on each send.
  So an expired token in a long notebook session is not an error.
  Only a failed refresh is.
  On the test doubles, it is a no-op that delegates to the backend.
  `MemoryBackend.submissions` is an attribute of the backend, so it still exists after the `with` ends (ADR-0015).
- **Epistole defines two classes and one Protocol.**
  `Backend` and `Connection` are Epistole classes.
  `Transport` is the Protocol a backend author implements.
  ADR-0006 records the shape.
  This ADR owns the lifecycle rules above, and ADR-0006 does not change them.
- **`EpistoleError.backend` is always the configured backend.**
  A connection exposes `.backend` and fills it in.
  So a log line names the route whether the send went through a connection or not.
  ADR-0004's wording stays unchanged.
- **A backend is not a context manager.**
  `with SMTPBackend(...)` is a `TypeError`.
  There is one way to get a connection, as with `Engine`.
- **Copy `Engine`'s shape, not its internals.**
  There is no pool: `connect()` opens a real socket and `close()` closes it.
  A pool gives a report loop no benefit, and SMTP servers time idle sockets out.
  There is no `begin()`, because acceptance is final.
  There is no `dispose()`, because there is no pool.
  There are no `execution_options()` copies.
  A `backend.replace(...)` can be added later without breaking anything.

## Considered options

- **Make the backend its own context manager, as Django does.**
  Rejected above: it needs a lock and reentrancy rules.
  It is also the shape Django is retiring around `connection=`.
- **Make the backend sugar for `connect()`, with `__enter__` returning the connection.**
  It gives two spellings for one thing.
  `as backend` would bind a connection under a misleading name.
- **Open lazily in `__enter__`.**
  It makes `connect()` a factory that does not connect.
  It leaves a half-state where a connection exists but has no socket.
- **Reconnect silently on a closed connection.**
  It hides the bug where a loop kept a connection past its `with`.
- **Put `connect()` on SMTP only.**
  Calling code would branch on backend type, and the library's premise would fail.
- **Add a lock per connection.**
  It gives correctness to a use nobody should write.
  It hides the bug instead of exposing it.
- **Put `connect()` inside the `Backend` Protocol.**
  It forces a connection to have `connect()` too, which is misleading on a live link.

## Consequences

- The public API gains `Connection`, and ADR-0006 adds `Transport` as the only Protocol.
- A connection left unclosed outside `with` holds an SMTP socket until the server times it out.
  On HTTP, nothing leaks.
  The docstring on `connect()` says to use `with`.
- The glossary gains *Connection*.
  The `Backend` entry no longer lists it under *Avoid*.
- [#16](https://github.com/ozanozbeker/epistole/issues/16) decides whether the chosen HTTP transport can hold a keep-alive link at all.
  It also decides how the per-send token refresh works through `google-auth` and `msal`.
- [#18](https://github.com/ozanozbeker/epistole/issues/18) takes as given that SMTP AUTH, including XOAUTH2, happens in `connect()`.
- The README's user guide is written against this shape.

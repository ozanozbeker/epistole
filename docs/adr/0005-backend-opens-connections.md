# A backend opens connections and is not one

Django, redmail, and the first draft of [#13](https://github.com/ozanozbeker/herma/issues/13) make the backend its own context manager: `with SmtpBackend(...) as backend:` opens a socket that the same object later closes.
Herma splits the two.
A backend is frozen configuration, `backend.connect()` opens a connection, and only the connection is a context manager.
`Message.send(over=...)` takes either, because both satisfy the one-method `Backend` Protocol.
This is SQLAlchemy's `Engine` and `Connection` shape, and `polars.read_database(connection=...)` accepting either an engine or a connection is the same call shape as `over=`.
Decided on [#13](https://github.com/ozanozbeker/herma/issues/13).

## Why

A backend that is sometimes live and sometimes not needs a lock, a reentrancy rule, and an answer for a second `with` on the same instance.
Django carries all three.
Splitting the objects makes each question disappear: configuration is immutable and shareable across threads for free, and a connection belongs to one thread and one `with`, the same rule as a DB-API connection at `threadsafety = 1`.
Each `connect()` is a fresh link, so there is no second `with` to define.

The audience is analysts and data engineers sending reports, blastula's users, not a web framework with its own connection management.
That is why the connection carries no lock: two threads on one SMTP socket serialize anyway, and Graph's four concurrent requests per mailbox call for four connections, not one shared.

## Rules

- **`connect()` takes no arguments and opens eagerly.**
  Socket, TLS, and AUTH on SMTP; token acquisition on Gmail and Graph.
  `AuthenticationError` and `TransportError` therefore surface at the line that called `connect()` on every backend.
  Everything about how to connect lives on the backend constructor, as it does on `create_engine`.
  `__enter__` returns `self` and does nothing else, so redmail's return-`None` trap has nowhere to hide.
- **A connection is one link, used once.**
  `submit` or `__enter__` on a closed connection raises `ValueError`, not a `HermaError`, because it is a mistake in the calling code (ADR-0004).
  Reopening means calling `connect()` again.
- **`close()` is idempotent and never raises; `__exit__` calls it and never suppresses.**
  SMTP `QUIT` is best effort, and a dead socket is swallowed so an error from the `with` body is not masked.
- **`TransportError` closes the connection; nothing else does.**
  A disconnect, an `OSError`, or SMTP `421` marks the connection closed, because the socket is gone.
  `RejectedError`, `SenderRefusedError`, `RecipientsRefusedError`, `ThrottledError`, `ProviderError`, and `AuthenticationError` leave it open, because `smtplib` leaves the socket open and a loop should continue with the next recipient.
- **Bare `backend.submit()` is `connect`, `submit`, `close`.**
  The one-off send stays one line and opens one connection for it.
- **Every backend has `connect()`, including Gmail, Graph, `MemoryBackend`, and `ConsoleBackend`.**
  The loop `with backend.connect() as c:` must survive a backend swap unchanged.
  On HTTP the connection holds a token and, where the transport allows it, one keep-alive link.
  It refreshes the token through the caller's credential object on each submit, so an expired token in a long notebook session is not an error; only a failed refresh is.
  On the test doubles it is a no-op that delegates to the backend, and `MemoryBackend`'s outbox lives on the backend so it survives the `with`.
- **Three Protocols, `over=` takes the smallest.**

  ```python
  @runtime_checkable
  class Backend(Protocol):
      def submit(self, message: Message, /) -> Receipt: ...


  class Connection(Backend, Protocol):
      def close(self) -> None: ...
      def __enter__(self) -> Self: ...
      def __exit__(self, *exc: object) -> None: ...


  class Connectable(Backend, Protocol):
      def connect(self) -> Connection: ...
  ```

  `Message.send(*, over: Backend)` is unchanged from #9 and never branches on which it received.
  `Connectable` exists so that `def send_all(backend: Connectable, ...)` type-checks the loop this library exists for; under a `submit`-only Protocol that loop is untypeable without a private Protocol.
  Names are provisional until [#14](https://github.com/ozanozbeker/herma/issues/14).
- **`HermaError.backend` is always the configured backend.**
  A connection exposes `.backend` and fills it in, so a log line names the route whether the send went through a connection or not, and ADR-0004's wording survives unchanged.
- **A backend is not a context manager.**
  `with SmtpBackend(...)` is a `TypeError`.
  There is one way to get a connection, as with `Engine`.
- **Mirror `Engine`'s shape, not its machinery.**
  No pool: `connect()` opens a real socket and `close()` closes it, because a pool buys nothing for a report loop and SMTP servers time idle sockets out.
  No `begin()`, because acceptance is final.
  No `dispose()`, because there is no pool.
  No `execution_options()` copies; a `backend.replace(...)` can be added later without breaking anything.

## Considered options

- **Backend as its own context manager, Django shaped.**
  Rejected above: it needs a lock and reentrancy rules, and it is the shape Django is retiring around `connection=`.
- **Backend as sugar for `connect()`, `__enter__` returning the connection.**
  Two spellings for one thing, and `as backend` would bind a connection under a misleading name.
- **Lazy open in `__enter__`.**
  Makes `connect()` a factory that does not connect, and leaves a half-state where a connection exists but has no socket.
- **Silent reconnect on a closed connection.**
  Hides the bug where a loop kept a connection past its `with`.
- **`connect()` on SMTP only.**
  Calling code would branch on backend type, which is the premise of the library failing.
- **A lock per connection.**
  Buys correctness for a use nobody should write and hides the bug instead of surfacing it.
- **`connect()` inside the `Backend` Protocol.**
  Forces a connection to have `connect()` too, which is a lie on a live link.

## Consequences

- One more public type and two more Protocol names for #14.
- A connection left unclosed outside `with` holds an SMTP socket until the server times it out; on HTTP nothing leaks.
  The docstring on `connect()` says to use `with`.
- The glossary gains *Connection* and `Backend` no longer lists it under _Avoid_.
- [#16](https://github.com/ozanozbeker/herma/issues/16) decides whether the chosen HTTP transport can hold a keep-alive link at all, and how the per-submit token refresh is wired through `google-auth` and `msal`.
- [#18](https://github.com/ozanozbeker/herma/issues/18) inherits that SMTP AUTH, including XOAUTH2, happens in `connect()`.
- The README's user guide is written against this shape.

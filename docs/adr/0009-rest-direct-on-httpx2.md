# The HTTP backends call REST directly on `httpx2` and take a credential, never a vendor client

`GmailBackend` and `GraphBackend` call the Gmail API and Microsoft Graph over `httpx2`, with `google-auth` and `msal` supplying tokens and nothing else.
Neither vendor SDK is a dependency.
A backend takes a credential, and the connection owns one `httpx2.Client` that every request, token or send, goes through.
Decided on [#16](https://github.com/ozanozbeker/epistole/issues/16), grounded by `docs/research/sdk-versus-rest.md`.
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): the `401` refresh is per request rather than per send, and a backend constructor names the extra its credential value needs even when that value comes from another backend's module.

## Why

**No vendor SDK.**
`msgraph-sdk` is async only, verified on 1.62.0: `SendMailRequestBuilder.post` is a coroutine.
Epistole is sync only and its audience sends from notebooks, where `asyncio.run()` raises `asyncio.run() cannot be called from a running event loop`.
Bridging that takes a worker thread per send, which is more code than the REST path and a bug surface of its own.
Weight is the second reason, not the first: 42 packages and 189 MiB against 16 MiB for `msal` alone.
`google-api-python-client` is sync and would work, but it costs 126 MiB and a third HTTP stack (`httplib2`, not thread-safe) to save about ten lines: the resumable-upload branch and one exception class.
Google calls the library complete and in maintenance mode.
What REST-direct rebuilds is roughly 150 lines, all sync and all testable against `httpx2.MockTransport`: two send calls, two envelope parsers, a `401` retry, two auth adapters, and the Graph upload loop that [#20](https://github.com/ozanozbeker/epistole/issues/20) owns.
The hard parts, OAuth grants, JWT signing, and token caching, stay in `google-auth` and `msal`.

**`httpx2`, not `urllib.request` or `requests`.**
The research favoured the stdlib because `httpx` had stalled at 0.28.1 since 2024-12-06.
`httpx2` is Pydantic's continuation of that code, at 2.12.0 on 2026-08-18, seven packages and 3 MiB.
The job is simple enough that `requests` would do, and `msal` pulls it in regardless.
What tips it is the seam: with `httpx2` both backends go through one client that tests replace with `MockTransport`, so the Graph chunk loop unit-tests without a server.
With `requests`, Gmail would ride `google-auth`'s own session and Graph would ride `msal`'s, two seams Epistole does not own.
It costs a fast-moving pin, `httpx2>=2.12,<3`, and about 35 lines of adapter.

**Epistole writes both auth adapters.**
`google-auth` defines an abstract `Request` and ships an implementation only for `requests`, which the Gmail extra does not install, so an adapter over `httpx2` is required there.
`msal` defaults to `requests` and the adapter is optional, but without it a proxy or CA set on Epistole's client does not reach the token call, and a corporate network then fails in a way Epistole cannot explain.

**A credential, never a client.**
Unwrapping a built SDK client reaches the credential through private attributes, one on Google and three on Graph, two of them on `kiota` classes Microsoft Graph does not own.
Accepting a credential covers every vendor shape through one public interface, `google.auth.credentials.Credentials` and a structural `get_token()`, and it is the choice that keeps the door open for Epistole building credentials itself later (#2's standing constraint).
Taking a client would tie the backend signature to a vendor class.

**Eager token, per-send header, one refresh on `401`.**
ADR-0005 already put token acquisition in `connect()` so `AuthenticationError` lands on the same line as SMTP's AUTH.
The per-send step and the `401` handling copy what the vendors' own clients do: `google-auth`'s `AuthorizedSession` calls `before_request` before every call and refreshes once on `401` (`max_refresh_attempts=2`); `azure-core`'s bearer policy calls `get_token` before every request and re-acquires once on a `401` challenge.
The retry re-sends only a request the service has not accepted, so it cannot double-submit, and it is token freshness, not the backoff policy #2 rules out.

## Rules

- **Extras.** `gmail` is `google-auth` and `httpx2`; `graph` is `msal` and `httpx2`; `all` is `gmail`, `graph`, and `markdown`.
  The core stays free of runtime dependencies.
- **`from epistole import GmailBackend` always works.**
  The vendor imports happen in the backend constructor, which raises `ImportError` naming the extra to install, the ADR-0008 shape.
  A misconfigured job dies at construction, not on its first send.
- **The backend constructor names the extra its credential value needs, whichever module the value came from.**
  `SMTPBackend(credential=OAuth(credential=graph.ClientSecret(...)))` needs `msal`, so `SMTPBackend` raises `ImportError` naming `epistole[graph]`.
  The check belongs to the constructor that received the value, because ADR-0011 keeps the values themselves inert.
  It over-installs `httpx2` for a caller who only wanted SMTP, which is 3 MB and the only extra that names the library they need.
- **`connect()` builds one `httpx2.Client` and acquires a token.**
  It makes no request to the mail endpoint.
  The connection holds the client; `close()` closes it.
- **Every request asks the credential for the header, then goes out on the connection's client.**
  On `401` that one request refreshes once and retries itself once; a second `401` on it is `AuthenticationError`.
  The budget is per request, not per send, because Graph's draft path makes `2 + N` requests and a token can expire partway through one send.
  This is what `azure-core`'s bearer policy does: re-acquire once per `401` challenge, on the request that got it.
  A retry re-sends only a request the service did not accept, so a long draft sequence cannot double-submit or leave a second draft.
  The upload `PUT`s carry no bearer, so they are outside this rule and their statuses map under ADR-0004 like any other.
- **Timeout is 60 s** on connect, read, write, and pool, for send and token requests alike.
  No constructor knob in v1.
- **No caller-supplied `httpx2.Client` in v1.**
  Proxy and CA come from the environment (`trust_env`) and the OS trust store (`truststore`), which `httpx2` reads by default.
  `httpx2` is not part of the public signature, so it can be swapped without breaking a caller.
- **`__cause__` on the HTTP backends.**

  | Failure | `__cause__` | Epistole class |
  | --- | --- | --- |
  | mail endpoint answered non-2xx | `httpx2.HTTPStatusError`; `.response` keeps status, headers, and body | ADR-0004 status tables |
  | connect, TLS, read, write, timeout | the `httpx2.TransportError` subclass raised | `TransportError` |
  | Google refresh failed | `google.auth.exceptions.RefreshError` | `AuthenticationError` |
  | Google refresh failed on the network | the `RefreshError`; Epistole reads one level down and maps on the `httpx2.TransportError` inside | `TransportError` |
  | msal token call failed | `None`; msal returns an error dict and raises nothing, so the message carries `error` and `error_description` | `AuthenticationError` |
  | second `401` after the refresh | `httpx2.HTTPStatusError` | `AuthenticationError` |
  | Epistole pre-check | `None`, per ADR-0004 | `RejectedError` |

- **The Graph upload `PUT` goes through the connection's client and never carries the bearer.**
  The upload URL is pre-authenticated on a different host, and the bearer would leak.
  A shared private HTTP helper attaches the bearer and does the `401` retry; the upload loop bypasses both and keeps the timeout.

## Considered options

- **Both vendor SDKs.**
  Rejected above: Graph's is async only against notebook users.
- **Gmail SDK with Graph on REST.**
  Two HTTP stacks and two error paths either way, for a ten-line win.
- **`urllib.request`.**
  The research's pick, on the grounds that `httpx` had stalled.
  `httpx2` removes that ground, and `urllib` has no keep-alive, no test transport, and no default timeout.
- **`requests`.**
  Free on the Graph extra and adapter-free on both.
  Rejected for the seam: neither backend's HTTP would be Epistole's to mock.
- **Accept an SDK client, or a credential or a client.**
  Private-attribute unwrapping and a vendor class in the signature.
- **A caller-supplied `httpx2.Client`, or `proxy=` and `verify=` pass-throughs.**
  Ownership and lifetime questions on the first, another library's knobs re-documented on the second.
  Both are additive later.
- **Probe the mail endpoint at `connect()`.**
  Catches a missing scope early but needs a permission Epistole otherwise never asks for.

## Consequences

- Two pins to watch: `httpx2` moved from 2.6 to 2.12 in five weeks, and each release exact-pins `httpcore2`.
- `httpx2.TransportError` and `epistole.TransportError` share a name.
  Epistole imports `httpx2` as a module and never re-exports it.
- An insufficient scope surfaces on the first `send`, not on `connect()`, as on SMTP.
- [#18](https://github.com/ozanozbeker/epistole/issues/18) owns the concrete credential shapes, including whether a bare token or a callable is accepted; this ADR fixes only that the boundary is a credential.
- [#20](https://github.com/ozanozbeker/epistole/issues/20) owns the three Graph strategies and writes the upload loop against the rules here.
- The glossary gains *Credential*.

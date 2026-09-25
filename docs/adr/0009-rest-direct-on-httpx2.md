# The HTTP backends call REST directly on `httpx2` and take a credential, never a vendor client

`GmailBackend` and `GraphBackend` call the Gmail API and Microsoft Graph over `httpx2`.
`google-auth` and `msal` supply tokens and nothing else.
Neither vendor SDK is a dependency.
A backend takes a credential.
The connection owns one `httpx2.Client`.
Every request goes through it, whether for a token or a send.
Decided on [#16](https://github.com/ozanozbeker/epistole/issues/16), based on `docs/research/sdk-versus-rest.md`.
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): the `401` refresh is per request rather than per send.
A backend constructor names the extra its credential value needs, even when that value comes from another backend's module.
Amended on [#44](https://github.com/ozanozbeker/epistole/issues/44): `google-auth` 2.57 raises the request adapter's own `google.auth.exceptions.TransportError` for a network failure during a refresh, not a `RefreshError`.
So Epistole reads any `google-auth` error one level down.
Amended on [#45](https://github.com/ozanozbeker/epistole/issues/45): `msal` 1.38 does not always return an error dict.
It raises `MsalServiceError` for a `5xx` from Entra's discovery or token endpoint, and `json.JSONDecodeError` for a token reply that is not JSON.
Epistole maps both to `ProviderError`.
It raises a plain `ValueError` for a tenant that does not exist, and Epistole leaves that unmapped, because `msal` raises the same class for a pfx it cannot read.

## Why

**Epistole uses no vendor SDK.**
`msgraph-sdk` is async only, verified on 1.62.0: `SendMailRequestBuilder.post` is a coroutine.
Epistole is sync only.
Its audience sends from notebooks, where `asyncio.run()` raises `asyncio.run() cannot be called from a running event loop`.
Bridging that takes a worker thread per send, which is more code than the REST path and a bug surface of its own.
Weight is the second reason, not the first: 42 packages and 189 MiB against 16 MiB for `msal` alone.
`google-api-python-client` is sync and would work.
But it costs 126 MiB and a third HTTP stack (`httplib2`, not thread-safe) to save about ten lines: the resumable-upload branch and one exception class.
Google calls the library complete and in maintenance mode.
REST-direct rebuilds roughly 150 lines, all sync and all testable against `httpx2.MockTransport`.
They are two send calls, two envelope parsers, a `401` retry, two auth adapters, and the Graph upload loop that [#20](https://github.com/ozanozbeker/epistole/issues/20) owns.
The hard parts stay in `google-auth` and `msal`: OAuth grants, JWT signing, and token caching.

**Epistole uses `httpx2`, not `urllib.request` or `requests`.**
The research favoured the stdlib because `httpx` had stalled at 0.28.1 since 2024-12-06.
`httpx2` is Pydantic's continuation of that code.
It was at 2.12.0 on 2026-08-18, with seven packages and 3 MiB.
The job is simple enough that `requests` would do.
`msal` pulls it in regardless.
The deciding reason is how tests replace the HTTP layer.
With `httpx2`, both backends go through one client that tests replace with `MockTransport`.
So the Graph chunk loop unit-tests without a server.
With `requests`, Gmail would use `google-auth`'s own session, and Graph would use `msal`'s.
Those are two sessions Epistole does not own.
`httpx2` needs a fast-moving pin, `httpx2>=2.12,<3`, and about 35 lines of adapter.

**Epistole writes both auth adapters.**
`google-auth` defines an abstract `Request` and ships an implementation only for `requests`.
The Gmail extra does not install `requests`, so Gmail needs an adapter over `httpx2`.
`msal` defaults to `requests`, and the adapter is optional.
Without it, a proxy or CA set on Epistole's client does not apply to the token call.
A corporate network then fails, and Epistole's error does not show why.

**A backend takes a credential, never a client.**
Unwrapping a built SDK client reads the credential through private attributes: one on Google and three on Graph.
Two of the Graph ones are on `kiota` classes Microsoft Graph does not own.
Accepting a credential covers every vendor shape through one public interface: `google.auth.credentials.Credentials` and a structural `get_token()`.
It also still allows Epistole to build credentials itself later (#2's standing constraint).
Taking a client would make the backend signature depend on a vendor class.

**Epistole gets the token eagerly, sets the header per send, and refreshes once on `401`.**
ADR-0005 already put token acquisition in `connect()`, so `AuthenticationError` is raised at the same line as SMTP's AUTH.
The per-send step and the `401` handling copy what the vendors' own clients do.
`google-auth`'s `AuthorizedSession` calls `before_request` before every call and refreshes once on `401` (`max_refresh_attempts=2`).
`azure-core`'s bearer policy calls `get_token` before every request and re-acquires once on a `401` challenge.
The retry re-sends only a request the service has not accepted, so it cannot double-submit.
It is token freshness, not the backoff policy #2 rules out.

## Rules

- **The extras are defined as follows.**
  `gmail` is `google-auth` and `httpx2`.
  `graph` is `msal` and `httpx2`.
  `all` is `gmail`, `graph`, and `markdown`.
  The core stays free of runtime dependencies.
- **`from epistole import GmailBackend` always works.**
  The vendor imports happen in the backend constructor.
  It raises `ImportError` naming the extra to install, the ADR-0008 shape.
  A misconfigured job fails at construction, not on its first send.
- **The backend constructor names the extra its credential value needs, whichever module the value came from.**
  `SMTPBackend(credential=OAuth(credential=graph.ClientSecret(...)))` needs `msal`, so `SMTPBackend` raises `ImportError` naming `epistole[graph]`.
  The check belongs to the constructor that received the value, because ADR-0011 keeps the values themselves inert.
  It over-installs `httpx2` for a caller who only wanted SMTP.
  The over-install is 3 MB, and `epistole[graph]` is the only extra that names the library they need.
- **`connect()` builds one `httpx2.Client` and acquires a token.**
  It makes no request to the mail endpoint.
  The connection holds the client.
  `close()` closes it.
- **For every request, Epistole gets the header from the credential and sends the request on the connection's client.**
  On `401`, Epistole refreshes once and retries that one request once.
  A second `401` on it is `AuthenticationError`.
  The budget is per request, not per send, because Graph's draft path makes `2 + N` requests and a token can expire partway through one send.
  `azure-core`'s bearer policy does the same: it re-acquires once per `401` challenge, on the request that got it.
  A retry re-sends only a request the service did not accept, so a long draft sequence cannot double-submit or leave a second draft.
  The upload `PUT`s carry no bearer, so they are outside this rule.
  Their statuses map under ADR-0004 like any other.
- **Timeout is 60 s** on connect, read, write, and pool, for send and token requests alike.
  There is no constructor setting for it in v1.
- **The backend takes no caller-supplied `httpx2.Client` in v1.**
  Proxy and CA come from the environment (`trust_env`) and the OS trust store (`truststore`), which `httpx2` reads by default.
  `httpx2` is not part of the public signature, so it can be swapped without breaking a caller.
- **`__cause__` on the HTTP backends is as follows.**

  | Failure | `__cause__` | Epistole class |
  | --- | --- | --- |
  | mail endpoint returned non-2xx | `httpx2.HTTPStatusError`; `.response` keeps status, headers, and body | ADR-0004 status tables |
  | connect, TLS, read, write, timeout | the `httpx2.TransportError` subclass raised | `TransportError` |
  | Google refresh failed | `google.auth.exceptions.RefreshError` | `AuthenticationError` |
  | Google refresh failed on the network | the `httpx2.TransportError` subclass, which Epistole reads one level down from `google.auth.exceptions.TransportError` | `TransportError` |
  | msal token call failed | `None`; msal returns an error dict, so the message carries `error` and `error_description` | `AuthenticationError` |
  | Entra's discovery or token endpoint replied `5xx` | `msal.exceptions.MsalServiceError`, which msal raises instead of returning a dict | `ProviderError` |
  | token reply is not JSON | `json.JSONDecodeError`, which msal raises | `ProviderError` |
  | second `401` after the refresh | `httpx2.HTTPStatusError` | `AuthenticationError` |
  | Epistole pre-check | `None`, per ADR-0004 | `RejectedError` |

- **The Graph upload `PUT` goes through the connection's client and never carries the bearer.**
  The upload URL is pre-authenticated on a different host, and the bearer would leak.
  A shared private HTTP helper attaches the bearer and does the `401` retry.
  The upload loop bypasses both and keeps the timeout.

## Considered options

- **Use both vendor SDKs.**
  Rejected above: Graph's is async only, against notebook users.
- **Use the Gmail SDK, with Graph on REST.**
  It keeps two HTTP stacks and two error paths either way, to save ten lines.
- **Use `urllib.request`.**
  The research picked it, because `httpx` had stalled.
  `httpx2` removes that reason.
  `urllib` has no keep-alive, no test transport, and no default timeout.
- **Use `requests`.**
  It is free on the Graph extra and needs no adapter on either backend.
  Rejected for testing: neither backend's HTTP would be Epistole's to mock.
- **Accept an SDK client, or a credential or a client.**
  It needs private-attribute unwrapping and puts a vendor class in the signature.
- **Accept a caller-supplied `httpx2.Client`, or `proxy=` and `verify=` pass-throughs.**
  The first raises ownership and lifetime questions.
  The second re-documents another library's settings.
  Both are additive later.
- **Probe the mail endpoint at `connect()`.**
  It catches a missing scope early.
  But it needs a permission Epistole otherwise never requests.

## Consequences

- Two pins need watching.
  `httpx2` moved from 2.6 to 2.12 in five weeks.
  Each release exact-pins `httpcore2`.
- `httpx2.TransportError` and `epistole.TransportError` share a name.
  Epistole imports `httpx2` as a module and never re-exports it.
- Epistole raises an insufficient-scope error on the first `send`, not on `connect()`, as on SMTP.
- [#18](https://github.com/ozanozbeker/epistole/issues/18) owns the concrete credential shapes, including whether a bare token or a callable is accepted.
  This ADR fixes only that the boundary is a credential.
- [#20](https://github.com/ozanozbeker/epistole/issues/20) owns the three Graph strategies and writes the upload loop against the rules here.
- The glossary gains *Credential*.

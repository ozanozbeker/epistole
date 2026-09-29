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
Amended on [#52](https://github.com/ozanozbeker/epistole/issues/52): the Google auth adapter raises for any token reply but `200`, so `google-auth` never retries a token request.
Epistole maps that reply by its status, so a `5xx` is `ProviderError`, as on Graph ([#54](https://github.com/ozanozbeker/epistole/issues/54)).
Amended on [#55](https://github.com/ozanozbeker/epistole/issues/55): a token reply that `google-auth` or `msal` cannot read is `ProviderError`, with the library's exception as `__cause__`.
The same classes raised before the library's auth adapter returns a reply stay unmapped.
Amended on [#62](https://github.com/ozanozbeker/epistole/issues/62): a reply nested too deeply for `json` is unreadable too, so `RecursionError` joins the five classes, in the error envelope readers as well.
An exception from a caller's `TokenCredential` propagates unchanged.
Amended on [#63](https://github.com/ozanozbeker/epistole/issues/63): the Graph auth adapter raises for any token reply outside 2xx but `400`, `401` or `403`.
Epistole maps that reply by its status, as it maps a Google token reply.
So `msal` never reads a `5xx` and never raises `MsalServiceError`.
Epistole also turns off `msal`'s HTTP cache, so `msal` sends every token request on the connection's client.

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

**The Google auth adapter raises for any token reply but `200`, because `google-auth` retries and sleeps.**
`google-auth` accepts only a `200` from the token endpoint.
It retries any other reply whose status is `408`, `429`, `500`, `503` or `504`, or whose `error` or `error_description` is `internal_failure`, `server_error` or `temporarily_unavailable`.
It makes 3 attempts, and sleeps about 1 s and then about 2 s between them.
Measured on `google-auth` 2.57.1: a token endpoint that always replies `503` received 3 requests, and `connect()` raised after 3 s.
ADR-0004 says Epistole never sleeps and never retries.
A caller's retry loop would also triple every attempt.
No public setting turns the retry off.
The adapter already raises `google.auth.exceptions.TransportError` for a network failure, and `google-auth` passes that out of its loop without a retry.
So the adapter raises the same class for any reply but `200`, and the loop ends before its first sleep.
Epistole then picks the class from the status one level down, because `RefreshError` carries no status.

**The Graph auth adapter raises for a token reply outside 2xx but `400`, `401` or `403`, because `msal`'s error dict carries no status.**
`msal` raises `MsalServiceError` for a status of `500` or above from Entra's discovery or token endpoint, and never for a managed identity endpoint.
Below `500`, it returns the parsed body.
Measured on `msal` 1.38.0: `connect()` raised `AuthenticationError` for a `429` from Entra or IMDS with a JSON body.
For a `429` with an empty body, it raised `ProviderError` with a `json.JSONDecodeError` as `__cause__`.
No error carried the `Retry-After` value.
`msal` also parses an IMDS reply as JSON at every status, so Epistole mapped an IMDS `404`, `410`, `500` or `503` with a JSON body to `AuthenticationError`.
IMDS's documentation says to retry all four.
The adapter raises before `msal` reads such a reply, so Epistole maps it by its status.
A `429` is `ProviderError`, not `ThrottledError`, as #52 decided for Google.
`smtp.OAuth` gets a Graph token on the same path, and the SMTP backend never raises `ThrottledError` (ADR-0004).
The adapter still returns a `400`, `401` or `403` to `msal`, for two reasons.
`msal`'s error dict carries `error` and `error_description`, and the `AADSTS` code in the description names the cause.
`msal`'s Azure Arc flow also reads the `WWW-Authenticate` header of a `401`.

**Epistole turns off `msal`'s HTTP cache, because `msal` returns a kept reply instead of sending a later token request.**
`msal` wraps the auth adapter in its own HTTP cache.
The cache keeps a `429`, a `5xx`, or any reply with `Retry-After` for `Retry-After` seconds: 5 s by default and 3600 s at most.
A confidential client also keeps a `400` for 60 s.
For a later token request on the same connection, `msal` returns the kept reply and sends no request.
ADR-0004 makes `ProviderError` transient, so a caller retries it.
`msal` then returns the kept reply again, and the endpoint receives no request.
The adapter's reply count does not change either, so an error from reading a kept reply propagates unmapped.
Measured on `msal` 1.38.0: after a refresh received a `400` with body `[]`, the next send raised a raw `AttributeError`.
Both `msal` clients take `http_cache=`, a public parameter that accepts any dict-like object.
Epistole passes a `dict` that keeps nothing, so it uses no private `msal` name.

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
- **The Google auth adapter raises `google.auth.exceptions.TransportError` for any token reply but `200`.**
  Its cause is an `httpx2.HTTPStatusError`, as a network failure's cause is the `httpx2.TransportError` subclass.
  So `google-auth` makes one attempt per token request and never sleeps.
  Epistole maps the reply by its status: `400`, `401` and `403` are `AuthenticationError`, and any other status is `ProviderError`.
  A `429` is `ProviderError`, not `ThrottledError`.
  `smtp.OAuth` gets a Gmail token on the same path, and the SMTP backend never raises `ThrottledError` (ADR-0004).
- **The Graph auth adapter raises `httpx2.HTTPStatusError` for any token reply outside 2xx but `400`, `401` or `403`.**
  It raises before `msal` reads the reply, on its `GET` and its `POST` alike.
  That covers Entra's discovery and token endpoints and every managed identity endpoint Epistole supports.
  Epistole maps that error to `ProviderError` at every status, `429` included.
  The `ProviderError` message names the status, and the `error` and `error_description` of a body that is a JSON object.
  The adapter raises a private subclass, so the mapping tells a token reply from a mail endpoint reply.
  A token `429` never maps to `ThrottledError`.
- **The Graph auth adapter returns a `400`, `401` or `403` to `msal`.**
  An error dict is `AuthenticationError`, and a body `msal` cannot read is `ProviderError`.
  The dict's `error` never sets the class, so a `400` whose `error` is `temporarily_unavailable` is `AuthenticationError`.
  A `400`, `401` or `403` from the discovery endpoint stays `msal`'s `ValueError`, unmapped.
  So Graph's token table is Google's, except that a `400`, `401` or `403` body that `msal` cannot read is `ProviderError`.
- **Epistole turns off `msal`'s HTTP cache.**
  It passes both `msal` clients `http_cache=`, a `dict` that keeps nothing.
  So `msal` sends every token request on the connection's client, and the adapter's `replies` counts every reply `msal` reads.
- **A token reply that `google-auth` or `msal` cannot read is `ProviderError`.**
  A proxy login page served with status `200` is one such reply.
  A body that is not a JSON object is another.
  So is a field of the wrong type, such as `expires_in`, `scope` or `id_token`.
  Reading one, the libraries raise `AttributeError`, `LookupError`, `OverflowError`, `TypeError` or `ValueError`.
  Measured on `google-auth` 2.57.1 and `msal` 1.38.0.
  A reply nested 10,000 levels deep makes `json` raise `RecursionError` on 3.13.12, and 1,000 levels parse.
  3.14.7 parses 10,000 levels and raises at 100,000, so the tests nest 100,000.
  Each auth adapter counts the replies it returns, and Epistole maps those six classes only when the count increased during the library call.
  Before any reply, the same classes come from the caller's credential.
  `msal` raises `TypeError` for an encrypted PEM, and `AttributeError` for a public key passed as `private_key`.
  Those stay unmapped.
  The rule also covers a `GoogleAuthError` that subclasses one of the five, such as `MalformedError`.
  `google-auth` 2.57.1 raises none after a reply.
- **An error body or a Graph draft reply that is too deeply nested to parse is unreadable too.**
  An error body then maps by its status alone, and a draft or upload session reply is `ProviderError`.
  So the mapper never raises on its own (ADR-0004).
- **An exception from a caller's `TokenCredential` propagates unchanged.**
  It is not a reply from the mail service, so no mapping table has a row for it.
  `get_token` raises whatever its own library raises, so Epistole cannot tell a failure the credential reports from a bug in it.
- **`__cause__` on the HTTP backends is as follows.**

  | Failure | `__cause__` | Epistole class |
  | --- | --- | --- |
  | mail endpoint returned non-2xx | `httpx2.HTTPStatusError`; `.response` keeps status, headers, and body | ADR-0004 status tables |
  | connect, TLS, read, write, timeout | the `httpx2.TransportError` subclass raised | `TransportError` |
  | Google's token endpoint replied with any status but `200` | `httpx2.HTTPStatusError`, which Epistole reads one level down from `google.auth.exceptions.TransportError` | `AuthenticationError` on `400`, `401` or `403`; `ProviderError` otherwise |
  | Google refresh failed otherwise | `google.auth.exceptions.RefreshError` | `AuthenticationError` |
  | Google refresh failed on the network | the `httpx2.TransportError` subclass, which Epistole reads one level down from `google.auth.exceptions.TransportError` | `TransportError` |
  | Entra or a managed identity endpoint rejected the credential with `400`, `401` or `403` | `None`; msal returns an error dict, so the message carries `error` and `error_description` | `AuthenticationError` |
  | a Graph token reply's status was outside 2xx and not `400`, `401` or `403` | `httpx2.HTTPStatusError`, which the Graph auth adapter raises before msal reads the reply | `ProviderError` |
  | `google-auth` or `msal` could not read a token reply | the `AttributeError`, `LookupError`, `OverflowError`, `TypeError` or `ValueError` the library raised, such as `json.JSONDecodeError` | `ProviderError` |
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
- **Pass `can_retry=False` to `google-auth`'s grant functions.**
  Only the private module `google.oauth2._client` takes it.
  `AuthorizedUser` refreshes through `google.oauth2.reauth.refresh_grant`, which takes no such argument.
  So Epistole would rebuild each credential's refresh from private attributes.
- **Document `google-auth`'s retry as an exception to ADR-0004.**
  Rejected because #2 puts retry and backoff policy out of scope.
- **Map a failed refresh by `RefreshError.retryable`.**
  `google.oauth2.reauth` sets it to `False` for any reply that is not JSON, so an `AuthorizedUser` `503` with an empty body reads as permanent.
  Measured on `google-auth` 2.57.1.
- **Map the five classes from the whole token call, without counting replies.**
  `msal` raises `TypeError` for an encrypted PEM inside the same call, before its token request.
  So a caller's key would read as a transient `ProviderError`.
- **Check the reply's shape in the auth adapter.**
  The adapter can raise for a body that is not a JSON object.
  It cannot check the fields each library reads, such as `expires_in` and `scope`, without copying the libraries' parsing.

## Consequences

- Two pins need watching.
  `httpx2` moved from 2.6 to 2.12 in five weeks.
  Each release exact-pins `httpcore2`.
- The Google auth adapter rule depends on `google-auth` passing the adapter's `TransportError` out of its loop without a retry, as 2.57.1 does.
  A test that counts the token requests on a `503` fails on a release that changes this.
- The no-cache rule depends on `msal` 1.38.0 writing to `http_cache` only by item assignment, which the `dict` subclass ignores.
  A test that counts the token requests after a `400` with body `[]` fails on a release that changes this.
- The unreadable-reply rule names the six classes measured on the replies above.
  A library release or an unmeasured reply can raise another class.
  That exception propagates unmapped.
  Each measured reply has a test that expects `ProviderError`, so a release that changes its class fails that test.
- `httpx2.TransportError` and `epistole.TransportError` share a name.
  Epistole imports `httpx2` as a module and never re-exports it.
- Epistole raises an insufficient-scope error on the first `send`, not on `connect()`, as on SMTP.
- [#18](https://github.com/ozanozbeker/epistole/issues/18) owns the concrete credential shapes, including whether a bare token or a callable is accepted.
  This ADR fixes only that the boundary is a credential.
- [#20](https://github.com/ozanozbeker/epistole/issues/20) owns the three Graph strategies and writes the upload loop against the rules here.
- The glossary gains *Credential*.

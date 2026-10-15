# What httpx2 provides for oxy's transport

This note records what httpx2 2.13.1 provides for oxy's transport, and how it differs from httpx 0.28.1.
It answers [#4](https://github.com/ozanozbeker/oxyscraper/issues/4) for [#11](https://github.com/ozanozbeker/oxyscraper/issues/11) and [#23](https://github.com/ozanozbeker/oxyscraper/issues/23).
It covers httpx2 at tag `v2.13.1` (commit `d91c9f4`) and httpx at tag `0.28.1` (commit `26d48e0`), as published on 2026-09-24.
The measurements ran that day on Python 3.11.15 and macOS, in throwaway environments outside the repo.
The two requests to Oxylabs sent no credentials, so they spent no credits.

## Answer

httpx2 provides a typed client in sync and async forms, a `transport` argument for tests, and connection pooling with optional HTTP/2.
It has no retries beyond connection setup, no pacing and no whole-request timeout, so oxy writes those itself.

- **Sync and async.**
  `Client` and `AsyncClient` are separate classes, but they share `Request`, `Response`, `Headers`, `Timeout`, `Limits` and every exception.
  Each client carries its own hand-written I/O path, and only `httpcore2` generates sync code from async code.
  One oxy code path needs oxy's own mechanism: a sans-IO core with two drivers, generated sync code, or an async core behind a sync facade.
- **Test seam.**
  Either client takes `transport=httpx2.MockTransport(handler)`.
  One sync handler serves both clients, and it can return any status or raise any httpx2 exception.
  `MockTransport` skips the connection pool, so `retries`, `Limits`, the `pool` timeout and HTTP/2 never run under test.
- **Retries.**
  The only built-in retry is `retries=N` on `HTTPTransport` and `AsyncHTTPTransport`.
  It retries `ConnectError` and `ConnectTimeout` while a connection opens.
  The delays are 0, 0.5, 1 and 2 s, and they keep doubling.
  Nothing retries a 429, a 5xx, a read error or a timeout, so oxy owns that policy.
  The same holds for httpx.
- **Side effects of passing a transport.**
  The client applies its own `limits`, `http2` and `verify` only to the default transport it builds, and it stops reading proxy environment variables.
  `HTTPTransport(proxy=...)` also drops `retries`.
  A production client that sets `http2` and `limits` itself, takes no transport, and leaves connect errors to oxy's retry policy avoids all three.
- **Timeouts.**
  Connect, read, write and pool each default to 5 s.
  The read timeout limits the gap between chunks, and no setting limits a whole request.
  Oxylabs asks for a 180 s client timeout on rendered Realtime jobs, so a Realtime request needs its own read timeout.
- **Concurrency.**
  `Limits` caps connections, not requests per second, and httpx2 has no rate limiter.
  Over HTTP/1.1 a request past `max_connections` waits for a free connection, and it raises `PoolTimeout` if none frees up within the `pool` timeout.
  Over HTTP/2 all requests to one host share one connection, and a request past the stream limit waits with no timeout.
  Both Oxylabs hosts negotiate HTTP/2 and allow 100 concurrent streams.
  An oxy-side limit of at most 100 concurrent requests therefore fits inside both the default pool and that stream limit.
- **Headers.**
  `response.headers.get()` returns `str | None` where httpx returns `Any`.
  Header lookup is case-insensitive.
- **Typing and platform.**
  Both packages ship `py.typed`, and CI runs mypy in strict mode.
  The strict preset of pyrefly finds no errors in httpx2's API.
  Installing httpx2 requires Python 3.10 or later, and it adds anyio, h11, httpcore2, idna, truststore and typing-extensions.
- **Maintenance.**
  Pydantic has published 17 releases since 2026-05-11, all by Marcelo Trylesinski.
  No document states a versioning policy, and minor releases have dropped Python 3.9 and replaced certifi with the operating system's trust store.
- **Relative to httpx.**
  Every public name in httpx 0.28.1 keeps its parameters and defaults.
  The changes are additions, narrower annotations and a few deprecations.
  Five things break: the import name, class identity across the two packages, logger and User-Agent names, certifi, and mocking libraries built for httpx.

## Sync and async

### What httpx2 ships

`Client` and `AsyncClient` both subclass `BaseClient` ([`_client.py`][client-classes]).
`BaseClient` holds the configuration, builds requests, merges URLs, headers, cookies and query parameters, and computes redirects.
`Client` defines `send`, `request`, `stream`, the verb methods and a private send chain as plain methods, and `AsyncClient` defines them again as `async` methods ([sync path][client-sync-io], [async path][client-async-io]).
Transports split the same way, into `BaseTransport.handle_request` and `AsyncBaseTransport.handle_async_request` ([`base.py`][base]).
Both clients use the same `Request`, `Response`, `Headers`, `Timeout` and `Limits` classes, and the same exceptions.
A non-streaming `send()` reads the body before it returns in both clients, so `response.json()` needs no `await` after either ([`_client.py`][client-send-read]).

### How httpx2 avoids writing everything twice

httpx2 uses three techniques, and none of them covers the whole library.

1. **A shared base class.**
   `BaseClient` holds everything that does no I/O.
   Both clients still carry a hand-written copy of the I/O path: lines 949 to 1094 of `_client.py` for `Client`, and lines 1787 to 1932 for `AsyncClient`.
2. **Generator flows for authentication.**
   `Auth.auth_flow` is a generator that yields requests and receives responses.
   `sync_auth_flow` and `async_auth_flow` drive the same generator, and they differ only in `response.read()` against `await response.aread()` ([`_auth.py`][auth]).
3. **Generated sync code, in `httpcore2` only.**
   The `_async` modules are the source.
   `scripts/unasync.py` rewrites them into `_sync` with 20 regex substitutions, such as `async def` to `def` and `aclose` to `close` ([`unasync.py`][unasync]).
   CI runs the script in check mode, and ruff and coverage skip the generated files ([`check`][check], [`pyproject.toml`][root-pyproject]).

`MockTransport` is the one class that serves both clients, because it subclasses both transport bases ([`mock.py`][mock]).
The same three techniques appear in httpx 0.28.1 and httpcore 1.0.9 ([httpcore `unasync.py`][httpcore-unasync]).

This trimmed excerpt from `_auth.py` shows one generator and its sync driver:

```python
def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
    yield request


def sync_auth_flow(self, request: Request) -> Generator[Request, Response, None]:
    flow = self.auth_flow(request)
    request = next(flow)
    while True:
        response = yield request
        if self.requires_response_body:
            response.read()  # async_auth_flow awaits response.aread() here
        try:
            request = flow.send(response)
        except StopIteration:
            break
```

### What that means for one oxy code path

The shared models make a sans-IO core practical.
A function that takes an `httpx2.Response` and returns oxy's next step works with responses from either client.
Only the I/O steps differ: `client.send()` against `await client.send()`, `time.sleep()` against `anyio.sleep()`, and threads against tasks for concurrent status checks.
A generator core in the `auth_flow` style yields those steps, and two short drivers run them.
A transport error raises in the driver, not in the generator.
A driver that retries network errors passes the exception back with `generator.throw()`, whereas httpx2's auth drivers let it propagate.

Two other routes exist:

- **Async code with generated sync code**, as `httpcore2` does.
  The httpx2 repo keeps its script as a 104-line file and does not publish it.
- **An async core behind a sync facade.**
  The anyio package, which httpx2 already installs, provides `anyio.from_thread.start_blocking_portal`.
  It runs an event loop in its own thread, and sync code calls async functions through it ([anyio docs][anyio-threads]).

Concurrent status checks from the sync `Client` need threads.
The `Client` docstring states that one client can be shared between threads ([`_client.py`][client-thread]).

## Transports and the test seam

Both clients take a `transport` argument and send every request through it ([transports docs][docs-transports]).
`MockTransport(handler)` passes each request to `handler` and returns the handler's `Response`.
A handler can also raise an httpx2 exception to simulate a network failure:

```python
def handler(request: httpx2.Request) -> httpx2.Response:
    if request.url.path == "/v1/queries":
        return httpx2.Response(429)
    raise httpx2.ReadTimeout("simulated", request=request)


client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
```

Running each case showed four things:

- One sync handler serves both `Client` and `AsyncClient`.
- An async handler serves only `AsyncClient`, and `Client` raises `TypeError: Cannot use an async handler in a sync Client`.
- An exception from the handler reaches the caller unchanged, with its `request` attached.
- The client sets `response.request` on each mock response.

`mounts={"all://data.oxylabs.io": httpx2.MockTransport(handler)}` mocks one host and leaves requests to other hosts on the default transport.
`WSGITransport` and `ASGITransport` call an in-process web app instead of a handler.

Three details matter for oxy's seam:

- **`MockTransport` bypasses the connection pool.**
  `retries`, `Limits`, the `pool` timeout and HTTP/2 do not run under test.
  A test of pacing or concurrency therefore exercises oxy's own limiter and nothing in httpx2.
- **The client uses a supplied transport as it is.**
  The client's `verify`, `cert`, `http1`, `http2` and `limits` configure only the `HTTPTransport` that it builds when `transport` is `None` ([`_client.py`][client-init-transport]).
  Measured: `Client(transport=HTTPTransport(), limits=Limits(max_connections=1))` keeps a pool of 100 connections.
- **A supplied transport turns off proxy environment variables.**
  The client sets `allow_env_proxies = trust_env and transport is None` ([`_client.py`][client-env]).
  Measured: with `HTTPS_PROXY` set, `Client()` mounts a proxy transport and `Client(transport=...)` mounts none.
  That isolates tests from a developer's proxy, and it bypasses a user's proxy if oxy passes its own transport in production.

RESPX 0.23.1 and pytest-httpx 0.36.2 intercept httpx requests but not httpx2 requests, which reach the network (measured).
The docs list two httpx2 plugins instead: `httpx2-pytest`, a fork of pytest-httpx, and `pytest-HTTPX2`, a plugin based on RESPX ([third-party packages][docs-third-party]).
`MockTransport` meets oxy's requirement without either.

## Retries

`HTTPTransport(retries=N)` and `AsyncHTTPTransport(retries=N)` pass `retries` to `httpcore2`'s connection pool ([`default.py`][default-retries]).
The retry loop runs only while a connection opens, and it catches only `ConnectError` and `ConnectTimeout` ([`connection.py`][hc-retry-loop]).
This trimmed excerpt from `httpcore2/_async/connection.py` shows the loop:

```python
RETRIES_BACKOFF_FACTOR = 0.5  # 0s, 0.5s, 1s, 2s, 4s, etc.

while True:
    try:
        stream = await self._network_backend.connect_tcp(**kwargs)
        ...  # TLS handshake
        return stream
    except (ConnectError, ConnectTimeout):
        if retries_left <= 0:
            raise
        retries_left -= 1
        await self._network_backend.sleep(next(delays))
```

- The backoff factor is a module constant, so only the retry count is configurable.
- `Client` and `AsyncClient` take no `retries` argument.
  Using it means passing a transport, with the side effects above.
- `HTTPTransport(proxy=...)` builds an `HTTPProxy` or `SOCKSProxy` pool without `retries` ([`default.py`][default-proxy]).
  Measured: `HTTPTransport(proxy="http://127.0.0.1:3128", retries=3)` builds a pool with 0 retries.
- The docs recommend a general tool such as tenacity for read and write errors and for status codes such as 503 ([transports docs][docs-transports]).

Two runs confirm the scope:

- `HTTPTransport(retries=3)` against a refused port raised `ConnectError` after 1.57 s, which matches sleeps of 0, 0.5 and 1 s.
- `HTTPTransport(retries=3)` against a server that returns 503 sent one request and returned the 503.

The same constant and `except` clause appear in httpcore 1.0.9, so httpx behaves the same ([httpcore `connection.py`][httpcore-connection]).
The retry policy for 429s, 5xx responses, network errors and timeouts is therefore oxy's own code.
That policy can cover connect errors too, which makes `retries=` redundant.

## Timeouts

Connect, read, write and pool each default to 5 s ([`_config.py`][config-defaults], [timeouts docs][docs-timeouts]).
The read timeout limits the wait for each chunk of the response, and the write timeout limits each chunk of the request.
No httpx2 setting limits a whole request.
A Realtime request receives nothing until its job finishes, so its read timeout must exceed the job's duration.
Oxylabs sets a 150 s TTL on API connections and asks for a 180 s client timeout on rendered Realtime jobs ([Integration Methods][ox-integration], [JS rendering][ox-js-rendering]).
A per-request `timeout=` overrides the client default, so one client can serve Realtime and Push-Pull.
The `pool` timeout limits the wait for a free connection, which the next section covers.

## Connection limits, pools and HTTP/2

`Limits` defaults to `max_connections=100`, `max_keepalive_connections=20` and `keepalive_expiry=5.0` ([`_config.py`][config-limits], [resource limits docs][docs-limits]).
It caps connections, not requests per second.

Over HTTP/1.1 each connection carries one request at a time.
A request that finds every allowed connection busy waits in the pool's queue, and it raises `PoolTimeout` if no connection frees up within the `pool` timeout ([`connection_pool.py`][hc-pool-wait]).

Over HTTP/2 the pool counts a connection as available while it has stream IDs left.
Every request to one host therefore goes onto one connection ([`connection.py`][hc-connection-avail], [`http2.py`][hc-http2-avail]).
A request past the stream limit waits on a semaphore that has no timeout ([`http2.py`][hc-http2-sem]).
The stream limit is the smaller of the server's `MAX_CONCURRENT_STREAMS` and 100, the value `httpcore2` sends ([`http2.py`][hc-http2-settings]).
HTTP/2 needs the `httpx2[http2]` extra and `http2=True`.
The docs keep it off by default and call the HTTP/1.1 implementation the more robust option ([HTTP/2 docs][docs-http2]).

Four runs against local servers show the difference:

| Server | Client | Result |
| --- | --- | --- |
| HTTP/1.1, 1 s per request | 6 concurrent requests, `max_connections=2`, `pool=0.5` | 2 succeed, 4 raise `PoolTimeout` |
| HTTP/1.1, 1 s per request | The same with `pool=None` | 6 succeed in 3.0 s |
| HTTP/2 limited to 10 streams, 0.5 s per request | 30 concurrent requests, `http2=True`, `max_connections=2`, `pool=0.2` | 30 succeed in 1.6 s over 1 connection, at most 10 at once |
| HTTP/2 limited to 10 streams, 0.5 s per request | The same with `http2=False` | 2 succeed, 28 raise `PoolTimeout` |

With `http2=True`, `data.oxylabs.io` and `realtime.oxylabs.io` both negotiate HTTP/2 and advertise `MAX_CONCURRENT_STREAMS` of 100 (measured with one unauthenticated request to each).
One HTTP/2 connection therefore carries up to 100 concurrent requests to each host, and further requests wait for a free stream.

Three consequences follow for oxy:

- Under HTTP/2, `Limits` does not bound concurrent requests.
- Under HTTP/1.1, concurrency above `max_connections` raises `PoolTimeout` whenever a queued request waits longer than the `pool` timeout.
- An oxy-side limit of at most 100 concurrent requests fits inside both the default pool and Oxylabs' stream limit, under either protocol.

## Rate-limit pacing and response headers

httpx2 has no pacing, no requests-per-second limit and no `Retry-After` handling, so oxy parses the `x-ratelimit-*` headers and sleeps itself.

- `response.headers` is a case-insensitive multi-dict.
  `keys()` and `items()` return lowercase names, and `get()` matches any case.
  `raw` keeps the bytes as received (measured).
- `Headers.get` returns `str | None` ([`_models.py`][models-headers-get]).
  In httpx 0.28.1 it returns `Any` ([httpx `_models.py`][httpx-headers-get]), so the `None` check that pyrefly now requires is new.
- Event hooks receive every response before the client reads the body, including redirect responses ([event hooks docs][docs-hooks]).
  Hooks on `AsyncClient` must be async functions, so a hook that reads headers needs a sync and an async version.
- A transport wrapper is a `BaseTransport` or `AsyncBaseTransport` subclass that calls an inner transport.
  It also receives every request and response ([transports docs][docs-transports]).
  Under test the inner transport can be a `MockTransport`, so pacing and retry code in a wrapper still runs.
  A wrapper needs one class per client type, unless it defines both methods as `MockTransport` does.
- The sleep between submissions is I/O, so it differs between sync and async code like every other I/O step.

## Typing and tooling

- Both packages ship `py.typed` ([httpx2][py-typed], [httpcore2][hc-py-typed]).
- CI runs mypy with `strict = true` over the source and the tests ([`pyproject.toml`][root-pyproject], [`check`][check]).
- The strict preset of pyrefly 1.3.1 reports no errors in httpx2's API.
  Those are the version and preset oxy uses.
  The probe built both clients, a `MockTransport` with sync and async handlers, and an `AsyncBaseTransport` subclass marked with `@override`.
- `Response.json()` returns `Any`, so oxy validates parsed JSON itself.
- On Python 3.11 `override` comes from `typing_extensions`, which httpx2 already installs below Python 3.13.
- Ruff 0.16.8 flags blocking `httpx` calls inside `async def` with [ASYNC210][ruff-async210] and [ASYNC212][ruff-async212], but it does not flag the same `httpx2` calls (measured).
  A sync `httpx2.Client` call inside oxy's async code gets no lint error.

## Python floor, dependencies and maintenance

- httpx2 needs Python 3.10 or later ([`pyproject.toml`][httpx2-pyproject]).
  Its classifiers list 3.10 to 3.15, and CI tests the same range on Ubuntu only ([`main.yml`][ci]).
  For comparison, httpx 0.28.1 needs Python 3.8.
- On Python 3.11 httpx2 2.13.1 resolves to seven packages: httpx2, httpcore2, h11, anyio, idna, truststore and typing-extensions ([PyPI JSON][pypi-httpx2], [`httpcore2` `pyproject.toml`][hc-pyproject]).
  `httpx2[http2]` adds h2, hpack and hyperframe.
  The httpx 0.28.1 set is the same, with httpcore in place of httpcore2 and certifi in place of truststore ([PyPI JSON][pypi-httpx]).
  For 2.13.1, PyPI holds an sdist and one pure-Python wheel tagged `py3-none-any` ([PyPI JSON][pypi-httpx2]).
- httpx2 pins `httpcore2` to its own version, and the two packages release in lockstep ([changelog][changelog], [`httpcore2` changelog][hc-changelog]).
- Pydantic has published 17 releases, from 2.0.0b1 on 2026-05-11 to 2.13.1 on 2026-09-23 ([releases][releases]).
  Besides 2.0.0b1 and 2.0.0, that is 13 minor releases and two patch releases in 19 weeks.
- Marcelo Trylesinski (GitHub `Kludex`, company `@pydantic`) published all 17 releases and authored 125 of the 201 commits dated in that window ([commits][commits], [user][kludex]).
  PyPI lists Pydantic Services Inc. as maintainer and Tom Christie as author ([PyPI JSON][pypi-httpx2]).
- The README says Pydantic took over stewardship because httpx had little recent activity, and it names timely security updates as a goal ([README][readme]).
- No httpx2 document states a versioning or deprecation policy, and the contributing guide covers only the release steps ([`CONTRIBUTING.md`][contributing]).
  The `httpcore2` README says it uses SemVer, in a line copied from the httpcore README ([`httpcore2` README][hc-readme], [httpcore README][httpcore-readme]).
  The PyPI classifier is "Production/Stable", where httpx 0.28.1 says "Beta".
- Minor releases have changed behaviour: 2.1.0 dropped Python 3.9, 2.3.0 replaced certifi with truststore, and 2.10.0 narrowed `Headers.get` from `Any` to `str | None` ([changelog][changelog]).
- The last httpx release is 0.28.1, from 2024-12-06 ([PyPI JSON][pypi-httpx]).
  Its `master` branch last changed on 2026-02-23 ([httpx commits][httpx-master]).
  Its pre-releases 1.0.dev1 to 1.0.dev6 describe a redesign that puts a client and a server in one package ([1.0.dev6 JSON][pypi-httpx-dev]).
  Those pre-releases depend only on truststore and typing-extensions.

## Why oxy's floor is 2.12.0

A review of every httpx2 and httpcore2 change from 2.0.0 to 2.13.1 found these costs below 2.12.0.
Each was checked against a 2.0.0 install.

- **An HTTP/2 connection closes under a request, fixed in 2.8.0.**
  The last stream to close on a connection can mark it idle while another request is starting on it ([#1013][pr-1013]).
  When no new request reaches that connection within the 5-second keep-alive expiry, the pool closes it, and the request in flight fails with `ReadError`.
  2.3.0's `fast_acquire` closes the window on asyncio only ([#970][pr-970]).
  On trio, 17 to 40 of 400 trials lost a request on each version up to 2.7.0, and none did from 2.8.0, whose pool stops expiring a connection that a request references ([#1075][pr-1075]).
  The retry policy retries a `ReadError`, but a submission that fails this way may already have created a billed job.
- **anyio below 4.5 breaks every request, fixed in 2.7.0.**
  In 2.3.0, httpcore2 creates its locks with `fast_acquire=True`, which anyio added in 4.5.0, while httpx2 2.3.0 to 2.6.0 accept any `anyio`.
  On asyncio, that pair raises `TypeError` on the first request, and oxy's retry policy does not catch it.
  From 2.7.0, httpx2 requires `anyio>=4.10`, so oxy's anyio floor is 4.10.0.
- **Each response body waits for the cyclic GC, fixed in 2.3.0.**
  A `Response` held a reference cycle through its stream ([#948][pr-948]).
  With 2 MB bodies, peak memory reached 68 to 82 MB on 2.0.0 and stayed at 16 MB on 2.3.0.
- **An IPv6 range in `NO_PROXY` breaks the client, fixed in 2.5.0.**
  An entry such as `fd00::/8` makes `AsyncClient` raise `InvalidURL`, so `AsyncSession` fails to build.
  The fake transport turns off environment proxies, so the `lowest` job cannot catch it.
- **Proxies leak or hang, fixed in 2.5.0 and 2.6.0.**
  Behind an HTTP CONNECT proxy, a request cancelled before its tunnel connects leaves a dead connection in the pool ([#983][pr-983]).
  150 cancels left 100 on 2.0.0, and every later request raised `PoolTimeout`.
  Before 2.5.0, a SOCKS5 handshake had no read or write timeout ([#1009][pr-1009]).
- **`verify=True` ignores the operating system's store, changed in 2.3.0.**
  It reads certifi's bundle, so a TLS-inspection CA held only in the operating system's store fails every request with `ConnectError`.
- **Reason phrases depend on the version, changed in 2.10.0.**
  413, 414, 416 and 422 take their RFC 9110 phrases, such as `Unprocessable Content`, and `codes.UNPROCESSABLE_CONTENT` appears.
  `OxylabsError.message` and `FakeOxylabs.fail(422)` read the phrase, so the fake's messages would change with the installed httpx2.
- **Security audits fail, fixed in 2.10.0 to 2.12.0.**
  [GHSA-7mj9-2mp8-4m2p][ghsa-socks] covers httpcore2 below 2.10.0, [GHSA-h4x7-gw46-3wm6][ghsa-multipart] covers httpx2 below 2.11.0, and [GHSA-8xx6-hgc6-gc2m][ghsa-decompress] covers httpx2 below 2.12.0.
  None of them reaches oxy: it never sends `wss://` through SOCKS5, never sends multipart, and reads whole bodies on every version.
  A user's audit still flags them.

Newer versions also save about 0.14 ms of CPU per HTTP/2 request, which Oxylabs' latency makes irrelevant.

## What changes relative to httpx

The changelog says httpx2 forked httpx 0.28.1 at commit `b5addb6`, which is still the latest commit on httpx's `master` (2026-02-23) ([changelog][changelog], [httpx commits][httpx-master]).

### Public API

A side-by-side import of both packages compared `__all__`, then the parameter names, kinds, defaults and return annotations of every public function, class and method.

- Every public name in httpx 0.28.1 exists in httpx2 with the same parameters and defaults.
- `main` left `__all__`, but `httpx2.main` still resolves and emits a `DeprecationWarning` ([`__init__.py`][init-main]).
- httpx2 adds `Client.sse`, `Client.websocket` and `Client.query`, and the same methods on `AsyncClient`.
  It also adds top-level `query` and `websocket`, `EventSource`, `ServerSentEvent`, `SSEError`, `FunctionAuth`, `Origin`, `URL.origin`, `alias_httpx` and the RFC 9110 names in `codes`.
- `Timeout` and `Limits` are now dataclasses, and their constructors are unchanged.
- `Headers.get` now returns `str | _T | None` instead of `Any`.
  `stream` and the `aiter_*` methods are now annotated as generators instead of iterators.
- Accessing an old `codes` name such as `UNPROCESSABLE_ENTITY` emits a `DeprecationWarning` ([`_status_codes.py`][codes]).

### Idioms that break

- `import httpx` becomes `import httpx2` ([migration guide][docs-migration]).
  The CLI, the User-Agent (`python-httpx2/<version>`) and the loggers (`httpx2` and `httpcore2.*`) change with it.
  The `httpx2` logger writes one INFO line per request, as httpx did ([`_client.py`][client-log]).
- httpx and httpx2 classes are distinct.
  An `httpx2.Client` fails a library's `isinstance(client, httpx.Client)` check, and `except httpx.HTTPError` does not catch httpx2 errors.
- `alias_httpx()` makes `import httpx` resolve to httpx2 for the whole process.
  The migration guide restricts it to applications, so a library such as oxy must not call it.
- `verify=True` reads the operating system's trust store through truststore instead of certifi's bundle ([`_config.py`][config-ssl], [httpx `_config.py`][httpx-certifi], [SSL docs][docs-ssl]).
  `SSL_CERT_FILE` and `SSL_CERT_DIR` still take precedence under the default `trust_env=True`.
  A container image without a system CA bundle therefore needs one installed, or `SSL_CERT_FILE` set.
- RESPX and pytest-httpx do not intercept httpx2 requests, as the runs above show.
- The migration guide says deprecations now use `HTTPXDeprecationWarning`, a `UserWarning` subclass that Python shows by default ([`_exceptions.py`][exc-deprecation]).
  At 2.13.1 only `URL.raw` uses it ([`_urls.py`][urls-raw]).
  Every other deprecation still emits a plain `DeprecationWarning`.

## Open questions

- **HTTP/2 against Oxylabs is unmeasured under load.**
  Both hosts support it with 100 streams, but nothing here shows whether it is faster or more reliable than HTTP/1.1 for oxy's status checks.
  A live test in [#9](https://github.com/ozanozbeker/oxyscraper/issues/9) can measure it.
- **No httpx2 document states a stability policy.**
  Two things are unconfirmed: whether the 2.x line keeps the 0.28 API, and whether `<3` is a safe upper bound for oxy.
  Either [#21](https://github.com/ozanozbeker/oxyscraper/issues/21) or a question to upstream can settle it.
- **Where retry and pacing code runs is a design choice for [#11](https://github.com/ozanozbeker/oxyscraper/issues/11), [#13](https://github.com/ozanozbeker/oxyscraper/issues/13) and [#14](https://github.com/ozanozbeker/oxyscraper/issues/14).**
  A transport wrapper needs a sync and an async class.
  A layer above the client can share one sans-IO core between both clients.
  `MockTransport` tests either.
- **The seam's shape is a design choice for #11 and #23.**
  Accepting a `transport` keeps oxy's timeouts and base URL.
  Accepting a whole client lets a user set proxies and limits, but the user's client then replaces oxy's settings.

## Sources

These files come from httpx2 at tag `v2.13.1` (commit `d91c9f4`):

- `_client.py` holds [the base class][client-classes], [the sync send path][client-sync-io], [the async send path][client-async-io], [the body read in `send`][client-send-read], [the thread-sharing note][client-thread], [`allow_env_proxies`][client-env], [`_init_transport`][client-init-transport] and [the request log line][client-log].
- [`_auth.py`][auth] defines the generator flow and its two drivers.
- [`_transports/base.py`][base] and [`_transports/mock.py`][mock] define the transport bases and `MockTransport`.
- `_transports/default.py` passes [`retries`][default-retries] to the plain pool but not to [the proxy pools][default-proxy].
- `_config.py` defines [`create_ssl_context`][config-ssl], [`Limits`][config-limits] and [the defaults][config-defaults].
- [`_models.py`][models-headers-get] defines `Headers.get`.
- [`__init__.py`][init-main], [`_status_codes.py`][codes], [`_exceptions.py`][exc-deprecation] and [`_urls.py`][urls-raw] hold the deprecations.
- [`httpx2/py.typed`][py-typed] and [`httpcore2/py.typed`][hc-py-typed] mark both packages as typed.
- `httpcore2/_async/connection.py` holds [the retry loop][hc-retry-loop] and [HTTP/2 availability before connecting][hc-connection-avail].
- `httpcore2/_async/connection_pool.py` holds [the `pool` timeout wait][hc-pool-wait].
- `httpcore2/_async/http2.py` holds [the stream semaphore][hc-http2-sem], [the advertised stream limit][hc-http2-settings] and [`is_available`][hc-http2-avail].
- [`scripts/unasync.py`][unasync], [`scripts/check`][check], [the root `pyproject.toml`][root-pyproject], [the `httpx2` `pyproject.toml`][httpx2-pyproject], [the `httpcore2` `pyproject.toml`][hc-pyproject] and [the CI workflow][ci] set the build, lint and test setup.
- [The httpx2 changelog][changelog], [the httpcore2 changelog][hc-changelog], [the README][readme], [the `httpcore2` README][hc-readme] and [`CONTRIBUTING.md`][contributing] record releases and policy.

These docs pages come from the same tag, and [pydantic.dev/docs/httpx2][docs-site] publishes them:

- [Migrating from HTTPX][docs-migration] lists the renames, the behaviour differences and `alias_httpx()`.
- [Transports][docs-transports] covers `transport=`, `retries`, `MockTransport`, mounts and custom transports.
- [Timeouts][docs-timeouts], [Resource Limits][docs-limits] and [HTTP/2][docs-http2] cover pool and protocol settings.
- [Event Hooks][docs-hooks], [SSL][docs-ssl] and [Third Party Packages][docs-third-party] cover hooks, certificates and plugins.

These sources cover httpx and httpcore:

- httpx at tag `0.28.1` (commit `26d48e0`) defines [`Headers.get`][httpx-headers-get] and [the certifi default][httpx-certifi].
- [The httpx `master` history][httpx-master] shows the fork point and the last change.
- httpcore at tag `1.0.9` (commit `9820975`) holds [`connection.py`][httpcore-connection], [`unasync.py`][httpcore-unasync] and [the README][httpcore-readme].

These package indexes and GitHub endpoints supply release data:

- [httpx2 on PyPI][pypi-httpx2] lists dependencies, the Python floor, files, classifiers and maintainers.
- [httpx on PyPI][pypi-httpx] and [httpx 1.0.dev6 on PyPI][pypi-httpx-dev] list the httpx releases.
- [The httpx2 releases][releases], [the httpx2 commits since the fork][commits] and [the `Kludex` user record][kludex] show who publishes.

These other primary sources back single claims:

- [anyio: using threads][anyio-threads] documents `start_blocking_portal`.
- Ruff documents [ASYNC210][ruff-async210] and [ASYNC212][ruff-async212].
- Oxylabs [Integration Methods][ox-integration] sets the 150 s TTL.
- Oxylabs [JS rendering][ox-js-rendering] asks for the 180 s client timeout.

[client-classes]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L179-L563
[client-sync-io]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L949-L1094
[client-async-io]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L1787-L1932
[client-send-read]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L985-L994
[client-thread]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L566-L571
[client-env]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L659
[client-init-transport]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L690-L710
[client-log]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_client.py#L1085-L1092
[auth]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_auth.py#L38-L106
[base]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_transports/base.py
[mock]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_transports/mock.py#L15-L39
[default-retries]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_transports/default.py#L151-L163
[default-proxy]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_transports/default.py#L164-L206
[config-ssl]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_config.py#L24-L43
[config-limits]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_config.py#L157-L175
[config-defaults]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_config.py#L218-L219
[models-headers-get]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_models.py#L241-L247
[init-main]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/__init__.py#L116-L130
[codes]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_status_codes.py#L8-L27
[exc-deprecation]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_exceptions.py#L75-L82
[urls-raw]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/_urls.py#L420
[py-typed]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/httpx2/py.typed
[hc-py-typed]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/httpcore2/py.typed
[hc-retry-loop]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/httpcore2/_async/connection.py#L98-L149
[hc-connection-avail]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/httpcore2/_async/connection.py#L162-L168
[hc-pool-wait]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/httpcore2/_async/connection_pool.py#L203-L220
[hc-http2-sem]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/httpcore2/_async/http2.py#L104-L114
[hc-http2-settings]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/httpcore2/_async/http2.py#L184
[hc-http2-avail]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/httpcore2/_async/http2.py#L482-L488
[unasync]: https://github.com/pydantic/httpx2/blob/v2.13.1/scripts/unasync.py
[check]: https://github.com/pydantic/httpx2/blob/v2.13.1/scripts/check
[root-pyproject]: https://github.com/pydantic/httpx2/blob/v2.13.1/pyproject.toml
[httpx2-pyproject]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/pyproject.toml
[hc-pyproject]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/pyproject.toml
[ci]: https://github.com/pydantic/httpx2/blob/v2.13.1/.github/workflows/main.yml#L19
[changelog]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpx2/CHANGELOG.md
[hc-changelog]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/CHANGELOG.md
[readme]: https://github.com/pydantic/httpx2/blob/v2.13.1/README.md
[hc-readme]: https://github.com/pydantic/httpx2/blob/v2.13.1/src/httpcore2/README.md?plain=1#L99
[contributing]: https://github.com/pydantic/httpx2/blob/v2.13.1/.github/CONTRIBUTING.md#releasing
[docs-site]: https://pydantic.dev/docs/httpx2/
[docs-migration]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/migration.md
[docs-transports]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/advanced/transports.md
[docs-timeouts]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/advanced/timeouts.md
[docs-limits]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/advanced/resource-limits.md
[docs-http2]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/http2.md
[docs-hooks]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/advanced/event-hooks.md
[docs-ssl]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/advanced/ssl.md
[docs-third-party]: https://github.com/pydantic/httpx2/blob/v2.13.1/docs/third_party_packages.md
[httpx-headers-get]: https://github.com/encode/httpx/blob/0.28.1/httpx/_models.py#L242
[httpx-certifi]: https://github.com/encode/httpx/blob/0.28.1/httpx/_config.py#L31-L40
[httpx-master]: https://github.com/encode/httpx/commits/master
[httpcore-connection]: https://github.com/encode/httpcore/blob/1.0.9/httpcore/_async/connection.py#L19
[httpcore-unasync]: https://github.com/encode/httpcore/blob/1.0.9/scripts/unasync.py
[httpcore-readme]: https://github.com/encode/httpcore/blob/1.0.9/README.md?plain=1#L103
[pypi-httpx2]: https://pypi.org/pypi/httpx2/json
[pypi-httpx]: https://pypi.org/pypi/httpx/json
[pypi-httpx-dev]: https://pypi.org/pypi/httpx/1.0.dev6/json
[releases]: https://api.github.com/repos/pydantic/httpx2/releases
[commits]: https://api.github.com/repos/pydantic/httpx2/commits?since=2026-05-11T00:00:00Z&until=2026-09-24T00:00:00Z
[kludex]: https://api.github.com/users/Kludex
[anyio-threads]: https://anyio.readthedocs.io/en/stable/threads.html
[ruff-async210]: https://docs.astral.sh/ruff/rules/blocking-http-call-in-async-function/
[ruff-async212]: https://docs.astral.sh/ruff/rules/blocking-http-call-httpx-in-async-function/
[ox-integration]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods
[ox-js-rendering]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control
[pr-948]: https://github.com/pydantic/httpx2/pull/948
[pr-970]: https://github.com/pydantic/httpx2/pull/970
[pr-983]: https://github.com/pydantic/httpx2/pull/983
[pr-1009]: https://github.com/pydantic/httpx2/pull/1009
[pr-1013]: https://github.com/pydantic/httpx2/pull/1013
[pr-1075]: https://github.com/pydantic/httpx2/pull/1075
[ghsa-socks]: https://github.com/advisories/GHSA-7mj9-2mp8-4m2p
[ghsa-multipart]: https://github.com/advisories/GHSA-h4x7-gw46-3wm6
[ghsa-decompress]: https://github.com/advisories/GHSA-8xx6-hgc6-gc2m

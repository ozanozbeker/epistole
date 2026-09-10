# Vendor SDKs versus raw REST for Gmail and Graph

Answers [issue #5](https://github.com/ozanozbeker/epistole/issues/5).
Maintenance figures were measured on 2026-09-07 and go stale.
See [Figures to recheck](#figures-to-recheck).

## Recommendation

Call REST directly for both backends.
Take credentials from the vendor auth library and leave the vendor client out of the dependency tree.

| Extra | Depend on | Do not depend on |
| --- | --- | --- |
| `epistole[gmail]` | `google-auth` | `google-api-python-client`, `google-auth-oauthlib` |
| `epistole[graph]` | `msal` | `msgraph-sdk`, `msgraph-core`, `azure-identity` |

Write the transport on `urllib.request` from the standard library.
Do not add `httpx`.
Both auth libraries let epistole supply its own HTTP, so `httpx` would buy nothing that `urllib.request` does not already give a sync-only library, and its stable line has not moved in 21 months ([evidence](#httpx)).

What that costs, measured (see [Install weight](#2-install-weight)):

| Extra | Packages | Installed | Download |
| --- | --- | --- | --- |
| `google-api-python-client` + `google-auth-oauthlib` | 25 | 125.9 MiB | 21.5 MiB |
| `google-auth` alone | 6 | 15.6 MiB | 4.5 MiB |
| `msgraph-sdk` | 42 | 188.2 MiB | 34.3 MiB |
| `msal` alone | 10 | 16.2 MiB | 4.7 MiB |

The two backends reach the same answer by different routes, and the reasoning does not transfer between them.

**Gmail.**
Google has declared the SDK finished.
The README says the library "is considered complete and is in maintenance mode" and steers new code at the Cloud Client Libraries instead ([source](https://github.com/googleapis/google-api-python-client/blob/main/README.md)).
There is no Cloud Client Library for Gmail, because Gmail is a Workspace API, so that advice has no destination.
Releases still ship weekly, but they are regenerated discovery documents, not maintenance of the Python code.
For one send call the SDK contributes a URL, a base64url encode, and an exception class.
Its retry helper is off unless you pass `num_retries` yourself.

**Graph.**
The SDK is alive and does real work, but it is the wrong shape for epistole.
It is async-only: every generated request builder is an `async def`, and the README calls async "the default" ([source](https://github.com/microsoftgraph/msgraph-sdk-python/blob/main/README.md)).
Issue #2 fixes epistole as sync-only, so the SDK would mean `asyncio.run()` per send.
The SDK's headline feature for a send is a retry middleware that fires by default on 429, 503 and 504, and issue #2 already ruled out epistole owning a retry policy.
Adopting the SDK means adopting behaviour epistole decided against, then configuring it back off.
It also pins `httpx<1.0.0` transitively and drags in `aiohttp`, `requests` and `opentelemetry-sdk`, which is a lot of resolver surface for one POST.

**Where the call is closest.**
Graph attachments over 3 MB.
`msgraph-core` ships a real `LargeFileUploadTask`, and hand-writing the equivalent is the one piece of genuine work this decision creates.
Section 4 sizes it: roughly 60 lines, and the flow is four steps whichever way you go.
Gmail has no equivalent complexity, because its resumable upload is a single 35 MiB ceiling on one endpoint.

**On the standing constraint.**
REST-direct does not foreclose anything.
Both backends should accept a credential object, not a client object, and both vendors already define the credential interface epistole needs: `google.auth.credentials.Credentials` and `azure.core.credentials.TokenCredential`.
Section 5 shows that a caller's built SDK client can still be unwrapped, and why epistole should not ask for one.

## Evidence

### 1. Maintenance health

Method: `curl https://pypi.org/pypi/<name>/json` for versions and upload timestamps, `gh api repos/<repo>` and `gh api search/issues` for repository state.
All figures below are as of **2026-09-07**.

| Package | Latest | Released | Releases since 2024-09-07 | Median gap | Open issues | Open PRs |
| --- | --- | --- | --- | --- | --- | --- |
| `google-api-python-client` | 2.200.0 | 2026-09-01 | 55 | 11 days | 23 | 28 |
| `google-auth` | 2.57.1 | 2026-09-04 | 40 | 10 days | 14 (title match in monorepo) | n/a |
| `google-auth-oauthlib` | 1.4.1 | 2026-08-24 | 7 | 77 days | n/a | n/a |
| `msgraph-sdk` | 1.62.0 | 2026-09-02 | 53 | 12 days | 92 | 20 |
| `msgraph-core` | 1.5.1 | 2026-07-13 | 16 | 26 days | 18 | 22 |
| `azure-identity` | 1.25.3 | 2026-03-13 | 15 | 28 days | 11 (label `Azure.Identity`) | n/a |
| `msal` | 1.38.0 | 2026-08-24 | 18 | 41 days | 65 | 12 |
| `httpx` | 0.28.1 | **2024-12-06** | 8 (6 of them `1.0.dev*`) | 32 days | 0 | 77 |

Commits in the 90 days to 2026-09-07, via `gh api "repos/<repo>/commits?since=2026-06-09T00:00:00Z&per_page=100" --jq 'length'`:

```text
googleapis/google-api-python-client:                  17
microsoftgraph/msgraph-sdk-python:                    31
microsoftgraph/msgraph-sdk-python-core:               34
AzureAD/microsoft-authentication-library-for-python:  20
encode/httpx:                                          0
```

#### Google's signal on `google-api-python-client`

This is the sharpest finding, and it is stated by Google in the package's own README:

> This library is considered complete and is in maintenance mode.
> This means that we will address critical bugs and security issues but will not add any new features.
>
> This library is officially supported by Google.
> However, the maintainers of this repository recommend using Cloud Client Libraries for Python, where possible, for new code development.

Source: <https://github.com/googleapis/google-api-python-client/blob/main/README.md>

Read the two sentences together and the picture is specific, not alarming.
The package is supported and will keep getting security fixes.
It will not grow.
The recommended replacement does not cover Gmail: Cloud Client Libraries are generated per Cloud API, and Gmail is a Workspace API.
Google's own Gmail client library page still lists only "the Google API Client Library for Python" ([source](https://developers.google.com/workspace/gmail/api/downloads)).

So the weekly release cadence is misleading if read as health.
The 55 releases since September 2024 are discovery documents regenerated across roughly 600 Google APIs.
The Python code underneath them is frozen by policy.

#### `google-auth` and `google-auth-oauthlib` moved, they did not die

Both standalone repositories are archived:

```text
$ gh api repos/googleapis/google-auth-library-python --jq '{archived, description}'
{"archived":true,"description":"This library has moved to https://github.com/googleapis/google-cloud-python/tree/main/packages/google-auth"}
```

The archive is a monorepo consolidation, not abandonment.
`google-auth` shipped 40 releases in the last two years with a 10 day median gap, the tightest cadence of any package here, and 2.57.1 landed on 2026-09-04.

`google-auth-oauthlib` is the outlier: 7 releases in two years, 77 day median gap, 191 day longest.
It exists only to run three-legged OAuth flows (`InstalledAppFlow`, `Flow`).
Issue #2 puts OAuth flows out of scope, so epistole does not need it and should not carry its slow cadence.

#### `msgraph-sdk` is active and knows it is heavy

31 commits in 90 days, 53 releases in two years, 12 day median gap.
No deprecation or maintenance-mode notice anywhere in the README or repository metadata.
The README does warn about weight:

> The Microsoft Graph SDK for Python is a fairly large package.
> It may take a few minutes for the initial installation to complete.

The size problem is tracked and unresolved:

| Issue | Opened | State on 2026-09-07 |
| --- | --- | --- |
| [#939 Split the SDK into smaller parts](https://github.com/microsoftgraph/msgraph-sdk-python/issues/939) | 2024-10-22 | open, last touched 2025-02-04 |
| [#1287 kiota-dom-export.txt is large and included in the released package](https://github.com/microsoftgraph/msgraph-sdk-python/issues/1287) | 2025-07-11 | open, last touched 2026-05-26 |

Issue #1287 is worth naming precisely: `msgraph/generated/kiota-dom-export.txt` is 35.7 MiB of code-generator metadata shipped inside the wheel.
It has been known and unfixed for 14 months.

#### `azure-identity` is the slowest link in the Graph chain

No stable release since 1.25.3 on 2026-03-13, roughly six months.
It lives inside `Azure/azure-sdk-for-python`, a monorepo with 1115 open issues across all services, of which 11 carry the `Azure.Identity` label.
`msal` underneath it is more current: 1.38.0 on 2026-08-24, 20 commits in 90 days.
Depending on `msal` directly skips the slower layer and drops `azure-core`, `msal-extensions` and `typing-extensions` from the tree.

#### httpx

`httpx` is the one package here whose stable line has genuinely stalled.

```text
latest stable:        0.28.1, 2024-12-06   (21 months old)
since then:           1.0.dev1 .. 1.0.dev6, the last on 2026-08-31
last commit on master: 2026-02-23
commits in 90 days:    0
open PRs:             77
```

The `1.0.0.beta0` tag in the repository dates to 2021-09-14, so the 1.0 line has been imminent for five years.
None of this makes `httpx` unusable, and 0.28.1 is stable code.
It does mean two things for epistole.
First, a 1.0 release is a breaking change waiting to land in an extra epistole does not control.
Second, `microsoft-kiota-http` pins `httpx[http2]>=0.25,<1.0.0`, so anyone who installs `msgraph-sdk` alongside another `httpx` consumer inherits that ceiling.
Both problems disappear if epistole writes its transport on `urllib.request`.

### 2. Install weight

Method: one throwaway venv per candidate, `uv venv --python 3.13` then `uv pip install`, sizes from `du -sk` on `site-packages`, package counts from `uv pip list`.
Download figures sum the wheel sizes reported by the PyPI JSON API for the exact resolved versions, preferring `py3-none-any` and falling back to `macosx_arm64`.
An empty venv measures 0.0 MiB, so every figure below is the delta.
Resolved on macOS arm64, Python 3.13.12, `uv` 0.12.10, on 2026-09-07.

| Candidate | Packages | Installed | Download |
| --- | --- | --- | --- |
| `google-api-python-client` + `google-auth-oauthlib` | 25 | 125.9 MiB | 21.5 MiB |
| `google-auth` + `httpx` | 13 | 17.9 MiB | 5.1 MiB |
| **`google-auth` alone** | **6** | **15.6 MiB** | **4.5 MiB** |
| `msgraph-sdk` | 42 | 188.2 MiB | 34.3 MiB |
| `msal` + `httpx` | 15 | 17.9 MiB | 5.0 MiB |
| **`msal` alone** | **10** | **16.2 MiB** | **4.7 MiB** |
| `azure-identity` alone | 14 | 18.1 MiB | n/a |
| `httpx` alone | 7 | 2.3 MiB | n/a |

Gmail drops 8.1x on disk, Graph drops 11.6x.

#### Where the weight actually sits

```text
gmail_sdk, top of du -sk site-packages/*
   101.7 MiB  googleapiclient        <- 101.5 MiB of it is discovery_cache
    12.0 MiB  cryptography
     4.5 MiB  google

graph_sdk, top of du -sk site-packages/*
   159.2 MiB  msgraph                <- all of it under msgraph/generated
    12.0 MiB  cryptography
     1.9 MiB  aiohttp
     1.8 MiB  opentelemetry
```

`googleapiclient/discovery_cache/documents/` holds 600 JSON files, one per Google API.
The one epistole needs, `gmail.v1.json`, is 151,948 bytes. epistole would ship 101.5 MiB to use 0.14 MiB of it, and the cache cannot be trimmed at install time.

`msgraph/generated` contains 16,572 `.py` files plus the 35.7 MiB `kiota-dom-export.txt` from issue #1287.
By comparison `googleapiclient` is 16 `.py` files, because Google's design puts the API surface in data and Microsoft's puts it in generated code.

Note that `cryptography` at 12.0 MiB is unavoidable.
`google-auth` requires it (`cryptography>=38.0.3`) and so does `msal` (`cryptography<51,>=2.5`).
It is 77% of the recommended Gmail extra and 74% of the recommended Graph extra.
Neither backend can go below roughly 16 MiB while doing real authentication.

#### Resolver surface

`msgraph-sdk` pulls two complete HTTP stacks and an observability SDK:

```text
$ uv pip tree --python .../graph_sdk/bin/python   (abridged)
msgraph-sdk v1.62.0
├── azure-identity -> azure-core -> requests -> {certifi, charset-normalizer, idna, urllib3}
│                  -> msal -> {cryptography, pyjwt, requests}
│                  -> msal-extensions
├── microsoft-kiota-serialization-{form,json,multipart,text}
│     └── microsoft-kiota-abstractions -> {opentelemetry-api, opentelemetry-sdk, std-uritemplate}
└── msgraph-core
      ├── httpx[http2] -> {anyio, certifi, httpcore, h2, hpack, hyperframe}
      ├── microsoft-kiota-authentication-azure -> aiohttp -> {aiohappyeyeballs, aiosignal,
      │                                                        attrs, frozenlist, multidict,
      │                                                        propcache, yarl}
      └── microsoft-kiota-http -> httpx[http2]>=0.25,<1.0.0
```

`microsoft-kiota-abstractions` requires `opentelemetry-sdk`, not just `opentelemetry-api`.
A library requiring the SDK rather than the API is a known way to collide with an application's own tracing setup.

The Gmail SDK is smaller but not clean either:

```text
google-api-python-client v2.200.0
├── google-api-core -> {googleapis-common-protos, proto-plus, protobuf, opentelemetry-api, requests}
├── google-auth
├── google-auth-httplib2 -> httplib2 -> pyparsing
└── uritemplate
```

`protobuf` arrives for a JSON-over-HTTP API that never uses it.
`httplib2` is a sync-only HTTP library that has no async story at all, which caps the Gmail SDK path forever.

#### What weight does not cost

Warm import time is a wash, and this surprised me:

```text
googleapiclient.discovery:   0.057s, 373 modules
msgraph.GraphServiceClient:  0.063s, 486 modules
google.oauth2.credentials:   0.037s, 270 modules
msal:                        0.038s, 344 modules
```

Building the Gmail service object from the cached discovery document takes 0.003s.
So the argument against the SDKs is install size, dependency conflicts and maintenance posture.
It is not runtime cost.

### 3. How tightly auth couples to the client

Not tightly.
Both vendors ship the credential layer as a separate package with its own HTTP abstraction, and both let a caller substitute their own transport.
The snippets below ran against local servers that returned canned OAuth responses, so the output is real.

#### `google-auth` alone

`google.auth.transport.Request` is a public one-method ABC.
Implement it over anything.
This is the version epistole should ship, because `google.auth.transport._http_client` is documented "for internal use only" and `google.auth.transport.requests` raises `ImportError` unless `requests` is installed.

```python
import urllib.request

from google.auth import transport
from google.oauth2.credentials import Credentials


class _Response(transport.Response):
    def __init__(self, r):
        self._r = r
        self._data = r.read()

    @property
    def status(self):
        return self._r.status

    @property
    def headers(self):
        return dict(self._r.headers)

    @property
    def data(self):
        return self._data


class UrllibRequest(transport.Request):
    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kw):
        req = urllib.request.Request(
            url, data=body, headers=headers or {}, method=method
        )
        return _Response(urllib.request.urlopen(req, timeout=timeout))


creds = Credentials(
    token=None, refresh_token=..., token_uri=..., client_id=..., client_secret=...
)
creds.refresh(UrllibRequest())
```

Verified output, against a local server returning a canned token response:

```text
custom transport token: ya29.CUSTOM | valid: True
```

For a send, use `before_request`, which refreshes only if the token expired and then writes the header:

```text
$ python -c "...; creds.apply(headers); print(headers)"
{'authorization': 'Bearer ya29.FAKE'}
```

`Credentials.before_request(request, method, url, headers)` is the one call epistole needs.
It works identically for `google.oauth2.credentials.Credentials` (user OAuth), `google.oauth2.service_account.Credentials` (with `with_subject` for domain-wide delegation), and whatever `google.auth.default()` returns.

#### `msal` alone

`msal.ClientApplication` takes an `http_client` parameter.
The docstring calls for "your implementation of abstract class HttpClient", which is two methods, `get` and `post`.
Verified end to end against a stub:

```python
app = msal.ConfidentialClientApplication(
    client_id=...,
    client_credential=...,
    authority="https://login.microsoftonline.com/<tenant>",
    http_client=my_http_client,  # optional; defaults to a requests session
)
result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
headers = {"Authorization": f"{result['token_type']} {result['access_token']}"}
```

Verified output:

```text
  GET  https://login.microsoftonline.com/contoso.onmicrosoft.com/v2.0/.well-known/openid-configuration
  POST https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token | grant_type: client_credentials | scope: https://graph.microsoft.com/.default
result keys: ['access_token', 'expires_in', 'ext_expires_in', 'token_source', 'token_type']
header a REST call sends: {'Authorization': 'Bearer eyJ0eXAFAKE'}

second call served from cache (no POST expected):
cached: eyJ0eXAFAKE | token_source: cache
```

Two things worth keeping.
`msal` caches in memory and serves the second call from cache without a network round trip, so epistole does not need to track expiry itself.
`msal` also declares `requests` as a hard dependency regardless of `http_client`, so the Graph extra gets `requests` whether epistole uses it or not.
Injecting an `http_client` is therefore optional, and epistole should not bother unless a user asks for proxy control.

### 4. What the SDK does for one send that REST must reimplement

| Concern | Gmail SDK | Graph SDK | What epistole writes |
| --- | --- | --- | --- |
| Token refresh | `AuthorizedHttp` calls `creds.before_request` | kiota auth provider calls `credential.get_token` | one line, `creds.before_request(...)` or `app.acquire_token_for_client(...)` |
| Retries | **off by default** | 3 retries on 429/503/504, honours `Retry-After` | nothing; issue #2 rules retry out of scope |
| Large attachments | resumable upload helper for one endpoint | `LargeFileUploadTask` in `msgraph-core` | Gmail: nothing. Graph: roughly 60 lines |
| Error typing | one `HttpError` class | `ODataError(APIError)` with typed fields | parse the vendor error envelope, raise epistole's own |
| Batching | `BatchHttpRequest` | `$batch` builders in `msgraph-core` | nothing; epistole sends one message |
| Endpoint knowledge | 600 cached discovery documents | 16,572 generated request builders | two URL constants |

#### Retries

The Gmail SDK does not retry unless you ask:

```python
# googleapiclient/http.py
def execute(self, http=None, num_retries=0):
    """...If zero (default), we attempt the request only once."""
```

`build(..., num_retries=1)` looks like a default but only covers fetching the discovery document (`discovery.py:440`).
Per-request retries are opt-in.
When enabled, `_should_retry_response` covers 5xx, 429, and 403 whose body carries a rate-limit reason.

The Graph SDK does retry, on by default:

```text
kiota_http/middleware/options/retry_handler_option.py
  DEFAULT_MAX_RETRIES = 3
  DEFAULT_DELAY       = 3.0 seconds
  MAX_DELAY           = 180.0 seconds

kiota_http/middleware/retry_handler.py
  DEFAULT_RETRY_STATUS_CODES = {429, 503, 504}
  backoff = {backoff factor} * (2 ** ({retry number} - 1)), overridden by Retry-After
```

This is the one place the Graph SDK gives away real, correct code.
It is also the one place epistole has already decided not to go.
Issue #2: "No retry policy.
Errors expose `retry_after` where the provider gives one."
Reading `Retry-After` off a 429 is a header lookup, and that is the whole requirement.

#### Large attachments

Gmail is simple.
From the cached discovery document `gmail.v1.json` (revision 20260727):

```json
"send": {
  "path": "gmail/v1/users/{userId}/messages/send",
  "supportsMediaUpload": true,
  "mediaUpload": {
    "accept": ["message/*"],
    "maxSize": "36700160",
    "protocols": {
      "simple":    {"multipart": true, "path": "/upload/gmail/v1/users/{userId}/messages/send"},
      "resumable": {"multipart": true, "path": "/resumable/upload/gmail/v1/users/{userId}/messages/send"}
    }
  }
}
```

36,700,160 bytes is exactly 35 MiB, and that is the hard ceiling.
Google's upload guide puts simple and multipart at "5 MB or less" and resumable above ([source](https://developers.google.com/workspace/gmail/api/guides/uploads)).
So epistole picks one of two URLs by message size and POSTs a base64url RFC 5322 message.
There is no session to manage.

Graph is where the work is.
Attachments over 3 MB cannot go inline, and the flow is four requests, not one ([source](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)):

1. `POST /me/messages` to create a draft.
2. `POST /me/messages/{id}/attachments/createUploadSession` with `{"AttachmentItem": {"attachmentType": "file", "name": ..., "size": ...}}`, which returns a pre-authenticated `uploadUrl` on `outlook.office.com` and an `expirationDateTime`.
3. `PUT` byte ranges to that URL with `Content-Range: bytes {start}-{end}/{total}`, no `Authorization` header, chunks under 4 MB, following `nextExpectedRanges` from each response.
4. `POST /me/messages/{id}/send`.

The ceiling is 150 MB.
Under 3 MB it is one `POST /me/sendMail` with `contentBytes` inline, or `Content-Type: text/plain` with a base64 MIME blob.

`msgraph_core/tasks/large_file_upload.py` implements step 3 generically.
Reimplementing it is a loop over ranges plus resume handling, and the other three steps are plain requests that the SDK does not simplify.
Call it 60 lines of epistole code against 188 MiB and an async runtime.

#### Error typing

The Gmail SDK gives one exception class, `googleapiclient.errors.HttpError`, with `.status_code`, `.reason` and `.error_details` parsed out of the JSON envelope.
The parsing has a comment warning that keyword order must not change or user code breaks (`errors.py`, referencing issue #1243).

The Graph SDK gives `ODataError(APIError)` carrying `message`, `response_status_code`, `response_headers` and a typed `error` object.

epistole will raise its own exception type either way, so both are one envelope parse rather than a reusable win.
Graph's envelope is `{"error": {"code", "message", "innerError"}}`.
Gmail's is `{"error": {"code", "message", "errors"}}`.

#### Batching

`BatchHttpRequest` posts to `https://gmail.googleapis.com/batch`, derived from `batchPath` in the discovery document.
`msgraph-core` ships `$batch` request and response builders.
Neither matters: epistole sends one message per call.

### 5. Accepting caller-supplied clients and credentials

A REST-direct backend accepts more, not less.
The right thing to accept is a credential, and both vendors already define a narrow interface for it.

**Gmail.**
Accept `google.auth.credentials.Credentials`.
Every Google credential type subclasses it, so one parameter covers user OAuth, service accounts with `with_subject`, and application default credentials. epistole calls `before_request(request, method, url, headers)` and supplies the `Request` from section 3.

**Graph.**
Accept anything matching `azure.core.credentials.TokenCredential`.
The protocol is one method:

```text
get_token(*scopes: str, claims=None, tenant_id=None, enable_cae=False, **kwargs) -> AccessToken
AccessToken._fields == ('token', 'expires_on')
```

That is a structural type, so epistole can declare it as a `Protocol` in its own code and never import `azure-core`.
Every `azure.identity` credential satisfies it.
An `msal` app is three lines from satisfying it.
A caller who already builds `ClientSecretCredential` for other Azure work hands it straight over.

Also accept a plain `str` token and a `Callable[[], str]` for both backends.
That covers callers who mint tokens somewhere else entirely, and it is what makes the extras genuinely optional.

**Unwrapping a built SDK client works, but do not ask for it.**
Both are reachable:

```text
googleapiclient Resource:  svc._http.credentials   -> the same object the caller passed in (verified)
msgraph GraphServiceClient: client.request_adapter._authentication_provider
                                  .access_token_provider._credentials   (verified)
```

The Gmail path goes through one underscore attribute.
The Graph path goes through three, two of which are private on classes owned by `kiota`, not by Microsoft Graph.
Supporting either means epistole breaks when a vendor renames a private attribute.
Accept the credential instead.
A caller who has a client also has the credential they built it from.

**On the standing constraint.**
Nothing here blocks epistole owning OAuth later.
Owning OAuth means epistole constructs the credential rather than receiving it, and the backend protocol is unchanged either way as long as it takes a credential and not a client.
Taking a client is the choice that would foreclose it, because it would tie the protocol to a vendor class epistole does not control.

## Figures to recheck

Measured on 2026-09-07.
The maintenance table, the install-weight table and the dependency trees all move.
Recheck before the packaging ticket locks extras, and specifically:

- Whether `httpx` 1.0 has shipped, and whether `microsoft-kiota-http` still pins `<1.0.0`.
- Whether msgraph-sdk issues [#939](https://github.com/microsoftgraph/msgraph-sdk-python/issues/939) and [#1287](https://github.com/microsoftgraph/msgraph-sdk-python/issues/1287) have closed.
  Closing #1287 alone removes 35.7 MiB.
- Whether `azure-identity` has shipped a stable release after 1.25.3.
- Whether Google has said anything further about `google-api-python-client`.
  The maintenance-mode text has been in the README for years, so a change would be news either way.

Reproduce the weight figures with:

```bash
uv venv --python 3.13 /tmp/w && VIRTUAL_ENV=/tmp/w uv pip install <candidate>
du -sk /tmp/w/lib/python3.13/site-packages
uv pip tree --python /tmp/w/bin/python
```

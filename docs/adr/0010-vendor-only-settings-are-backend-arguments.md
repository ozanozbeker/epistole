# A vendor-only setting is a backend argument, and a backend raises for a feature it cannot send

`docs/research/prior-art.md` names two mechanisms django-anymail needed to keep one API across fourteen providers.
`esp_extra` is a dict passed through to the provider.
`unsupported_feature()` raises unless a setting suppresses the error.
Epistole ships neither.
A setting only one mail service supports is a keyword argument on that backend's constructor.
A message never holds one.
`send` takes the message alone.
A backend that cannot carry a feature raises `RejectedError` with `__cause__` `None` before writing, as ADR-0004 already states.
Nothing downgrades that error to a warning.
Decided on [#17](https://github.com/ozanozbeker/epistole/issues/17).
Amended on [#27](https://github.com/ozanozbeker/epistole/issues/27): the custom-header consequence is closed (ADR-0016).

## Why

**The three cases the issue cites were already settled.**
Graph's 3 MB attachment threshold is a send strategy and a permission question on [#20](https://github.com/ozanozbeker/epistole/issues/20).
A knowable limit is `RejectedError` under ADR-0004.
Only SMTP refuses some recipients, and `SendResult.refused` reports them.
The field is empty on the two APIs by contract (ADR-0004).
The from address belongs to the backend.
When a service rejects it, Epistole raises `SenderRefusedError` (ADR-0001).

**Almost nothing can be unsupported.**
Gmail takes the RFC 5322 bytes as `raw`.
Graph accepts the same bytes as `text/plain`.
This ADR first assumed Graph's `sendMail` path would use them.
[ADR-0012](0012-graph-sends-json-on-two-paths-chosen-by-size.md) chose JSON on every Graph request instead, so the gap covers Graph at any size rather than its draft path alone.
On Graph, custom headers must start with `x-`.
Exchange also replaces the caller's plain text next to HTML with its own.
ADR-0012 treats that as degradation rather than rejection.
The count is still three backends and one gap.
Anymail's mechanism covers fourteen providers and twelve optional message attributes.
A method with one caller is a mechanism, not a design.

**The gap is a pre-check, not a new class.**
Under ADR-0004, a limit Epistole can check before writing is `RejectedError` with `__cause__` `None`, because the same message succeeds on another backend.
The caller should get one class whether Epistole or the service detects the limit first.
A custom header Graph cannot carry is exactly that case.
The fix is on the message, so `RejectedError` is the right class.
An eighth class would split one meaning across two names.

**Epistole adds no warning and no flag.**
ADR-0004 already rejected warnings because they are invisible in production logs.
An `ignore_unsupported` flag would be a setting that exists for one pre-check.
A caller who wants the degraded send strips the header first.

**The message stays backend-agnostic.**
The glossary says a message never carries a backend.
#9 says the send call takes the message and nothing else.
`backend_extra` on either would contradict both.
It would exist for request-level settings (Graph `saveToSentItems`, Gmail `threadId`) that are backend configuration, not message content.
Each backend is its own class, so those settings are already named, typed keyword arguments rather than a dict the backend forwards unchecked.

## Consequences

- Each provider-only setting worth exposing becomes a typed, documented keyword argument on the backend constructor.
  Anything not exposed is out of scope.
  The caller uses the provider's REST API for it.
- Per-message provider features that are MIME headers (`Importance`, read receipts) were expected to be set as custom headers.
  [#27](https://github.com/ozanozbeker/epistole/issues/27) closed that as a no.
  Both names are non-`x-`, so Graph raises on both, as it does on any other such custom header.
  Neither gets a v1 surface (ADR-0016).
  Custom headers themselves are supported through `.headers(mapping)` on the message, because a header is message content rather than provider configuration.
- A third-party transport (ADR-0006) that cannot carry part of a message raises `RejectedError` itself.
  There is no base-class hook to call.
- Every Graph request is JSON, as decided on #20 (ADR-0012).
  A MIME-built draft with attachments uploaded afterwards would shrink the gap.
  It is untested, and ADR-0012 records it as the reopener.
- A provider that rewrites the `Message-ID` Epistole set is not a contract break: ADR-0004 defines `SendResult.message_id` as the id of the submission Epistole made.
- ADR-0004's consequence that #17 "can add an unsupported-feature class" is closed: it does not.
- `docs/research/prior-art.md` still recommends both mechanisms.
  This ADR is the decision on that recommendation, not a correction of the research.

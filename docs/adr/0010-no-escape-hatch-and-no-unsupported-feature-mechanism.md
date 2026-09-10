# No escape hatch on the message or the send call, and no unsupported-feature mechanism

`docs/research/prior-art.md` names two things django-anymail needed to keep one API across fourteen providers: `esp_extra`, a dict passed through to the provider, and `unsupported_feature()`, which raises unless a setting silences it.
Epistole ships neither.
A setting only one mail service understands is a keyword argument on that backend's constructor, a message never carries one, and `send` takes the message alone.
A feature a backend cannot carry is refused before writing as `RejectedError` with `__cause__` `None`, the rule ADR-0004 already states, and nothing downgrades it to a warning.
Decided on [#17](https://github.com/ozanozbeker/epistole/issues/17).
Amended on [#27](https://github.com/ozanozbeker/epistole/issues/27): the custom-header consequence is discharged (ADR-0016).

## Why

**The three cases the issue cites were already settled.**
Graph's 3 MB attachment cliff is a send strategy and a permission question on [#20](https://github.com/ozanozbeker/epistole/issues/20), and a knowable ceiling is `RejectedError` under ADR-0004.
SMTP alone refusing some recipients is `SendResult.refused`, empty on the two APIs by contract (ADR-0004).
The from address belongs to the backend, and a service that will not send as it raises `SenderRefusedError` (ADR-0001).

**Almost nothing can be unsupported.**
Gmail takes the RFC 5322 bytes as `raw`.
Graph accepts the same bytes as `text/plain`, and this ADR first assumed its small path would use them.
[ADR-0012](0012-graph-sends-json-on-two-paths-chosen-by-size.md) chose JSON on every Graph request instead, so the gap is Graph at any size rather than its large path alone: custom headers must start with `x-`, and the caller's plain text next to HTML is replaced by Exchange's own, which ADR-0012 treats as degradation rather than refusal.
The count below is unchanged: three backends, one gap.
Anymail's mechanism serves fourteen providers and twelve optional message attributes; Epistole has three backends and one gap.
A method with one caller is a mechanism, not a design.

**The gap is a pre-check, not a new class.**
ADR-0004 rules that a limit Epistole can check before touching the wire is `RejectedError` with `__cause__` `None`, because the same message succeeds on another backend and the caller should see one class whether Epistole or the service noticed first.
A header the large path cannot carry is that case exactly, and the fix is on the message, so `RejectedError` is the right class and an eighth leaf would split one meaning across two names.

**No warning, no flag.**
ADR-0004 already rejected warnings because they are invisible in production logs.
An `ignore_unsupported` flag would be one configuration axis serving one pre-check, and a caller who wants the degraded send strips the header first.

**The message stays backend-agnostic.**
The glossary says a message never carries a backend, and #9 says nothing but the message goes on the send call.
`backend_extra` on either would contradict both for the sake of request-level knobs (Graph `saveToSentItems`, Gmail `threadId`) that are backend configuration, not message content.
Each backend is its own class, so those knobs are already keyword arguments with names and types instead of a dict the backend forwards blind.

## Consequences

- A backend constructor grows a keyword argument for each provider-only setting worth exposing, and it is typed and documented there.
  Anything not exposed is out of scope, and the caller drops to the provider's REST API.
- Per-message provider features that are MIME headers (`Importance`, read receipts) were expected to ride on custom headers.
  [#27](https://github.com/ozanozbeker/epistole/issues/27) closed that as a no: both names are non-`x-`, so both raise on Graph like any other custom header, and neither gets a v1 surface (ADR-0016).
  Custom headers themselves are in, as `.headers(mapping)` on the message, because a header is message content rather than provider configuration.
- A third-party transport (ADR-0006) that cannot carry part of a message raises `RejectedError` itself; there is no base-class hook to call.
- #20 decided that every Graph request is JSON (ADR-0012).
  A MIME-built draft with attachments uploaded afterwards would shrink the gap; it is untested and recorded there as the reopener.
- A provider that rewrites the stamped `Message-ID` is not a contract break: ADR-0004 defines `SendResult.message_id` as the id of the submission Epistole made.
- ADR-0004's consequence that #17 "can add an unsupported-feature leaf" is closed: it does not.
- `docs/research/prior-art.md` keeps recommending both mechanisms; this ADR is the answer to that recommendation, not a correction of the research.

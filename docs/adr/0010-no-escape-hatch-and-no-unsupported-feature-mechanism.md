# No escape hatch on the message or the send call, and no unsupported-feature mechanism

`docs/research/prior-art.md` names two things django-anymail needed to keep one API across fourteen providers: `esp_extra`, a dict passed through to the provider, and `unsupported_feature()`, which raises unless a setting silences it.
Herma ships neither.
A setting only one mail service understands is a keyword argument on that backend's constructor, a message never carries one, and `send` takes the message alone.
A feature a backend cannot carry is refused before writing as `RejectedError` with `__cause__` `None`, the rule ADR-0004 already states, and nothing downgrades it to a warning.
Decided on [#17](https://github.com/ozanozbeker/herma/issues/17).

## Why

**The three cases the issue cites were already settled.**
Graph's 3 MB attachment cliff is a send strategy and a permission question on [#20](https://github.com/ozanozbeker/herma/issues/20), and a knowable ceiling is `RejectedError` under ADR-0004.
SMTP alone refusing some recipients is `SendResult.refused`, empty on the two APIs by contract (ADR-0004).
The from address belongs to the backend, and a service that will not send as it raises `SenderRefusedError` (ADR-0001).

**Almost nothing can be unsupported.**
Gmail takes the RFC 5322 bytes as `raw`.
Graph takes the same bytes as `text/plain` on its small path.
So two of three backends carry everything the SMTP backend writes, headers included, and the message model never has to shrink to a JSON schema.
The one path that does is Graph's large path (#20), where a draft is built from JSON and custom headers must start with `x-`.
Anymail's mechanism serves fourteen providers and twelve optional message attributes; Herma has three backends and one gap.
A method with one caller is a mechanism, not a design.

**The gap is a pre-check, not a new class.**
ADR-0004 rules that a limit Herma can check before touching the wire is `RejectedError` with `__cause__` `None`, because the same message succeeds on another backend and the caller should see one class whether Herma or the service noticed first.
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
- Per-message provider features that are MIME headers (`Importance`, read receipts) ride on custom headers, which #2 still has to specify.
- A third-party transport (ADR-0006) that cannot carry part of a message raises `RejectedError` itself; there is no base-class hook to call.
- #20 decides how much of the large path is JSON.
  A MIME-built draft with attachments uploaded afterwards would shrink the gap further; whatever it leaves is the pre-check's job.
- A provider that rewrites the stamped `Message-ID` is not a contract break: ADR-0004 defines `SendResult.message_id` as the id of the submission Herma made.
- ADR-0004's consequence that #17 "can add an unsupported-feature leaf" is closed: it does not.
- `docs/research/prior-art.md` keeps recommending both mechanisms; this ADR is the answer to that recommendation, not a correction of the research.

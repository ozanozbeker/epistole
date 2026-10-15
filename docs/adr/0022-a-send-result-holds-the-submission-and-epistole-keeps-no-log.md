# A send result holds the submission, and Epistole keeps no log of sends

`SendResult.submission` holds the submission the transport received.
`Submission.as_bytes()` returns it as an RFC 5322 message, the bytes of an `.eml` file.
Epistole keeps no log, manifest or dedup store of what it sent.
A caller who must not send twice keeps their own, and `user_guide/orchestration.qmd` shows the pattern.
Decided on [#134](https://github.com/ozanozbeker/epistole/issues/134), which amends ADR-0004 and ADR-0015.

## Why

**The key is the caller's.**
A backfill must recognise "the same email again".
That identity is a report date, a partition key, or a customer and a month.
Epistole's `Message-ID` is new on every submission (ADR-0015), so it cannot be the key.

**The storage is the caller's.**
Dagster has materialization metadata, Prefect has artifacts, and a pipeline has its own tables.
A store inside Epistole would copy one of them.
It would also need a location, a lock and a retention policy, and only the caller's deployment fixes those.

**No store makes a send exactly-once.**
The service can accept a message, and the process can then die before the caller writes anything.
Writing first loses that email, and writing after sends it twice on the rerun.
Only the caller knows which costs more, so only the caller can choose the order.
The guide shows at-most-once by default, because a duplicate email to a customer usually does more harm than a held send that a person releases.

**The submission holds what an audit needs, and `.eml` is its file format.**
A send result already held the `Message-ID` and `Date`.
The submission adds the message, every recipient and the from address.
The field holds a reference to the caller's immutable message, not a copy.
`.eml` opens in any mail client and keeps the attachments.
`message_id` and `date` become properties that read the submission, so a send result holds each value once, as ADR-0015 requires.

## Rules

- `SendResult.submission` is required and never `None`.
  Only `Connection.send` builds a send result, so the change breaks no documented use.
- `as_bytes` returns bytes, not an `EmailMessage`, so `build`'s policy stays private and the value cannot be mutated.
  The name is the stdlib's `EmailMessage.as_bytes`.
- The bytes hold `Bcc`, because an audit copy names every recipient.
  A forwarded `.eml` shows the bcc list, and the docstring says so.
- The bytes are Epistole's rendering of the submission.
  `build` sets no MIME boundary, so the stdlib generator writes new ones on every call.
  SMTP sends the same rendering without `Bcc`.
  Gmail sends it, then replaces the `Message-ID` ([#68](https://github.com/ozanozbeker/epistole/issues/68)).
  Graph receives JSON built from the same submission (ADR-0012).
- A send that raises returns no submission.

## Considered options

- **A log inside Epistole, written by each send.**
  Rejected above: the key, the storage and the order belong to the caller.
- **`send(message, record=path)`, which writes the `.eml`.**
  It makes Epistole manage files, which is the storage concern above.
- **`Submission.as_email()`, returning an `EmailMessage`.**
  It exposes a mutable object and `build`'s policy choices.
  A caller who wants headers parses the bytes with `email.message_from_bytes`.
- **`as_bytes(bcc=...)`.**
  No caller asked for a copy without `Bcc`.
  A keyword with the default `True` can come later without a break.
- **`EpistoleError.submission`, set when a send fails after building one.**
  It would serve an audit of failed sends, and it changes the error model in ADR-0004.
  Nobody has asked for it yet.
- **A boundary derived from the `Message-ID`, so `as_bytes` returns the bytes sent.**
  It changes every message SMTP and Gmail send, and each nested multipart needs its own.
  Nobody has asked for byte-identical copies yet.
- **A default of `None` on `SendResult.submission`.**
  It would type the field `Submission | None` for a case that never happens.

## Consequences

- A caller can write `result.submission.as_bytes()` to storage after each send.
- A caller who builds a `SendResult` themselves, such as in a test fake, must now pass `refused` and `submission` only.
- `user_guide/orchestration.qmd` holds the only documentation of the pattern.
  Its Dagster section is a filename block, so `tests/test_examples.py` skips it and the `dev` group needs no `dagster`.

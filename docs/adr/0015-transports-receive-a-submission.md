# Transports receive a submission, and the test doubles record it

`Transport.submit` took a `Message` with `Message-ID` and `Date` set on a private copy.
It now takes a frozen `Submission(message, from_address, message_id, date)` and returns refusals alone.
So `Connection.send` builds every `SendResult` in one place.
`MemoryBackend.submissions` is a `list[Submission]` on the backend.
`ConsoleBackend` renders a submission rather than the bytes any one backend sends.
Decided on [#28](https://github.com/ozanozbeker/epistole/issues/28), which amends ADR-0002, ADR-0004, ADR-0005, ADR-0006, ADR-0007, and ADR-0008.
Amended on [#27](https://github.com/ozanozbeker/epistole/issues/27): the rendering includes the caller's custom headers, alongside the addressing (ADR-0016).
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30): `Message-ID` and `Date` get their generators, and `MemoryBackend` records a submission only when at least one recipient is accepted.
Amended on [#35](https://github.com/ozanozbeker/epistole/issues/35): a non-ASCII domain is IDNA-encoded before it is written into `message_id`.
Amended on [#42](https://github.com/ozanozbeker/epistole/issues/42): the rendering includes the from address, which the submission holds and the message does not. `ConsoleBackend` flushes the stream after each rendering.

## Why

**The double needed a from address the message does not have.**
A test asserting that a report went out as `reports@example.com` had nowhere to read it from.
A `Message` never holds a from address (ADR-0001).
The id and date Epistole set were on a copy no caller could reach.
Three shapes were considered: a bare `Message` with the headers set, which is the `outbox[0].to_` shape [#14](https://github.com/ozanozbeker/epistole/issues/14) fixed; nullable `message_id` and `date` fields on `Message`; or a record holding all of it.
The record was chosen because the first two leave the from address unreachable.
Keeping #14's assertion shape adds one word: `submissions[0].message.to_`.

**Making it core removes a contradiction instead of adding a type.**
ADR-0002 says submission identity is never on the value, then has `Connection.send` set it "on the copy it gives `Transport.submit`".
Both cannot be true.
The copy was the exception to the rule.
With a `Submission`, there is no copy with the headers set.
A `Message` is exactly what the caller built.
The record holds the identity.
The rule no longer contradicts itself.

**A double that records the real argument makes tests stronger.**
Had `Submission` stayed local to `MemoryBackend`, its record would hold a shape no real transport ever receives.
A passing test would then prove something about the double rather than about the send path.
Recording the same type `SMTPTransport` and `GraphTransport` receive makes the double faithful instead of merely convenient.

**The transport returns refusals, and the send result is built once.**
ADR-0006 put the code that sets `Message-ID` and `Date` in one place with a plain argument: "A third-party backend that forgot it would send mail with no `Message-ID`."
The same problem existed one step later.
Every transport constructed its own `SendResult`.
So a third-party author could return the wrong id or make one up, and no check would detect it.
Narrowing `submit` to return the refusals it received fixes that problem, on the ADR's own reasoning.
It also removes the duplication the record introduced.
`message_id` and `date` name the same two values in `Submission` and `SendResult`, but only ever one instance at a time.
The transport receives the submission, and the send result is built from it.

**The double takes `refuse=`, and nothing more general.**
The error model in ADR-0004 is a mapping from native exceptions to seven Epistole classes.
A double that raises `ThrottledError` on command tests that `raise` works, not that the mapping is right.
The mapping is testable only by passing the mapper real `SMTPDataError`s and real Graph status bodies.
That is a unit test on the mapper, not a fake backend.
A general injection hook would suggest coverage it does not provide.
Refusals are different in kind.
They are data returned on the same output channel a real SMTP transport uses.
ADR-0004's own consequences name them the one silent risk in the model: "A caller who ignores the send result loses SMTP refusals silently."
Without `refuse=`, the only way to produce a partial refusal is a live SMTP server configured to refuse one recipient of three.

**The console renders a submission, because the backends send no common format.**
SMTP and Gmail take the RFC 5322 bytes Epistole builds.
Graph takes JSON, and Exchange serializes the MIME later (ADR-0012).
Django's console backend writes RFC 5322 because Django sends exactly one format.
Writing it here would print SMTP's serialization to a user who sends through Graph.
That output would be wrong for a third of the backends.
The rest follows from size.
This audience works in notebooks.
ADR-0013 measured real reports past 100 KB.
Base64 expands attachments by 37 percent, so a 2 MB PDF becomes 2.7 MB of noise in an output cell that is then saved into the `.ipynb`.
Plain text is the one part a human reads to check the message is right.
ADR-0008 already chose a real extractor for it.
So plain text prints in full, and everything bulky prints as a size.

**The attribute is `submissions`, not `outbox`.**
In every mail client this audience uses, Outbox holds messages that have not been sent, and Sent Items holds messages that have.
This list holds accepted submissions, so the inherited Django name suggests the reverse of what the list holds.
It never caused problems in Django because Django only ever reads it.
#14 rejected `Receipt` on exactly this ground: it read as the one thing it must not imply.
The same test rules out `outbox` here.
The entries are `Submission` values, so the attribute name matches the type, as `SendResult.refused` holds `Refusal`s.

## Rules

- **`Submission` is frozen and has four fields.**
  They are `message`, `from_address`, `message_id`, and `date`.
  It has no `refused`, because refusals do not exist until the transport returns.
- **`Message-ID` and `Date` have one generator each.**
  `message_id` is `email.utils.make_msgid(domain=...)`, with the domain taken from the addr-spec of the backend's from address.
  It keeps its angle brackets, so the value reads the same in a log, in the header, and in Graph's `internetMessageId`.
  The domain comes from the from address rather than from `make_msgid`'s default.
  That default resolves through `socket.getfqdn()` and would put the sending machine's internal hostname in every message a scheduled job sends.
  A non-ASCII domain is IDNA-encoded before Epistole writes it into the `Message-ID`, because RFC 5322 requires a `msg-id` in ASCII.
  `EmailMessage.as_bytes()` raises `UnicodeEncodeError` on anything else.
  That error is not an `EpistoleError` and appears in no mapping table (ADR-0004).
  The encoding is safe to apply unconditionally.
  A `Message-ID` is an identifier and not a route, so nothing resolves the domain.
  The domain only has to be stable and legal.
  For the same reason, the stdlib codec's IDNA 2003 folding does not matter.
  That folding turns `straße.de` into `strasse.de` rather than IDNA 2008's `xn--strae-oqa.de`.
  ADR-0014 is unchanged: it covers what Epistole checks, and this ADR covers what Epistole sets.
  `date` is `email.utils.localtime()`: timezone-aware, with the sending machine's offset.
  A mail client writes the same, and a recipient reading a timestamp expects it.
- **`Transport` is `submit(submission, /) -> Mapping[str, Refusal]` and `close() -> None`.**
  The argument is positional-only, as ADR-0006 requires.
  For an accepted submission with nothing refused, the transport returns an empty mapping.
- **`Connection.send` builds both records.**
  It checks the message, builds the `Submission`, calls `submit`, then constructs the `SendResult` from the submission's `message_id` and `date` plus the returned mapping.
  A transport never constructs a `SendResult`.
- **`Connection.send` alone raises `RecipientsRefusedError` when every recipient is refused.**
  A transport returns refusals and never raises it, `SMTPTransport` included.
  It catches `SMTPRecipientsRefused` and returns its `.recipients` as data.
  The rule moved here so that it holds on every backend, including the doubles (ADR-0004).
- **`MemoryBackend.submissions` is a live `list[Submission]`.**
  It is an attribute of the backend and persists across every connection the backend opens (ADR-0005).
  There is no reset method.
  `list.clear()` already exists, and a fresh backend per test starts empty.
  It is the one mutable thing a backend holds.
  `list.append` is atomic under both the GIL and a free-threaded build, so the list cannot be corrupted.
  Concurrency affects order only: entries are appended in submit-completion order rather than call order.
  A test that asserts on order sends from one thread.
- **`MemoryBackend` records a submission only when at least one recipient is accepted.**
  `refuse` is applied first.
  A submission with every recipient refused is not appended.
  Otherwise the double would hold a record of a send that raised `RecipientsRefusedError`, which means nothing was submitted.
  `CONTEXT.md`'s "keeps every one it accepted" would then be false on the one backend a test can inspect.
- **`MemoryBackend(from_address=..., refuse=...)`.**
  `refuse` maps an address to a `Refusal`, matched against each recipient's addr-spec.
  It is applied at submit.
  Nothing else is injectable.
- **`ConsoleBackend(from_address=..., stream=None)`.**
  `None` means `sys.stdout` looked up at write time, never captured in `__init__`.
  pytest's `capsys` and Jupyter both replace it after import, and an eagerly bound stream writes somewhere the test does not capture.
- **`ConsoleBackend` writes a rendering, not bytes.**
  The rendering holds the from address, the addressing, custom headers, `Message-ID`, `Date`, subject, and the plain text in full.
  It has one line per attachment and inline image, with name, content type and size.
  It shows the HTML as a size line alone.
  It flushes the stream after each rendering, as Django's console backend and `logging.StreamHandler` do, so a pipe or a file holds the rendering when the send returns.
- **Both doubles default the from address and take no credential.**
  The default is `epistole@example.invalid`, reserved by RFC 2606 and passing the ADR-0014 shape check.
  On a double, the from address carries no information, because there is no mail service to authorize it.
  ADR-0011 puts credentials in each backend's own module.
  Neither double authenticates to a mail service.
- **`Submission` and `Refusal` are exported from `epistole`.**
  `refuse=` cannot be written without `Refusal`.
  The concrete transports are still not exported (ADR-0006).

## Considered options

- **Use a bare `Message` with the headers set as the record.**
  It keeps #14's `outbox[0].to_` exactly.
  Rejected because the from address, `Message-ID` and `Date` stay unreachable from the record, and the from address is the fact a test most needs.
- **Add nullable `message_id` and `date` to `Message`.**
  It keeps the short assertion and adds one attribute.
  Rejected because it puts two almost-always-`None` fields on the public value type and forces `__eq__` to exclude them, to save one word per assertion.
- **Keep `Submission` local to `MemoryBackend`.**
  It leaves ADR-0006 unchanged and is the cheapest change.
  Rejected above: the record would be a shape invented for tests.
- **`submit` keeps returning `SendResult`.**
  Rejected above: it leaves every transport author able to get the id wrong.
- **Add a general `on_submit` hook that may raise anything.**
  Rejected above: it cannot test the mapping it appears to test.
- **Print RFC 5322 bytes on the console, as Django does.**
  It is faithful to SMTP, wrong for Graph, and unusable in a notebook.
- **Name it `outbox`.**
  The Django audience [#6](https://github.com/ozanozbeker/epistole/issues/6) aimed at would recognise it instantly.
  Rejected above: the glossary entry would have to explain that the word means the reverse of its meaning in the reader's mail client.
- **Expose a read-only `tuple` view plus `clear()`.**
  It is consistent with a surface where every other value is frozen.
  Rejected because the entries are frozen either way, `list.clear()` already exists, and a tuple rebuilt per access copies on every `len()`.

## Consequences

- ADR-0002 loses the copy with the headers set.
  Its rule "Submission identity is never on the value" now holds without qualification.
  `Connection.send` builds a record instead of copying a message.
- ADR-0006's `Transport` signature changes on both counts, argument and return.
  A third-party transport author reads one indirection deeper, at `submission.message`.
  The author gets `submission.from_address` instead of closing over it at `_open()`.
- ADR-0004 keeps its shape.
  `SendResult` still has three fields and still holds refusals.
  Only the construction site moves.
  `Refusal` becomes part of the public surface because `refuse=` takes one.
- ADR-0007's attributes still work one level deeper, as `submissions[0].message.to_`.
  That is still the only place the trailing underscore is typed.
- ADR-0008's `outbox[0].text` becomes `submissions[0].message.text`.
- ADR-0005's line about the outbox being on the backend holds unchanged, under the new name.
- A test can now assert on the from address, which no shape before this could express.
- A `refuse=` entry makes `MemoryBackend` do something only SMTP does.
  The docstring says so, as ADR-0004 already requires of `SendResult.refused`.
- The console rendering is not a format any backend sends.
  Nothing should parse it.
  A user who wants bytes writes a `Transport`.
  ADR-0006 already says a third-party backend writes a transport and nothing else.

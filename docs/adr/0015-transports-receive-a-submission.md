# Transports receive a submission, and the test doubles record it

`Transport.submit` took a `Message` with `Message-ID` and `Date` stamped onto a private copy.
It now takes a frozen `Submission(message, from_address, message_id, date)` and returns refusals alone, so `Connection.send` builds every `SendResult` in one place.
`MemoryBackend.submissions` is a `list[Submission]` on the backend, and `ConsoleBackend` renders a submission rather than any one backend's wire bytes.
Decided on [#28](https://github.com/ozanozbeker/epistole/issues/28), which amends ADR-0002, ADR-0004, ADR-0005, ADR-0006, ADR-0007, and ADR-0008.

## Why

**The double needed a from address the message does not have.**
A test asserting that a report went out as `reports@example.com` had nowhere to read it from.
A `Message` never carries a from address (ADR-0001), and the stamped id and date lived on a copy no caller could reach.
Three shapes were on the table: a bare stamped `Message`, which is the `outbox[0].to_` shape [#14](https://github.com/ozanozbeker/epistole/issues/14) fixed; nullable `message_id` and `date` fields on `Message`; or a record holding all of it.
The record won because the first two leave the from address unreachable at any price, and #14's assertion shape costs one word to keep as `submissions[0].message.to_`.

**Making it core removes a contradiction instead of adding a type.**
ADR-0002 says submission identity is never on the value, then has `Connection.send` stamp it "on the copy it gives `Transport.submit`".
Both cannot be true, and the copy was the seam where the rule leaked.
With a `Submission` there is no stamped copy: a `Message` is exactly what the caller built, and the record carries the identity.
The rule stops arguing with itself.

**A double that records the real argument proves more.**
Had `Submission` stayed local to `MemoryBackend`, its record would hold a shape no real transport ever sees, and a passing test would prove something about the double rather than about the send path.
Recording the same type `SMTPTransport` and `GraphTransport` receive is what makes the double faithful instead of merely convenient.

**Refusals return, and the send result is built once.**
ADR-0006 gave stamping one home with a plain argument: "A third-party backend that forgot it would send mail with no `Message-ID`."
The same hole was open one step later.
Every transport constructed its own `SendResult`, so a third-party author could echo the wrong id or invent one, and nothing would catch it.
Narrowing `submit` to return the refusals it learned closes that hole with the ADR's own reasoning, and it removes the duplication the record introduced: `message_id` and `date` name the same two values in `Submission` and `SendResult`, but only ever one instance at a time.
The submission dies at the wire and the send result is born from it.

**`refuse=` on the double, and nothing more general.**
The error model in ADR-0004 is a mapping from native exceptions to seven Epistole classes.
A double that raises `ThrottledError` on command tests that `raise` works, not that the mapping is right; the mapping is testable only by feeding the mapper real `SMTPDataError`s and real Graph status bodies, which is a unit test on the mapper and not a fake backend.
A general injection hook would sell confidence it cannot deliver.
Refusals are different in kind.
They are data returned on the same output channel a real SMTP transport uses, and ADR-0004's own consequences name them the one silent footgun in the model: "A caller who ignores the send result loses SMTP refusals silently."
Without `refuse=`, the only way to produce a partial refusal is a live SMTP server willing to refuse one recipient of three.

**The console renders, because there is no universal wire form.**
SMTP and Gmail take the RFC 5322 bytes Epistole builds; Graph takes JSON and Exchange serializes the MIME later (ADR-0012).
Django's console backend dumps RFC 5322 because Django has exactly one wire form to be faithful to.
Dumping it here would print SMTP's serialization to a user who ships through Graph, which is a lie about a third of the backends.
Size decides the rest.
This audience works in notebooks, ADR-0013 measured real reports past 100 KB, and base64 expands attachments by 37 percent, so a 2 MB PDF becomes 2.7 MB of noise in an output cell that then gets saved into the `.ipynb`.
Plain text is the one part a human reads to check the mail is right, and ADR-0008 already put a real extractor behind it, so plain text prints in full and everything bulky prints as a size.

**`submissions`, not `outbox`.**
In every mail client this audience uses, Outbox holds mail that has not gone and Sent Items holds mail that has.
This list holds accepted submissions, so the inherited Django name means the reverse of what it says.
It never bit Django because Django only ever reads it.
#14 rejected `Receipt` on exactly this ground, that it read as the one thing it must not claim, and the same test rules out `outbox` here.
The entries are `Submission` values, so the attribute and the type agree, as `SendResult.refused` holds `Refusal`s.

## Rules

- **`Submission` is frozen and has four fields.**
  `message`, `from_address`, `message_id`, `date`.
  No `refused`: it does not exist until the transport answers.
- **`Transport` is `submit(submission, /) -> Mapping[str, Refusal]` and `close() -> None`.**
  Positional-only as ADR-0006 requires.
  An accepted submission with nothing refused returns an empty mapping.
- **`Connection.send` builds both records.**
  It checks the message, builds the `Submission`, calls `submit`, then constructs the `SendResult` from the submission's `message_id` and `date` plus the returned mapping.
  A transport never constructs a `SendResult`.
- **Every recipient refused raises `RecipientsRefusedError`.**
  Unchanged from ADR-0004, but the rule lives in `Connection.send`, so it holds on every backend including the doubles.
- **`MemoryBackend.submissions` is a live `list[Submission]`.**
  On the backend, in send order, surviving every connection the backend opens (ADR-0005).
  No reset method: `list.clear()` already exists, and a fresh backend per test starts empty.
- **`MemoryBackend(from_address=..., refuse=...)`.**
  `refuse` maps an address to a `Refusal` and is applied at submit.
  Nothing else is injectable.
- **`ConsoleBackend(from_address=..., stream=None)`.**
  `None` means `sys.stdout` looked up at write time, never captured in `__init__`, because pytest's `capsys` and Jupyter both swap it after import and an eagerly bound stream writes where the test cannot see.
- **`ConsoleBackend` writes a rendering, not bytes.**
  Addressing, `Message-ID`, `Date`, subject, the plain text in full, one line per attachment and inline image carrying name, content type and size, and HTML as a size line alone.
- **Both doubles default the from address and take no credential.**
  The default is `epistole@example.invalid`, reserved by RFC 2606 and passing the ADR-0014 shape check.
  On a double the from address carries no information, because there is no mail service to authorize it.
  ADR-0011 puts credentials in each backend's own module, and neither double has anything to prove.
- **`Submission` and `Refusal` are exported from `epistole`.**
  `refuse=` cannot be written without `Refusal`.
  The concrete transports are still not exported (ADR-0006).

## Considered options

- **A bare stamped `Message` as the record.**
  Keeps #14's `outbox[0].to_` exactly.
  Rejected because the from address and the stamps stay unreachable from the record, and the from address is the fact a test most wants.
- **Nullable `message_id` and `date` on `Message`.**
  Keeps the short assertion and adds one attribute.
  Rejected because it puts two almost-always-`None` fields on the public value type and forces `__eq__` to exclude them, to save one word per assertion.
- **`Submission` local to `MemoryBackend`.**
  Leaves ADR-0006 frozen and is the cheapest change.
  Rejected above: the record would be a shape invented for tests.
- **`submit` keeps returning `SendResult`.**
  Rejected above; it leaves every transport author able to get the id wrong.
- **A general `on_submit` hook that may raise anything.**
  Rejected above; it cannot test the mapping it appears to test.
- **RFC 5322 bytes on the console, as Django.**
  Faithful to SMTP, wrong for Graph, and hostile in a notebook.
- **`outbox`.**
  Recognised instantly by the Django audience [#6](https://github.com/ozanozbeker/epistole/issues/6) aimed at.
  Rejected above; the glossary entry would have to explain that the word means the reverse of what the reader's mail client says.
- **A read-only `tuple` view plus `clear()`.**
  Consistent with a surface where every other value is frozen.
  Rejected because the entries are frozen either way, `list.clear()` already exists, and a tuple rebuilt per access copies on every `len()`.

## Consequences

- ADR-0002 loses the stamped copy.
  Its rule "Submission identity is never on the value" now holds without qualification, and `Connection.send` builds a record instead of copying a message.
- ADR-0006's `Transport` signature changes on both counts, argument and return.
  A third-party transport author reads one indirection deeper, `submission.message`, and gains `submission.from_address` instead of closing over it at `_open()`.
- ADR-0004 keeps its shape.
  `SendResult` still has three fields and still carries refusals; only the construction site moves.
  `Refusal` becomes part of the public surface because `refuse=` takes one.
- ADR-0007's readbacks survive one hop deeper, `submissions[0].message.to_`, and that is still the only place the trailing underscore is typed.
- ADR-0008's `outbox[0].text` becomes `submissions[0].message.text`.
- ADR-0005's line about the outbox living on the backend holds unchanged, under the new name.
- A test can now assert on the from address, which no shape before this could express.
- A `refuse=` entry makes `MemoryBackend` do something only SMTP does.
  The docstring says so, as ADR-0004 already requires of `SendResult.refused`.
- The console rendering is not a wire format and nothing should parse it.
  A user who wants bytes writes a `Transport`, which ADR-0006 already calls the whole of what a third-party backend writes.

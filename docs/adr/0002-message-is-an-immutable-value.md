# Message is an immutable value that copies on write

No Python email library chains, and the two that come closest mutate while doing it.
Epistole chains anyway, and every builder method returns a new `Message` instead of `self`.
A `Message` is a closed value: nothing it holds changes, nothing it holds is read later, and nothing can be removed from it.
Decided on [#10](https://github.com/ozanozbeker/epistole/issues/10), building on the prototype verdict in [#8](https://github.com/ozanozbeker/epistole/issues/8).

## Why

The loop Epistole exists for is one composed body sent to many recipients over one connection:

```python
report = Message(html=html).subject("Weekly numbers").attach(pdf)

with smtp.connect() as connection:
    for subscriber in subscribers:
        connection.send(report.to(subscriber.email))
```

Under a `return self` builder that loop leaks.
`.to()` accumulates, subscriber 200 receives a `To` header naming all 200 addresses, and every earlier subscriber already received everyone ahead of them.
Nothing raises, and the code reads exactly like the version that works. blastula chains safely only because R copies values on modify.
Porting the look without the semantics imports a bug R does not have, so chaining stays only because copy on write makes it safe.

## Rules

- **A method named for a field replaces it.
  A method named with a verb of addition appends.**
  `.to("a").to("b")` sends to `b`; `.attach(x).attach(y)` sends both; `.attach(x).attach(x)` sends `x` twice, because that is what was written.
  Replace won over append for recipients because the silent-drop mistake shows up in the sent mail and the silent-leak mistake does not.
  The class docstring states the rule, and each replacing method says so in one sentence.
- **Nothing removes.**
  Address methods take at least one address, `to(address, /, *more)`, so `.to(*[])` is a `TypeError` at the call site rather than a message with an empty `To`.
  There is no way to drop an attachment.
  A base without something is built without it.
- **Closed value.**
  `.attach(Path(...))` reads the file when called, an open file object is read when passed and left open for the caller, and address lists become tuples.
  A message sent twice sends the same bytes twice, and a missing file fails at the line that named it.
- **Content enters only through the constructor, as `html=`, `markdown=`, or `text=` (ADR-0008), and preparation runs there.**
  Subject, recipients, reply-to, and attachments arrive only through methods, so each field has one spelling.
  Plain-text derivation and the rewrite of `data:` images into inline images happen in `Message(...)` whenever the content is HTML, so every copy shares the result and the loop above derives nothing per subscriber.
  `Connection.send` checks addressing and `cid:` references, stamps submission identity, and hands off to the transport.
  The derived text and the rewritten HTML are readable the moment the object exists.
- **Submission identity is never on the value.**
  `Message-ID` and `Date` describe one submission, not the content.
  `Connection.send` stamps them on the copy it gives `Transport.submit`, and the send result carries the id back.
  One message sent twice is two submissions with two ids.
- **Equal by content, hashable.**
  The plain-text renderer runs at construction and is not stored, so two messages built the same way compare equal whatever callable produced their text.

## Considered options

- **Mutable, Django shaped.**
  A constructor plus a mutating `attach`.
  Familiar, and it is what every Python library does.
  Rejected on the loop above: the natural way to reuse a template is wrong, silently.
- **Frozen value without chaining.**
  `Message(html=..., subject=...)` plus `copy.replace(report, to=(x,))` from the 3.13 stdlib.
  Same safety, no invented API.
  Rejected because appending an attachment becomes `replace(m, attachments=(*m.attachments, new))`, and `to=("a",)` reopens the bug where a bare string iterates into single-character recipients, which varargs on `.to()` close for free.
- **Constructor accepts every field.**
  Rejected because it gives each field two spellings, and the keyword name `to` would differ from whatever [#14](https://github.com/ozanozbeker/epistole/issues/14) names the readback.
- **Lazy preparation inside `send`, as [#9](https://github.com/ozanozbeker/epistole/issues/9) first wrote it.**
  Copy on write means `send` cannot write derived text back to the caller's message, so the loop would derive once per subscriber.
  A public idempotent `prepare()` fixes the cost but adds a second state to one type.
  Eager preparation removes the state.

## Consequences

- One shallow copy per builder step.
  Attachments and derived text are shared by reference between copies, so the copy is cheap.
- A Django reader expects `.attach()` to mutate, and it does not.
  The return value must be used, and the docstrings say so.
- `MemoryBackend` needs no deep copy on the way into its outbox, because nothing can change a stored message afterwards.
  Django's locmem backend deep-copies for exactly that reason.
- The constructor does work and can raise.
  A renderer error or a malformed `data:` URI surfaces at the line that supplied the HTML.
- The split from [#9](https://github.com/ozanozbeker/epistole/issues/9) survives with one line moved: backends never re-derive, and neither does `send`.
- [#11](https://github.com/ozanozbeker/epistole/issues/11) inherits attach-time reads and the construction-time `data:` rewrite.
  [#12](https://github.com/ozanozbeker/epistole/issues/12) inherits the per-send `Message-ID`.
  [#14](https://github.com/ozanozbeker/epistole/issues/14) still owns the readback names once `.to()` has taken the attribute.
  [#15](https://github.com/ozanozbeker/epistole/issues/15) inherits a renderer that runs once, at construction.

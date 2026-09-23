# `Message` is an immutable value, and each builder method returns a copy

No Python email library chains.
The two that come closest mutate while doing it.
Epistole chains anyway.
Every builder method returns a new `Message` instead of `self`.
A `Message` is a closed value: nothing it holds changes, nothing it holds is read later, and nothing can be removed from it.
Decided on [#10](https://github.com/ozanozbeker/epistole/issues/10), based on the prototype's conclusion in [#8](https://github.com/ozanozbeker/epistole/issues/8).
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): `Connection.send` builds a `Submission` that carries the identity, in place of a copy with the identity set (ADR-0015).
Amended on [#27](https://github.com/ozanozbeker/epistole/issues/27): `.headers(mapping)` is now one of the field-named methods that replace.
It follows the same at-least-one rule as the address methods (ADR-0016).

## Why

Epistole exists for a loop that sends one built message to many recipients over one connection:

```python
report = Message(html=html).subject("Weekly numbers").attach(pdf)

with smtp.connect() as connection:
    for subscriber in subscribers:
        connection.send(report.to(subscriber.email))
```

Under a `return self` builder, that loop leaks.
`.to()` accumulates.
Subscriber 200 receives a `To` header naming all 200 addresses.
Every earlier subscriber has already received the addresses of everyone ahead of them.
Nothing raises.
The code reads exactly like the version that works.
blastula chains safely only because R copies values on modify.
Porting the syntax without the semantics adds a bug that R does not have.
So Epistole keeps chaining only because copy on write makes it safe.

## Rules

- **A method named for a field replaces it.
  A method named with a verb of addition appends.**
  `.to("a").to("b")` sends to `b`.
  `.attach(x).attach(y)` sends both.
  `.attach(x).attach(x)` sends `x` twice, because the caller wrote it twice.
  Recipient methods replace rather than append, because the silent-drop mistake is visible in the sent mail and the silent-leak mistake is not.
  The class docstring states the rule.
  Each replacing method's docstring says so in one sentence.
- **Nothing removes.**
  Address methods take at least one address: `to(address, /, *more)`.
  So `.to(*[])` is a `TypeError` at the call site rather than a message with an empty `To`.
  No method drops an attachment.
  To leave something out, the caller builds the base without it.
- **A message is a closed value.**
  `.attach(Path(...))` reads the file when called.
  `.attach()` reads an open file object when passed, and leaves it open for the caller.
  Address lists become tuples.
  Sending a message twice sends the same bytes twice.
  A missing file raises at the line that named it.
- **Content enters only through the constructor, as `html=`, `markdown=`, or `text=` (ADR-0008).
  Preparation runs there too.**
  Only methods set the subject, recipients, reply-to, attachments, and custom headers, so each field has one spelling.
  Whenever the content is HTML, `Message(...)` derives the plain text and rewrites `data:` images into inline images.
  Every copy shares the result, so the loop above derives nothing per subscriber.
  `Connection.send` checks addressing and `cid:` references, then builds the submission it passes to the transport (ADR-0015).
  The derived text and the rewritten HTML are readable the moment the object exists.
- **Submission identity is never on the value.**
  `Message-ID` and `Date` describe one submission, not the content.
  `Connection.send` sets them on the `Submission` it passes to `Transport.submit`, never on the message.
  `send` returns the id in the send result (ADR-0015).
  One message sent twice is two submissions with two ids.
- **A message compares equal by content and is hashable.**
  The plain-text renderer runs at construction and is not stored.
  So two messages built the same way compare equal, whatever callable produced their text.

## Considered options

- **Make `Message` mutable, as Django does.**
  The API is a constructor plus a mutating `attach`.
  It is familiar.
  Every Python library does it.
  Rejected because of the loop above: the natural way to reuse a template is silently wrong.
- **Use a frozen value without chaining.**
  The API is `Message(html=..., subject=...)` plus `copy.replace(report, to=(x,))` from the 3.13 stdlib.
  It is as safe, and needs no invented API.
  Rejected because appending an attachment becomes `replace(m, attachments=(*m.attachments, new))`.
  A `to=("a",)` keyword also reintroduces the bug where a bare string iterates into single-character recipients.
  Varargs on `.to()` prevent that bug with no extra code.
- **Constructor accepts every field.**
  Rejected because it gives each field two spellings.
  The keyword name `to` would also differ from whatever [#14](https://github.com/ozanozbeker/epistole/issues/14) names the attribute.
- **Prepare lazily inside `send`, as [#9](https://github.com/ozanozbeker/epistole/issues/9) first wrote it.**
  Copy on write means `send` cannot write derived text back to the caller's message, so the loop would derive once per subscriber.
  A public idempotent `prepare()` removes the repeated derivation but adds a second state to one type.
  Eager preparation removes the state.

## Consequences

- Each builder step makes one shallow copy.
  Copies share attachments and derived text by reference, so the copy is cheap.
- A Django reader expects `.attach()` to mutate, and it does not.
  The caller must use the return value.
  The docstrings say so.
- `MemoryBackend` needs no deep copy when it adds to `submissions`, because nothing can change a stored message afterwards.
  Django's locmem backend deep-copies for exactly that reason.
- The constructor does work and can raise.
  It raises on a renderer error or a malformed `data:` URI, at the line that supplied the HTML.
- The split from [#9](https://github.com/ozanozbeker/epistole/issues/9) stays, with one change: backends never re-derive, and neither does `send`.
- [#11](https://github.com/ozanozbeker/epistole/issues/11) takes attach-time reads and the construction-time `data:` rewrite as given.
  [#12](https://github.com/ozanozbeker/epistole/issues/12) takes the per-send `Message-ID` as given.
  [#14](https://github.com/ozanozbeker/epistole/issues/14) still chooses the attribute names, because the method `.to()` already uses `to`.
  [#15](https://github.com/ozanozbeker/epistole/issues/15) takes as given a renderer that runs once, at construction.

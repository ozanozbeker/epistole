# Custom headers are a mapping on the message, and Graph accepts only `x-` names

A `Message` holds custom headers.
`.headers(mapping)` replaces the whole set.
`headers_` reads it back.
A name Epistole already writes is a `ValueError`.
SMTP and Gmail carry any legal header.
Graph carries only names starting with `x-`.
Any other name fails a `RejectedError` pre-check at every size.
`Importance` and read receipts get no v1 surface.
Decided on [#27](https://github.com/ozanozbeker/epistole/issues/27), which closes an open consequence of ADR-0010 and makes ADR-0012's pre-check concrete.
Amended on [#40](https://github.com/ozanozbeker/epistole/issues/40): two names that differ only in case are a `ValueError`, as is a value holding any character `str.splitlines()` splits on.
Amended on [#42](https://github.com/ozanozbeker/epistole/issues/42): `.subject()` raises `ValueError` on a line break, by the rule a custom header value follows.

## Why

**A header is message content, not provider configuration, so ADR-0010 does not apply here.**
ADR-0010 rejected `backend_extra` because it was a dict of provider settings the message forwarded unchecked.
It rejected `unsupported_feature()` because one gap does not need a mechanism.
A custom header is a different thing.
RFC 5322 defines it, and all three backends model it.
The recipient's client reads it.
So ADR-0010's rule for a setting only one mail service supports does not apply to it.
What the message holds has a defined meaning, and no backend is named anywhere in it.
The settings ADR-0010 moved to backend constructors, Graph's `saveToSentItems` and Gmail's `threadId`, never appear in the sent message at all.
That is the difference between the two.

**One method replaces the whole set, because the API already has that rule.**
`.to(address, /, *more)` replaces (ADR-0002).
`.headers(mapping)` follows the same replace rule with the same shape.
It needs no amendment.
The alternative was `.header(name, value)` with a keyed replace.
That is a third semantic the API does not have today.
It would have made `headers_` the first exception to ADR-0007's mechanical rule.
Callers already hold a dict, since headers are a mapping everywhere else in Python's mail stack.
So the mapping form takes the value they have.

**Passing an empty mapping raises, so no method removes anything here either.**
`.headers({})` is a `ValueError`.
This looks like an inconsistency, but `.to()` cannot be called empty for the same reason.
Address methods take `(address, /, *more)`, so `.to(*[])` fails at the call site.
Under both rules, a base without something is built without it.
Neither method removes anything.

**A `Mapping` cannot hold an exact repeat, and `Message` raises on a repeat in another case.**
RFC 5322 allows a few field names to repeat, `Received` and `Comments` among them.
A mapping cannot express that, and nothing in v1 needs it.
Relays write `Received` in transit, not at submission.
Reading messages is out of scope for this map.
The type cannot hold an exact repeat.
It can hold one name in two cases, as `{"X-Id": "1", "x-id": "2"}` does.
RFC 5322 names are case-insensitive, so that is a repeat.
A backend would write a line for each spelling.
So `Message` raises `ValueError` on it.

**Both checks run in the message, and the newline check is a security rule.**
Python's stdlib already raises on the malformed cases, tested on 3.13:

```
"X-A", "a\r\nBcc: eve@example.com"  ->  ValueError  Header values may not contain linefeed or carriage return characters
"X:D", "1"                          ->  ValueError  Header field name contains invalid characters: 'X:D'
"X-Café", "1"                       ->  ValueError  Header field name contains invalid characters: 'X-Café'
"X-C", "café"                       ->  b'X-C: =?utf-8?q?caf=C3=A9?=\n'
```

Relying on that would cover only two backends out of three.
Graph never builds an `EmailMessage`, because ADR-0012 sends JSON.
A value holding `\r\n` would be sent as a JSON string, and Exchange would write the lines it spells out.
That is header injection.
The caller who supplied a user-controlled campaign id would have shipped it.
So `Message` runs the check itself, once, for every backend, at the line that named the header.

**Epistole's own names are a caller mistake, not an override.**
There is no reading of `.headers({"Subject": "Q3"})` where the caller does not mean `.subject("Q3")`.
ADR-0004 classes a caller mistake found before writing as `ValueError`.
Letting the caller's value take precedence would be worse than it sounds for two names.
`Message-ID` and `Date` describe a submission and are set on the `Submission`, not the `Message` (ADR-0015).
So a caller-set `Message-ID` would have to override a value that does not exist yet.
`SendResult.message_id` would then report an id Epistole did not set, which contradicts ADR-0004.
Silently dropping the caller's header is the third option.
ADR-0010 already banned the silent drop.
The match is case-insensitive because RFC 5322 field names are.
It is an exact name match rather than a prefix, so `In-Reply-To` stays legal next to an owned `Reply-To`.

**Graph's rule is inherited, and the two features that motivated this ticket close as a no.**
Microsoft documents the naming rule on the `message` resource: "Add custom headers only when creating a message, and name them starting with 'x-'."
ADR-0012 already chose JSON on every Graph request and recorded the pre-check.
This ADR only makes it concrete.
ADR-0010 left a consequence saying `Importance` and read receipts would be set as custom headers once headers were specified.
They are not.
Both are non-`x-`, so Graph raises on both.
Graph represents those meanings as first-class JSON properties instead (`importance`, `isReadReceiptRequested`).

Two ways to close that gap were considered and rejected under Considered options.
Neither fixes the header a newsletter actually needs.
`List-Unsubscribe` does not translate to any Graph property.
So Graph raises either way on the case users most want this feature for.

## Rules

- **`.headers(mapping, /)` replaces the whole set and returns a new message.**
  It takes a `Mapping[str, str]` and copies it at the call, so later changes to the caller's dict do not affect the message.
  `.headers({})` raises `ValueError`.
- **`headers_` reads the set back**, as a `MappingProxyType` in the order it was given, so `submissions[0].message.headers_ == {"X-Campaign-Id": "autumn"}` holds in a test (ADR-0007, ADR-0015).
  It holds the caller's headers alone and never the ones Epistole writes.
- **The set is stored as a tuple of pairs.**
  A `Message` is hashable and equal by content (ADR-0002), which a dict field would break.
  Address lists already become tuples for the same reason.
- **A legal name is one or more characters from printable ASCII 33 to 126, excluding colon.**
  This is RFC 5322 `ftext`.
  Anything else is a `ValueError`, including an empty name.
- **A legal value is a `str` holding no line break.**
  A line break is any character `str.splitlines()` splits on: `\r`, `\n`, `\v`, `\f`, `\x1c`, `\x1d`, `\x1e`, `\x85`, `\u2028`, and `\u2029`.
  `EmailMessage` raises on a value that `str.splitlines()` splits, tested on 3.13.12.
  A check on `\r` and `\n` alone would pass `\u2028`, and SMTP and Gmail would then raise at send time instead of at `.headers()`.
  Anything else is a `ValueError`.
  The character set is not otherwise checked, matching ADR-0014.
  The stdlib RFC 2047-encodes a non-ASCII value on the SMTP and Gmail paths, and Graph sends it as UTF-8 in JSON.
- **A subject takes the same line-break check, in `.subject()`.**
  `EmailMessage` raises on it at send time on SMTP and Gmail, and `ConsoleBackend` would write the rest as a separate line.
  Checking in `Message` raises at the line that set the subject, on every backend.
- **A name Epistole owns is a `ValueError`**, matched case-insensitively against the exact name: `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject`, `Message-ID`, `Date`, `MIME-Version`, `Content-Type`, `Content-Transfer-Encoding`, `Content-ID`, `Content-Disposition`.
- **Two names that differ only in case are a `ValueError`.**
  A `dict` holds both, and RFC 5322 names are case-insensitive.
- **Every check runs in `Message`**, so it fails at the line that named the header, on every backend (ADR-0002).
- **SMTP and Gmail write every custom header**, after the ones Epistole writes, in the caller's order.
- **`GraphTransport` rejects a name that does not start with `x-`**, case-insensitive, with `RejectedError` and `__cause__` `None`.
  The check runs before it writes, on both the `sendMail` path and the draft path (ADR-0004, ADR-0012).
  The error names the offending header.
- **Epistole caps neither the count nor the total size of custom headers.**
  Microsoft documents no limit on either.
  A rejection from the service maps under ADR-0004 like any other non-2xx.
- **The doubles handle custom headers like anything else.**
  `MemoryBackend` records the message that holds them.
  `ConsoleBackend` renders them alongside the addressing (ADR-0015).

## Considered options

- **Ship no header surface in v1.**
  It is the cheapest option, and consistent with ADR-0010's rejection of mechanisms for one caller.
  Rejected because `List-Unsubscribe` is a requirement for bulk senders at Gmail and Yahoo, and ADR-0002's motivating loop is a subscriber fan-out.
  A library whose main case is sending the same content to many people cannot leave out the header that case requires.
- **Allow only `x-` names on every backend.**
  It gives uniform behaviour, no backend-dependent rejection, and nothing to explain.
  Rejected because it applies Graph's limit to the two backends that do not have it, which inverts the premise of this map.
  It still does not give anyone `List-Unsubscribe`.
- **Add `.header(name, value)` with a keyed replace.**
  It reads well at a call site that varies one header per recipient.
  It matches `msg["X-Id"] = v` from every mail library.
  Rejected above: it adds a third semantic to ADR-0002 and the first exception to ADR-0007.
  It saves only a dict splat, and the caller writes that anyway when they already hold a mapping.
- **Add `.add_header(name, value)`, which appends, as the stdlib spells it.**
  It keeps ADR-0002's append rule with no amendment and allows repeated names.
  Rejected because a mistyped repeat writes two lines, and the recipient's client uses one of them.
  Nothing removes a line.
  The repeat it allows has no v1 use.
- **Translate known non-`x-` headers to Graph properties with a table.**
  It would map `Importance` to `importance` and `Disposition-Notification-To` to `isReadReceiptRequested`.
  Rejected because it covers two headers, not the one that matters.
  ADR-0010's test applies: it is a mechanism with two entries and no reported use.
- **Add named message features, `.importance("high")` and a read-receipt method.**
  This is the explicit version of the translation table.
  Each transport renders the feature its own way, and the header surface keeps the literal rule.
  Rejected here for scope, not for merit.
  It is a new public surface.
  It belongs in its own ticket with its own evidence, not inside a headers decision.
- **Use Graph's `singleValueExtendedProperties` with the `PS_INTERNET_HEADERS` namespace.**
  It does set arbitrary internet headers, including non-`x-` ones.
  It would close the gap completely.
  Rejected for v1 because it is undocumented for this use and verifying it needs a real tenant.
  [#23](https://github.com/ozanozbeker/epistole/issues/23) put that verification out of scope for a paper spec.
  It is the named reopener below.

## Consequences

- ADR-0010 expected `Importance` and read receipts to be set as custom headers, which #2 still had to specify.
  That consequence is closed as a no.
  Neither has a v1 surface.
  Graph raises on both as ordinary non-`x-` names.
- ADR-0007's list of attributes now includes `headers_`, produced by the mechanical rule with no exception.
- ADR-0012's pre-check "a custom header not starting with `x-`" now has the surface it lacked.
  Its inheritance note is closed.
- The same message can succeed on SMTP and raise on Graph.
  That is the one place in v1 where a backend swap changes the outcome for a legal message.
  It is a pre-check, so it makes no network call and the message is unchanged.
- A caller who wants the degraded send strips the header first, as ADR-0010 requires.
  There is no flag and no warning.
- `Message` gets one new field and the checks above, and no backend gets new configuration.
- Implementation verifies two things this ADR took from documentation.
  Microsoft's `message` resource marks `internetMessageHeaders` **Read-only** in its property table, while the same page says to add custom headers when creating a message.
  Every third-party report uses the create path, and a live send settles it.
  No documentation found says whether Exchange caps the header count or total size.
  So a large set is worth one live send before the docstring states anything.
- The reopener is `singleValueExtendedProperties` on the Graph draft path.
  If a live tenant shows it carries non-`x-` headers reliably, Graph's gap closes.
  This ADR's rejection then covers only whatever remains.

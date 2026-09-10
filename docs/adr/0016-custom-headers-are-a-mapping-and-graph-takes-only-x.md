# Custom headers are a mapping on the message, and Graph takes only `x-`

A `Message` carries caller-supplied headers.
`.headers(mapping)` replaces the whole set, `headers_` reads it back, and a name Epistole already writes is a `ValueError`.
SMTP and Gmail carry any legal header; Graph carries only names starting with `x-`, and any other name is a `RejectedError` pre-check at every size.
`Importance` and read receipts get no v1 surface.
Decided on [#27](https://github.com/ozanozbeker/epistole/issues/27), which closes an open consequence of ADR-0010 and makes ADR-0012's pre-check concrete.

## Why

**A header is message content, not provider configuration, so ADR-0010 does not rule here.**
ADR-0010 refused `backend_extra` because it was a dict of provider settings the message forwarded without understanding, and it refused `unsupported_feature()` because one gap does not need a mechanism.
A custom header is a different thing.
RFC 5322 defines it, all three backends model it, and the recipient's client is what reads it.
It fails ADR-0010's own test for an escape hatch: the message understands what it holds, and no backend is named anywhere in it.
The knobs ADR-0010 sent to backend constructors, Graph's `saveToSentItems` and Gmail's `threadId`, never appear in the sent mail at all, which is the line between the two.

**One method, whole-set replace, because the API already has that rule.**
`.to(address, /, *more)` replaces (ADR-0002), so `.headers(mapping)` replacing is the same rule with the same shape, and it needs no amendment.
The alternative was `.header(name, value)` with a keyed replace, which is a third semantic the API does not have today, and which would have made `headers_` the first exception to ADR-0007's mechanical rule.
Callers arrive holding a dict, since headers are already a mapping everywhere else in Python's mail stack, so the mapping form takes the value they have.

**An empty mapping raises, so nothing removes here either.**
`.headers({})` is a `ValueError`.
This looks like a wart until you notice `.to()` cannot be called empty for the same reason: address methods take `(address, /, *more)` so `.to(*[])` fails at the call site.
Under both rules a base without something is built without it, and neither method is a way to take something back.

**A `Mapping` forbids repeated names, and that is the whole answer.**
RFC 5322 allows a few field names to repeat, `Received` and `Comments` among them.
A mapping cannot express that, and nothing in v1 wants to: `Received` is written by relays in transit, not by senders, and reading mail is out of scope for this map.
The type refuses repeats, so there is no check to write and no rule for a caller to learn.

**Both checks live on the message, and the newline check is a security rule.**
Python's stdlib already refuses the malformed cases, tested on 3.13:

```
"X-A", "a\r\nBcc: eve@example.com"  ->  ValueError  Header values may not contain linefeed or carriage return characters
"X:D", "1"                          ->  ValueError  Header field name contains invalid characters: 'X:D'
"X-Café", "1"                       ->  ValueError  Header field name contains invalid characters: 'X-Café'
"X-C", "café"                       ->  b'X-C: =?utf-8?q?caf=C3=A9?=\n'
```

Relying on that would guard two backends out of three.
Graph never builds an `EmailMessage`: ADR-0012 sends JSON, so a value holding `\r\n` would travel as a JSON string and Exchange would write the lines it spells out.
That is header injection, and the caller who supplied a user-controlled campaign id would be the one who shipped it.
So `Message` runs the check itself, once, for every backend, at the line that named the header.

**Epistole's own names are a caller mistake, not a negotiation.**
There is no reading of `.headers({"Subject": "Q3"})` where the caller does not mean `.subject("Q3")`.
ADR-0004 sorts a caller mistake before the wire as `ValueError`, and letting the caller win would be worse than it sounds for two names: `Message-ID` and `Date` describe a submission and are stamped on the `Submission`, not the `Message` (ADR-0015), so a caller-set `Message-ID` would have to beat a value that does not exist yet, and `SendResult.message_id` would then report an id Epistole did not stamp, which contradicts ADR-0004.
Silently dropping the caller's header is the third option and ADR-0010 already banned the silent drop.
The match is case-insensitive because RFC 5322 field names are, and it is an exact name match rather than a prefix, so `In-Reply-To` stays legal next to an owned `Reply-To`.

**Graph's rule is inherited, and the two features that motivated this ticket close as a no.**
Microsoft documents the naming rule on the `message` resource: "Add custom headers only when creating a message, and name them starting with 'x-'."
ADR-0012 already chose JSON on every Graph request and recorded the pre-check; this ADR only makes it concrete.
ADR-0010 left a consequence saying `Importance` and read receipts would ride on custom headers once headers were specified.
They do not.
Both are non-`x-`, so both raise on Graph, and Graph expresses those meanings as first-class JSON properties instead (`importance`, `isReadReceiptRequested`).

Two ways to close that gap were considered and rejected under Considered options.
The honest summary is that neither fixes the header a newsletter actually needs: `List-Unsubscribe` is not translatable to any Graph property, so the case that sends this feature to the top of a user's list raises on Graph either way.

## Rules

- **`.headers(mapping, /)` replaces the whole set and returns a new message.**
  `Mapping[str, str]`, copied at the call, so the caller's dict cannot reach the message afterwards.
  `.headers({})` raises `ValueError`.
- **`headers_` reads the set back**, as a `MappingProxyType` in the order it was given, so `submissions[0].message.headers_ == {"X-Campaign-Id": "autumn"}` holds in a test (ADR-0007, ADR-0015).
  It holds the caller's headers alone and never the ones Epistole writes.
- **Stored as a tuple of pairs.**
  A `Message` is hashable and equal by content (ADR-0002), which a dict field would break, and address lists already become tuples for the same reason.
- **A legal name is one or more characters from printable ASCII 33 to 126, excluding colon.**
  RFC 5322 `ftext`. Anything else is a `ValueError`, including an empty name.
- **A legal value is a `str` holding no carriage return and no line feed.**
  Anything else is a `ValueError`.
  The character set is not otherwise checked, matching ADR-0014: a non-ASCII value travels, RFC 2047-encoded by the stdlib on the SMTP and Gmail paths and as UTF-8 in JSON on Graph.
- **A name Epistole owns is a `ValueError`**, matched case-insensitively against the exact name: `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject`, `Message-ID`, `Date`, `MIME-Version`, `Content-Type`, `Content-Transfer-Encoding`, `Content-ID`, `Content-Disposition`.
- **Every check runs in `Message`**, so it fails at the line that named the header, on every backend (ADR-0002).
- **SMTP and Gmail write every header**, after the ones Epistole writes, in the caller's order.
- **`GraphTransport` refuses a name that does not start with `x-`**, case-insensitive, with `RejectedError` and `__cause__` `None`, before it writes, on both the `sendMail` path and the draft path (ADR-0004, ADR-0012).
  The error names the offending header.
- **Epistole caps neither the count nor the total size of headers.**
  Microsoft documents no limit on either, and a refusal from the service maps under ADR-0004 like any other non-2xx.
- **The doubles carry headers like anything else.**
  `MemoryBackend` records the message that holds them, and `ConsoleBackend` renders them alongside the addressing (ADR-0015).

## Considered options

- **No header surface in v1.**
  Cheapest, and consistent with ADR-0010's refusal to build mechanisms for one caller.
  Rejected because `List-Unsubscribe` is a requirement for bulk senders at Gmail and Yahoo, and ADR-0002's motivating loop is a subscriber fan-out.
  A library whose main case is sending one body to many people cannot refuse the header that case requires.
- **`x-` only, on every backend.**
  Uniform behaviour, no backend-dependent refusal, nothing to explain.
  Rejected because it exports Graph's limit to the two backends that do not have it, which inverts the premise of this map, and it still does not give anyone `List-Unsubscribe`.
- **`.header(name, value)` with a keyed replace.**
  Reads well at a call site that varies one header per recipient, and matches `msg["X-Id"] = v` from every mail library.
  Rejected above: a third semantic in ADR-0002 and the first exception to ADR-0007, in exchange for a dict splat the caller writes anyway when they already hold a mapping.
- **`.add_header(name, value)`, appending, as the stdlib spells it.**
  Keeps ADR-0002's append rule with no amendment and allows repeated names.
  Rejected because a mistyped repeat writes two lines and the recipient's client picks one, nothing removes, and the repeat it buys has no v1 use.
- **A translation table from known non-`x-` headers to Graph properties.**
  `Importance` to `importance`, `Disposition-Notification-To` to `isReadReceiptRequested`.
  Rejected because it serves two headers, not the one that matters, and ADR-0010's test applies: a mechanism with two entries and no reported use.
- **Named message features, `.importance("high")` and a read-receipt method.**
  The honest version of the translation table: each transport renders the feature its own way, and the header surface keeps the literal rule.
  Rejected here for scope, not for merit.
  It is a new public surface and belongs to a ticket that argues for it on its own evidence, rather than arriving inside a headers decision.
- **Graph's `singleValueExtendedProperties` with the `PS_INTERNET_HEADERS` namespace.**
  It does set arbitrary internet headers, including non-`x-` ones, and it would close the gap completely.
  Rejected for v1 because it is undocumented for this use and verifying it needs a real tenant, which [#23](https://github.com/ozanozbeker/epistole/issues/23) put out of scope for a paper spec.
  It is the named reopener below.

## Consequences

- ADR-0010's consequence that `Importance` and read receipts "ride on custom headers, which #2 still has to specify" is closed as a no.
  Neither has a v1 surface, and both raise on Graph as ordinary non-`x-` names.
- ADR-0007 gains `headers_` in its list of readbacks, produced by the mechanical rule with no exception.
- ADR-0012's pre-check "a custom header not starting with `x-`" now has the surface it was waiting for, and its inheritance note is discharged.
- The same message can succeed on SMTP and raise on Graph.
  That is the one place in v1 where a backend swap changes the outcome for a legal message, and it is a pre-check, so it costs no wire call and the message is unchanged.
- A caller who wants the degraded send strips the header first, as ADR-0010 requires.
  There is no flag and no warning.
- `Message` grows one field and two checks, and no backend grows configuration.
- Implementation verifies two things this ADR took from documentation.
  Microsoft's `message` resource marks `internetMessageHeaders` **Read-only** in its property table while the same page says to add custom headers when creating a message; every third-party report uses the create path, and a live send settles it.
  Whether Exchange caps the header count or total size is documented nowhere found, so a large set is worth one live send before the docstring promises anything.
- The reopener is `singleValueExtendedProperties` on the Graph draft path.
  If a live tenant shows it carries non-`x-` headers reliably, Graph's gap closes and this ADR's refusal narrows to whatever remains.

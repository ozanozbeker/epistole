# An address is a string, and Epistole checks its shape, not its validity

An address is a `str` everywhere: in `.to()`, `.cc()`, `.bcc()`, `.reply_to()`, and in a backend's `from_address`.
`Address(name, email)` is a `str` subclass that formats a display name, so there is no second type in any signature.
Each string must hold exactly one address, checked when the caller supplies it and raised as `ValueError`.
Whether that address exists, accepts mail, or may send is the mail service's answer, never Epistole's.
Decided on [#26](https://github.com/ozanozbeker/epistole/issues/26).

Measurements below ran on this repo's interpreter, Python 3.14.7, against `requires-python = ">=3.13"`.

## Why

**A string is the shape the wire already carries.**
SMTP writes the header bytes as given, and Gmail takes an entire RFC 5322 message as base64url `raw`.
Only Graph needs the parts separately, because ADR-0012 puts JSON on every Graph request and `toRecipients` wants `{"emailAddress": {"address": ..., "name": ...}}`.
That split is one `email.utils.getaddresses` call on a string Epistole already holds.
A richer type would be built at the call site and taken apart again at the wire for two backends out of three.

**The helper is a `str`, so one type reaches every surface.**
A distinct `Address` class costs a union `str | Address` in `.to()` and its three sisters, a normalisation step to decide what a frozen `Message` stores, a decision about what readbacks return, and the same union again on `from_address`.
A `str` subclass costs none of them.
`Address("Ada Lovelace", "ada@example.com") == 'Ada Lovelace <ada@example.com>'` is `True`, so the ADR-0007 readbacks stay plain string comparisons in a test against `MemoryBackend`, which is the only place those names are typed.
The capital letter stays honest because the value is a real class and `isinstance` works.

The argument order is `(name, email)`, matching `email.utils.formataddr` and `parseaddr`.
`docs/research/prior-art.md` line 1499 records Envelopes using `(address, name)` and `emails` using `(name, address)`, and says to follow the stdlib rather than invent a third order.

**Quoting and international display names are already solved in stdlib.**
`formataddr` quotes a name that needs it and RFC 2047-encodes a name that is not ASCII:

```
formataddr(('Lovelace, Ada', 'ada@example.com'))  -> '"Lovelace, Ada" <ada@example.com>'
formataddr(('Ada Løvelace', 'ada@example.com'))   -> '=?utf-8?q?Ada_L=C3=B8velace?= <ada@example.com>'
```

So the helper is a call to `formataddr` and nothing else.
Writing the quoting rules by hand would be Epistole's own bug surface for a job the standard library does correctly.

**Checking structure and checking validity are different jobs, and only one is Epistole's.**
`docs/research/prior-art.md` line 1576 records flanker keeping `parse` (grammar, never raises) apart from `validate_address` (DNS and MX lookups).
ADR-0001 already took that position for the from address: "Whether the address is legitimate is the mail service's call. Epistole writes it and surfaces the refusal."
This ADR applies the same line to recipients.
Epistole answers "did the caller hand me one address", which it can know for certain.
It does not answer "will this address receive mail", which it cannot know without a network round trip it has no business making.

**One string means one address, because the stdlib loses the input otherwise.**
`parseaddr` never raises and fails open.
It returns `('', '')` for `'ada@example.com, bad'`, discarding both.
`getaddresses` splits correctly instead, so the count is the check:

```
input                             n  addr
'ada@example.com'                 1  'ada@example.com'
'Ada Lovelace <ada@example.com>'  1  'ada@example.com'
'"Lovelace, Ada" <ada@example.com>'  1  'Lovelace, Ada' / 'ada@example.com'
'ada@example.com, bob@example.com'   2  'a@b.com'
```

A comma inside a quoted display name does not split, so the count is safe.
Two addresses in one string is a `ValueError`, and the caller writes `.to("a@b.com", "c@d.com")`, which ADR-0002's varargs already require for the empty case.

**Requiring exactly one `@` would refuse legal addresses.**
A quoted local part may contain one:

```
'"a@b"@example.com'                        exactly-one-@ = False, last-@ split = True
'"very.unusual.@.unusual.com"@example.com' exactly-one-@ = False, last-@ split = True
```

Splitting on the **last** `@` and requiring both halves accepts these and still refuses `'garbage'` and `'@example.com'`.
It is the strictest rule that inspects nothing inside either half, so it cannot refuse an address on reasoning of its own.

**Character set is not checked, because Epistole is not a validation library.**
A caller supplies addresses they already know work.
Nothing in this repo establishes what Gmail, Exchange Online, the Gmail API, or Graph do with an internationalised local part or an IDN domain, and answering it would mean a research effort whose only product is a narrower `.to()`.
Non-ASCII addresses therefore pass through untouched and the service answers.

Two facts fall out of that and are handled in the rules rather than left as surprises.
`formataddr` refuses a non-ASCII addr-spec outright, at `email/utils.py` line 87, `address.encode('ascii')`, so the helper cannot format what the plain-string path accepts.
And `smtplib.send_message` raises `SMTPNotSupportedError` when the message carries a non-ASCII address and the server does not advertise `SMTPUTF8` (`docs/research/send-boundary-semantics.md` line 89), which ADR-0004 mapped only for `login` and `auth`.

## Rules

- **An address is a `str`.**
  `to(address: str, /, *more: str)` and the same for `.cc()`, `.bcc()`, `.reply_to()`.
  A `Message` stores addresses as `tuple[str, ...]` and the ADR-0007 readbacks return that.
- **`Address(name, email)` is a `str` subclass** whose `__new__` returns `formataddr((name, email))`.
  It is sugar for the display-name case and carries no behaviour of its own.
  A hand-written `"Ada Lovelace <ada@example.com>"` is equally valid and indistinguishable, by construction.
  It raises `ValueError` when `formataddr` raises `UnicodeEncodeError` on a non-ASCII address, with the original as `__cause__`.
  The helper formats what `formataddr` can format; the plain-string path stays open for the rest.
- **Structure is checked where the caller supplies the address**, in `.to()` and its sisters and in a backend's constructor, and raises `ValueError` per ADR-0004.
  A string passes when `getaddresses` returns exactly one pair, its addr-spec is non-empty, and both halves of the addr-spec's last `@` are non-empty.
  Nothing inside either half is inspected: no dot in the domain, no TLD list, no length limit, no DNS or MX lookup.
- **Validity belongs to the mail service.**
  A structurally sound address that the service refuses arrives as `RecipientsRefusedError` or `result.refused` on SMTP, and as a whole-message refusal on Gmail and Graph, per ADR-0004.
- **`from_address` takes the same type and the same check**, at backend construction, as `ValueError`.
  RFC 5322 section 3.6.2 requires a `Sender` header once `From` names more than one mailbox; Epistole writes no `Sender`, so the one-address rule is the same rule.
- **Character set is never checked.**
  Non-ASCII local parts and IDN domains pass through as written.
  Epistole does not punycode a domain, because that is a silent rewrite of the caller's address and this repo already refused silent rewrites of caller input in ADR-0013.
- **`Connection.send` gains nothing.**
  Its completeness checks stay as ADR-0006 and `CONTEXT.md` *Complete message* define them.
  A message cannot hold a structurally bad address, because the method that would have added one refused.
- **ADR-0004's SMTP mapping gains one row**: `SMTPNotSupportedError` from `send_message` maps to `RejectedError`, with the original as `__cause__`.
  It is permanent against that server and the message as written cannot be sent to it, which is what `RejectedError` means.

## Considered options

- **A distinct `Address` class, stored as-is.**
  Buys the ability to refuse `"Ada Lovelace <ada@example.com>"` typed as a plain string, so that a display name must go through the helper.
  Rejected: the enforcement is runtime-only either way, since a type checker sees `str` in both designs, and it costs a union type on four methods plus `from_address`, a normalisation step, and a readback that no longer compares to a string.
- **Both accepted and normalised to a class at construction.**
  The same costs as above, plus a parser to turn strings into instances.
- **Reject non-ASCII addresses with `addr.isascii()`.**
  One line, symmetric between the two paths, and it removes both loose ends above at a stroke.
  Rejected because it refuses addresses that are legal under RFC 6531 on the strength of a guess about provider support that nothing in this repo establishes.
  Reversibility argues for it, since accepting later is additive and refusing later is breaking, but that is an argument for shipping less rather than an argument that the smaller surface is right.
- **Punycode the domain and pass the local part.**
  `'例子.广告'.encode('idna')` returns `b'xn--fsqu00a.xn--4rr70v'`, so the ASCII-local-part case is solvable client-side with no protocol extension.
  Rejected as a silent rewrite of what the caller wrote, on ADR-0013's reasoning.
  It also splits the problem in half and leaves the non-ASCII local part unanswered, since that needs SMTPUTF8 end to end and cannot be encoded.
- **Check addresses at send instead of at `.to()`.**
  ADR-0006 gives `Connection.send` the completeness check, so a home exists.
  Rejected: the one-address rule is a rule about the argument, and by send time the string is already split and the extra recipient is just a recipient.
  A build-time failure also points at the line that introduced the mistake.
- **No structural check at all.**
  Consistent with ADR-0001 and the cheapest thing that works.
  Rejected only because it cannot express the one-address rule, which is the failure `parseaddr` makes silent.
- **Research the provider support matrix first.**
  Following #19 to #25, where research recommended and a later ticket decided.
  Rejected on scope: the product would be a narrower `.to()`, and the caller supplies addresses they already know work.

## Consequences

- **Address literals are refused, and Epistole did not choose that.**
  `getaddresses(['a@[192.168.1.1]'])` returns `[('', '')]`, and so does `parseaddr`, so the addr-spec is empty and the check fails.
  The same holds for `a@[IPv6:::1]`.
  They are legal RFC 5321 and the stdlib parser drops them.
  A caller who needs one has no route through Epistole.
- **The two paths disagree on non-ASCII addresses, by design.**
  `.to("用户@例子.广告")` is accepted and `Address("Ada", "用户@例子.广告")` raises `ValueError`.
  The rule is that the helper formats what `formataddr` can format, and the docstring says so.
- **The check and the wire split are one mechanism.**
  The `getaddresses` call that validates shape produces exactly the pair Graph's `toRecipients` needs and the addr-spec SMTP's envelope needs.
  An implementation that recomputes it at the transport is doing the work twice.
- **`getaddresses` silently repairs some input.**
  `'ada @example.com'` becomes `'ada@example.com'`.
  Epistole reports nothing, because the addr-spec it will send is the repaired one and it is sound.
- **A caller who passes a non-ASCII address to an SMTP server without `SMTPUTF8` learns at send, not at build.**
  That is the price of not checking character set, and the ADR-0004 row above is what keeps it inside the error model.
- `CONTEXT.md` gains an *Address* entry and its *Recipient* entry names the type.

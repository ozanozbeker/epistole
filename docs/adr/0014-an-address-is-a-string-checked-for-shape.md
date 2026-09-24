# An address is a string, and Epistole checks its shape, not its validity

An address is a `str` everywhere: in `.to()`, `.cc()`, `.bcc()`, `.reply_to()`, and in a backend's `from_address`.
`Address(name, email)` is a `str` subclass that formats a display name, so there is no second type in any signature.
Each string must hold exactly one address.
Epistole checks that when the caller supplies it and raises `ValueError` otherwise.
The mail service, never Epistole, checks whether that address exists, accepts mail, or may send.
Decided on [#26](https://github.com/ozanozbeker/epistole/issues/26).
Amended on [#42](https://github.com/ozanozbeker/epistole/issues/42): an address that holds a line break is a `ValueError`.
Amended on [#41](https://github.com/ozanozbeker/epistole/issues/41): SMTP and Gmail write a message that holds a non-ASCII addr-spec with UTF-8 headers.

Measurements below ran on this repo's interpreter, Python 3.14.7, against `requires-python = ">=3.13"`.

## Why

**The backends' request formats already carry addresses as strings.**
SMTP writes the header bytes as given.
Gmail takes an entire RFC 5322 message as base64url `raw`.
Only Graph needs the parts separately, because ADR-0012 puts JSON on every Graph request.
`toRecipients` takes `{"emailAddress": {"address": ..., "name": ...}}`.
That split is one `email.utils.getaddresses` call on a string Epistole already holds.
A richer type would be built at the call site and taken apart again when sending, for two backends out of three.

**The helper is a `str`, so every surface takes one type.**
A distinct `Address` class would need a union `str | Address` in `.to()` and the other three address methods, a normalisation step that determines what a frozen `Message` stores, a decision about what the address attributes return, and the same union again on `from_address`.
A `str` subclass needs none of them.
`Address("Ada Lovelace", "ada@example.com") == 'Ada Lovelace <ada@example.com>'` is `True`.
So the ADR-0007 attributes stay plain string comparisons in a test against `MemoryBackend`.
Such a test is the only place those names are typed.
The capital letter is accurate because the value is a real class and `isinstance` works.

The argument order is `(name, email)`, matching `email.utils.formataddr` and `parseaddr`.
`docs/research/prior-art.md` line 1611 records Envelopes using `(address, name)` and `emails` using `(name, address)`.
It says to follow the stdlib rather than invent a third order.

**Quoting and international display names are already solved in stdlib.**
`formataddr` quotes a name that needs it and RFC 2047-encodes a name that is not ASCII:

```
formataddr(('Lovelace, Ada', 'ada@example.com'))  -> '"Lovelace, Ada" <ada@example.com>'
formataddr(('Ada Løvelace', 'ada@example.com'))   -> '=?utf-8?q?Ada_L=C3=B8velace?= <ada@example.com>'
```

So the helper is a call to `formataddr` and nothing else.
Writing the quoting rules by hand would add a source of bugs in Epistole for a job the standard library does correctly.

**Checking structure and checking validity are different jobs, and only one is Epistole's.**
`docs/research/prior-art.md` line 1702 records flanker keeping `parse` (grammar, never raises) apart from `validate_address` (DNS and MX lookups).
ADR-0001 already took that position for the from address: "Whether the address is legitimate is the mail service's call. Epistole writes it and surfaces the refusal."
This ADR applies the same line to recipients.
Epistole checks whether the caller passed one address, which it can determine for certain.
It does not check whether the address will receive mail.
That needs a network round trip, and Epistole should not make one.

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
Two addresses in one string is a `ValueError`.
The caller writes `.to("a@b.com", "c@d.com")`, which ADR-0002's varargs already require for the empty case.

**Requiring exactly one `@` would reject legal addresses.**
A quoted local part may contain one:

```
'"a@b"@example.com'                        exactly-one-@ = False, last-@ split = True
'"very.unusual.@.unusual.com"@example.com' exactly-one-@ = False, last-@ split = True
```

Splitting on the **last** `@` and requiring both halves accepts these and still rejects `'garbage'` and `'@example.com'`.
It is the strictest rule that inspects nothing inside either half, so it never rejects an address for what either half contains.

**Character set is not checked, because Epistole is not a validation library.**
A caller supplies addresses they already know work.
Nothing in this repo establishes what Gmail, Exchange Online, the Gmail API, or Graph do with an internationalised local part or an IDN domain.
Finding out would take a research effort whose only product is a narrower `.to()`.
So Epistole passes non-ASCII addresses through untouched, and the mail service accepts or rejects them.

Two facts follow from that.
The rules below cover both, so neither is a surprise.
`formataddr` raises on any non-ASCII addr-spec, at `email/utils.py` line 87, `address.encode('ascii')`.
So the helper cannot format what the plain-string path accepts.
And `smtplib.send_message` raises `SMTPNotSupportedError` when the message holds a non-ASCII address and the server does not advertise `SMTPUTF8` (`docs/research/send-boundary-semantics.md` line 98).
ADR-0004 mapped that exception only for `login` and `auth`.

## Rules

- **An address is a `str`.**
  `to(address: str, /, *more: str)` is the signature, and `.cc()`, `.bcc()`, and `.reply_to()` share it.
  A `Message` stores addresses as `tuple[str, ...]`, and the ADR-0007 attributes return that.
- **`Address(name, email)` is a `str` subclass** whose `__new__` returns `formataddr((name, email))`.
  It is sugar for the display-name case and has no behaviour of its own.
  A hand-written `"Ada Lovelace <ada@example.com>"` is equally valid and indistinguishable, by construction.
  It raises `ValueError` when `formataddr` raises `UnicodeEncodeError` on a non-ASCII address, with the original as `__cause__`.
  The helper formats what `formataddr` can format.
  The plain-string path accepts the rest.
- **Epistole checks structure where the caller supplies the address**, in `.to()` and the other address methods and in a backend's constructor.
  A failure raises `ValueError` per ADR-0004.
  A string passes when it holds no line break, `getaddresses` returns exactly one pair, its addr-spec is non-empty, and both halves of the addr-spec's last `@` are non-empty.
  A line break fails anywhere in the string, because `EmailMessage` raises on it at send time on SMTP and Gmail, and `ConsoleBackend` would write the rest as a separate line.
  Apart from line breaks, the check inspects nothing inside either half: no dot in the domain, no TLD list, no length limit, no DNS or MX lookup.
- **Validity belongs to the mail service.**
  When the service refuses a structurally sound address, the caller gets `RecipientsRefusedError` or `result.refused` on SMTP.
  On Gmail and Graph, the caller gets a whole-message rejection, per ADR-0004.
- **`from_address` takes the same type and the same check**, run at backend construction and raising `ValueError`.
  RFC 5322 section 3.6.2 requires a `Sender` header once `From` names more than one mailbox.
  Epistole writes no `Sender`, so the one-address rule is the same rule.
- **Epistole never checks character set.**
  It passes non-ASCII local parts and IDN domains through as written.
  It does not punycode a domain, because that is a silent rewrite of the caller's address.
  ADR-0013 already rejected silent rewrites of caller input.
- **SMTP and Gmail write a message that holds a non-ASCII addr-spec with UTF-8 headers**, as RFC 6532 defines.
  The addr-spec may be in `From`, `To`, `Cc`, `Bcc`, or `Reply-To`.
  Without UTF-8 headers, `EmailMessage` writes an RFC 2047 encoded-word into the addr-spec, where RFC 2047 forbids one.
  It did so on 3.13.12 and on 3.14.7.
  `email.parser` decodes that encoded-word and raises no error, so only the bytes show it.
  `smtplib.send_message` asks the server for `SMTPUTF8` only when the envelope is not ASCII.
  When the only non-ASCII address is in `Reply-To`, SMTP must ask for it too.
  Otherwise a server without `SMTPUTF8` receives UTF-8 headers, and the caller gets no error.
- **`Connection.send` adds no check.**
  Its completeness checks stay as ADR-0006 and `CONTEXT.md` *Complete message* define them.
  A message cannot hold a structurally bad address, because the method that would have added one raised.
- **ADR-0004's SMTP mapping gets one more row**: `SMTPNotSupportedError` from `send_message` maps to `RejectedError`, with the original as `__cause__`.
  The error is permanent against that server, and the message as written cannot be sent to it.
  `RejectedError` means exactly that.

## Considered options

- **Make `Address` a distinct class, stored as-is.**
  It would allow rejecting `"Ada Lovelace <ada@example.com>"` typed as a plain string, so that a display name must go through the helper.
  Rejected: the enforcement is runtime-only either way, since the static type is `str` in both designs.
  It also needs a union type on four methods plus `from_address`, a normalisation step, and an attribute that no longer compares to a string.
- **Accept both and normalise to a class at construction.**
  It has the same costs as above, plus a parser to turn strings into instances.
- **Reject non-ASCII addresses with `addr.isascii()`.**
  It is one line and symmetric between the two paths.
  It removes both problems above at once.
  Rejected because it raises on addresses that are legal under RFC 6531, based on a guess about provider support that nothing in this repo establishes.
  Reversibility favours it, since accepting later is additive and rejecting later is breaking.
  That is an argument for shipping less, not an argument that the smaller surface is right.
- **Punycode the domain and pass the local part.**
  `'例子.广告'.encode('idna')` returns `b'xn--fsqu00a.xn--4rr70v'`, so the ASCII-local-part case is solvable client-side with no protocol extension.
  Rejected as a silent rewrite of what the caller wrote, on ADR-0013's reasoning.
  It also handles only half the problem: the non-ASCII local part needs SMTPUTF8 end to end and cannot be encoded.
- **Check addresses at send instead of at `.to()`.**
  ADR-0006 gives `Connection.send` the completeness check, so a place for the check exists.
  Rejected: the one-address rule is a rule about the argument.
  By send time, the string is already split, and the extra recipient is just a recipient.
  A build-time failure also raises at the line that introduced the mistake.
- **Run no structural check at all.**
  It is consistent with ADR-0001 and the cheapest thing that works.
  Rejected only because it cannot express the one-address rule.
  `parseaddr` makes a violation of that rule silent.
- **Research the provider support matrix first.**
  This follows the pattern of #19 to #25, where research made a recommendation and a later ticket made the decision.
  Rejected on scope: the product would be a narrower `.to()`, and the caller supplies addresses they already know work.

## Consequences

- **Address literals are rejected, and Epistole did not choose that.**
  `getaddresses(['a@[192.168.1.1]'])` returns `[('', '')]`, and so does `parseaddr`.
  So the addr-spec is empty and the check fails.
  The same holds for `a@[IPv6:::1]`.
  They are legal under RFC 5321, and the stdlib parser drops them.
  A caller who needs one has no route through Epistole.
- **The two paths differ on non-ASCII addresses, by design.**
  `.to("用户@例子.广告")` is accepted, and `Address("Ada", "用户@例子.广告")` raises `ValueError`.
  The helper formats what `formataddr` can format.
  The docstring says so.
- **The check and the split each backend needs are one mechanism.**
  The `getaddresses` call that validates shape produces exactly the pair Graph's `toRecipients` needs and the addr-spec SMTP's envelope needs.
  An implementation that recomputes it at the transport is doing the work twice.
- **`getaddresses` silently repairs some input.**
  `'ada @example.com'` becomes `'ada@example.com'`.
  Epistole reports nothing, because the addr-spec it will send is the repaired one and it is sound.
- **A caller who passes a non-ASCII address to an SMTP server without `SMTPUTF8` gets the error at send, not at build.**
  That is the trade-off for not checking character set.
  The ADR-0004 row above keeps it inside the error model.
- An *Address* entry goes into `CONTEXT.md`, and its *Recipient* entry names the type.

# A pre-check measures real bytes, and every ceiling it enforces cites a vendor source

A backend refuses a message before the wire only where a vendor documents the limit.
Gmail checks two: an encoded message over 36,700,160 bytes, and more than 500 recipients.
Graph checks the three ADR-0012 and ADR-0016 already decided.
SMTP checks nothing, because `smtplib` already tells the server the size and the server answers.
Every gate reads the bytes the backend is about to send; none applies an expansion factor to a raw size.
Decided on [#30](https://github.com/ozanozbeker/epistole/issues/30), which found the whole block in `docs/spec.md` citing no ADR at all.

## Why

**The numbers were sourced; the citation was missing.**
`docs/research/send-boundary-semantics.md` quotes Google's API usage limits page for "a limit of 500 recipients per email message", and records that the Workspace sending-limits page says 2,000 total addresses with 500 external.
Neither page reconciles the two, so the research took 500 as the safe ceiling and this ADR takes it unchanged.
`docs/research/html-bodies-in-email.md` sources 36,700,160 bytes to the Gmail v1 discovery document rather than to any prose page, which is why it is written as an exact byte count and not as "35 MiB".
Both facts were already in the repo; what was missing was an ADR to cite, which is what `docs/spec.md` requires of every rule.

**Measuring beats estimating, on backends that build the message anyway.**
`docs/research/attachment-and-inline-rules.md` derives base64 expansion as `1.3333 * 78/76`, about 1.37, matching Google's own "about a 37% increase", and recommends deriving the encoded size arithmetically so that nothing has to be encoded to refuse it.
That saving is real and small.
Gmail sends the whole RFC 5322 message as base64url `raw`, and SMTP flattens it through `send_message`, so on both the exact bytes exist at the moment the gate runs; the estimate only buys refusing a few hundred milliseconds sooner on a message that was going to be refused.
Graph serializes its JSON body before it can choose a path at all (ADR-0012).
Against that, an approximation is wrong in both directions near the boundary, and being wrong there means refusing a message the service would have taken, which is the one failure mode a pre-check must not have.
So the factor is not used and no constant carries it.

**SMTP gets no gate, because the stdlib already has one.**
`smtplib.sendmail` appends `size=n` to MAIL FROM whenever the server advertised the `SIZE` extension, so the server refuses with `552` before any `DATA`.
A pre-check would duplicate a negotiation the stdlib already runs, and it would still miss a server that enforces a size it never advertised.
ADR-0004 maps `SMTPSenderRefused` with `552` to `RejectedError`, which is the same class a pre-check would have raised, so nothing about the caller's experience changes.

**A limit nobody documents is not a pre-check.**
ADR-0004 justifies pre-checks by saying the caller should see one class whether Epistole or the service noticed first.
That argument holds only for a ceiling Epistole can be right about.
An undocumented or guessed number refuses messages the service would have accepted, which is worse than the round trip it saves.
The tenant message limit on Exchange Online is the standing example: ADR-0012 leaves it unchecked for exactly this reason.

## Rules

- **Every pre-check raises `RejectedError` with `__cause__` `None` before writing** (ADR-0004).
- **A gate measures the bytes the backend will send.**
  No expansion factor, no estimate from a raw size.
- **SMTP has no pre-check.**
  `smtplib` sends `size=` when the server advertises `SIZE`, and `552` on MAIL FROM maps to `RejectedError` (ADR-0004).
- **Gmail checks two**: an encoded message over `36_700_160` bytes, and more than 500 recipients.
- **Graph checks three**, unchanged: an attachment over `150_000_000` raw bytes, more than 500 recipients, and a custom header not starting with `x-` (ADR-0012, ADR-0016).
- **Every size constant is private to its transport**, as ADR-0012 already requires of Graph's.
- **A ceiling with no vendor source gets no pre-check.**
  The service answers and the reply maps under ADR-0004 like any other.

## Considered options

- **Estimate with the 1.37 factor**, as `docs/research/attachment-and-inline-rules.md` recommends.
  Refuses without encoding, which is the research's whole point.
  Rejected above: the saving is small on backends that build the message anyway, and the error near the boundary points the wrong way.
- **Estimate first, then measure.**
  Fast rejection on the obvious cases, exact behaviour at the boundary.
  Rejected because it is two constants and two rules serving one gate.
- **No pre-checks anywhere; let every service answer.**
  Smallest surface, and every reply already maps to the same leaf.
  Rejected because Epistole would ship knowing a documented limit it declines to check, and the round trip on a 35 MB message is not free.
- **A pre-check on the Exchange Online tenant message limit.**
  Rejected in ADR-0012 and unchanged here: the value is per tenant and not readable, so any number would be a guess.
- **Take Gmail's 2,000-recipient figure instead of 500.**
  Rejected on the research's own reading: the two Google pages do not reconcile, and 500 is the one both are consistent with.

## Consequences

- A Gmail send to 501 recipients fails at Epistole rather than at Google, with the same class either way.
- The 1.37 constant leaves the codebase before it enters it, and `docs/research/attachment-and-inline-rules.md` keeps the derivation as a measurement this ADR declined to use rather than as a correction.
- A caller sending a 36 MB message through Gmail pays the base64 encoding before the refusal.
- If Google reconciles its two recipient pages upward, this ADR is where the number moves, and nothing public changes.

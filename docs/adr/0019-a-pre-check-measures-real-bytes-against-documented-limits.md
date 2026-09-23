# A pre-check measures real bytes and enforces only limits a vendor documents

A backend rejects a message before writing only where a vendor documents the limit.
Gmail checks two: an encoded message over 36,700,160 bytes, and more than 500 recipients.
Graph checks the three ADR-0012 and ADR-0016 already decided.
SMTP checks nothing, because `smtplib` already sends the size to the server and the server replies.
Every size check reads the bytes the backend is about to send.
None applies an expansion factor to a raw size.
Decided on [#30](https://github.com/ozanozbeker/epistole/issues/30), which found the whole block in `docs/spec.md` citing no ADR at all.

## Why

**The numbers were sourced, but the citation was missing.**
`docs/research/send-boundary-semantics.md` quotes Google's API usage limits page for "a limit of 500 recipients per email message".
It also records that the Workspace sending-limits page says 2,000 total addresses with 500 external.
Neither page reconciles the two, so the research took 500 as the safe limit.
This ADR takes it unchanged.
`docs/research/html-bodies-in-email.md` sources 36,700,160 bytes to the Gmail v1 discovery document rather than to any prose page.
So it is written as an exact byte count and not as "35 MiB".
Both facts were already in the repo.
The repo lacked an ADR to cite, and `docs/spec.md` requires one for every rule.

**Measuring is better than estimating on backends that build the message anyway.**
`docs/research/attachment-and-inline-rules.md` derives base64 expansion as `1.3333 * 78/76`, about 1.37, matching Google's own "about a 37% increase".
It recommends deriving the encoded size arithmetically so that nothing has to be encoded to reject it.
That saving is real and small.
Gmail sends the whole RFC 5322 message as base64url `raw`, and SMTP flattens it through `send_message`.
So on both, the exact bytes exist when the check runs.
The estimate would only reject a message a few hundred milliseconds sooner, and that message was going to be rejected anyway.
Graph serializes its JSON body before it can choose a path at all (ADR-0012).
Against that, an approximation is wrong in both directions near the boundary.
Being wrong there means rejecting a message the service would have accepted.
That is the one failure mode a pre-check must not have.
So the factor is not used, and no constant holds it.

**SMTP gets no size check, because the stdlib already has one.**
`smtplib.sendmail` appends `size=n` to MAIL FROM whenever the server advertised the `SIZE` extension.
So the server rejects an oversized message with `552` before any `DATA`.
A pre-check would duplicate a negotiation the stdlib already runs.
It would still miss a server that enforces a size it never advertised.
ADR-0004 maps `SMTPSenderRefused` with `552` to `RejectedError`, the same class a pre-check would have raised.
So nothing changes for the caller.

**A limit nobody documents is not a pre-check.**
ADR-0004 justifies pre-checks by saying the caller should get one class whether Epistole or the service detected the limit first.
That argument holds only for a limit Epistole can be right about.
A pre-check with an undocumented or guessed number rejects messages the service would have accepted.
That is worse than the round trip it saves.
The tenant message limit on Exchange Online is the standing example: ADR-0012 leaves it unchecked for exactly this reason.

## Rules

- **Every pre-check raises `RejectedError` with `__cause__` `None` before writing** (ADR-0004).
- **A size check measures the bytes the backend will send.**
  It applies no expansion factor and makes no estimate from a raw size.
- **SMTP has no pre-check.**
  `smtplib` sends `size=` when the server advertises `SIZE`.
  `552` on MAIL FROM maps to `RejectedError` (ADR-0004).
- **Gmail checks two**: an encoded message over `36_700_160` bytes, and more than 500 recipients.
- **Graph checks three**, unchanged: an attachment over `150_000_000` raw bytes, more than 500 recipients, and a custom header not starting with `x-` (ADR-0012, ADR-0016).
- **Every size constant is private to its transport**, as ADR-0012 already requires of Graph's.
- **A limit with no vendor source gets no pre-check.**
  The service's reply maps under ADR-0004 like any other.

## Considered options

- **Estimate with the 1.37 factor**, as `docs/research/attachment-and-inline-rules.md` recommends.
  It rejects without encoding, which is the research's whole point.
  Rejected above: the saving is small on backends that build the message anyway.
  Near the boundary, its error can reject a message the service would accept.
- **Estimate first, then measure.**
  It gives fast rejection on the obvious cases and exact behaviour at the boundary.
  Rejected because it needs two constants and two rules for one check.
- **Run no pre-checks, and let every service reply.**
  It has the smallest surface, and every reply already maps to the same class.
  Rejected because Epistole would ship without checking a limit the vendor documents.
  The round trip on a 35 MB message is not free.
- **Add a pre-check on the Exchange Online tenant message limit.**
  Rejected in ADR-0012 and unchanged here: the value is per tenant and not readable, so any number would be a guess.
- **Take Gmail's 2,000-recipient figure instead of 500.**
  Rejected on the research's own reading: the two Google pages do not reconcile, and 500 is the one both are consistent with.

## Consequences

- A Gmail send to 501 recipients fails at Epistole rather than at Google, with the same class either way.
- The 1.37 constant never enters the codebase.
  `docs/research/attachment-and-inline-rules.md` keeps the derivation as a measurement this ADR declined to use, not as a correction.
- A caller sending a 36 MB message through Gmail incurs the cost of base64 encoding before the rejection.
- If Google reconciles its two recipient pages upward, the number changes in this ADR.
  Nothing public changes.

# Choosing a backend

Draft.
Written during specification, before the library exists, so treat the guidance as settled and the API names as provisional.

herma sends the same message through any backend.
Choosing one is a deployment decision, not a code decision, and this page is the reasoning behind it.

## Short answer

Use **SMTP** unless something stops you.
It works with every mail system, it carries the largest messages, and it sends exactly the MIME herma built.

Use **Graph** when your tenant has turned SMTP AUTH off, or when you need a message id or a retry hint.
Accept its 4 MB body limit before you choose it.

Use **Gmail** when you are already authenticated against a Google account and would rather not manage an SMTP credential.

## The comparison

| | SMTP | Gmail | Graph |
| --- | --- | --- | --- |
| Mail systems served | any | Google accounts | Exchange Online |
| Largest body | whole-message limit | whole-message limit | **4 MB, no path past it** |
| Largest message | server `SIZE`, 35 MB on a default Exchange Online tenant | 25 MB before encoding | 35 MB default, 1 MB to 150 MB configurable |
| Largest attachment | shares the message limit | shares the message limit | 150 MB, via upload session |
| Message id returned | none reachable | mailbox-local id | none |
| Per-recipient refusals | visible | not expressible | not expressible |
| Retry hint | none | none documented | `Retry-After` |
| MIME you send | is what arrives | is what arrives | rebuilt by Exchange |
| Recipients per message | server policy | 500 | 500 |
| Credentials | anonymous, password, or OAuth | Google credentials | token credential |

## The four things that decide it

### Body size

This is the one that most often removes the choice.

Graph caps the entire write request at 4 MB and publishes no chunked path for a message body.
A large HTML body cannot be sent, at all, by any route.
SMTP and Gmail measure against the whole message instead, so a body of several MB is routine on both.

If you send embedded HTML reports, Graph forces you to restructure: attach the report as a file and send a small body.
That is a sound pattern and plenty of teams already use it, but it is a rewrite rather than a setting.

### Whether your tenant allows SMTP AUTH

On Exchange Online, SMTP client submission can be switched off, and two common security postures do switch it off: enabling security defaults, and any authentication policy that blocks basic authentication for SMTP.
Neither is exotic and the trend runs one way.

Graph keeps working through all of it.
That is the argument for configuring the Graph backend even in a shop that expects to use SMTP forever.

Note that SMTP AUTH being disabled organization-wide is not by itself a blocker.
The per-mailbox setting overrides the organization setting, and enabling it for one mailbox is the documented pattern.

### Fidelity against features

SMTP and Gmail both take a complete RFC 5322 message that herma builds, so what you send is what arrives, and inline image structure is under herma's control.

Graph takes a flat JSON array and Exchange serializes the MIME later, inside its transport.
Microsoft does not document where inline parts land relative to the alternative body, so herma can guarantee the `cid:` references in your HTML but not the MIME structure around them.

In exchange, Graph is the only backend that tells you how long to wait when it throttles you, and Gmail is the only one that returns an id.

### What the permission costs

For a plain send the three are comparable: `SMTP.SendAsApp` on Exchange Online, the `gmail.send` scope on Google, `Mail.Send` on Graph.

Graph changes above 3 MB of attachment.
The large-attachment path needs a draft, which needs `Mail.ReadWrite`, which grants reading every message in scope.
So one large attachment moves an application from "can send" to "can send and can read all mail", and a security reviewer will notice.
Neither SMTP nor Gmail changes its permission with size.

Keeping attachments under 3 MB is worth designing for if you send through Graph.

## Test backends

`ConsoleBackend` and `MemoryBackend` are backends like any other.
Swapping one in is the same one-word change as swapping between real ones, which is the point.

## Where these numbers come from

Measured or quoted on 2026-09-08.
Limits move; re-check before relying on one.

- Graph's 4 MB applies to every write request, and `message.body.content` rides inside it: [Use the Microsoft Graph API](https://learn.microsoft.com/en-us/graph/use-the-api).
  There is no chunked path for a body.
  Upload sessions exist only for drive items, Outlook attachments, and to-do attachments: [uploadSession](https://learn.microsoft.com/en-us/graph/api/resources/uploadsession).
- Graph's large-attachment flow, its 150 MB ceiling, and the `Mail.ReadWrite` requirement: [Attach large files](https://learn.microsoft.com/en-us/graph/outlook-large-attachments).
  `Mail.ReadWrite` "Doesn't include permission to send mail", so it is additional rather than a substitute: [Application RBAC](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac).
- Exchange Online's 35 MB default and 1 MB to 150 MB range:
  [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits).
- Gmail's 25 MB account limit is measured before encoding: [Gmail sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace).
  The API's own cap is 36,700,160 bytes on `users.messages.send`, from the v1 discovery document.
- Gmail's recipient limit is stated as 500 on one Google page and 2,000 with 500 external on another.
  The two are not reconciled anywhere, so 500 is the safe ceiling.
- Gmail documents no `Retry-After` header and prescribes exponential backoff instead.
  Graph documents `Retry-After` on `429` and `503` and tells you to obey it.
- Exchange rebuilds MIME during transport:
  [Things to know about send mail](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail).
- SMTP's ceiling is whatever the server advertises through the `SIZE` extension:
  [RFC 1870](https://datatracker.ietf.org/doc/html/rfc1870).
- SMTP AUTH per-mailbox settings override the organization setting, and security defaults disable the
  protocol outright:
  [Enable or disable SMTP AUTH](https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/authenticated-client-smtp-submission).

Fuller working, including the parts that turned out not to matter, is in `docs/research/send-boundary-semantics.md` and `docs/research/attachment-and-inline-rules.md`.

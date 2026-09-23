# Attachment and inline-image rules across the three backends

This note records research for [issue #4](https://github.com/ozanozbeker/epistole/issues/4).
It uses primary sources only.
Every factual claim below has a URL.
Where a claim comes from a live probe or a local run rather than a document, the text says so.

## What this means for Epistole's design

Two of the three backends use MIME.
The third does not.
SMTP and the Gmail API both take a complete RFC 5322 message.
Epistole builds it with `email.message.EmailMessage`.
Microsoft Graph takes a flat JSON array of `fileAttachment` objects.
Graph builds the MIME itself, inside Exchange.
So Epistole's attachment API has to describe an attachment, not a MIME part.
An `Attachment` value object with the fields `content: bytes`, `filename: str`, `content_type: str | None`, `inline: bool`, and `content_id: str | None` maps cleanly onto all three.
A MIME-tree-shaped API does not, because Graph has no way to express nesting.

The backends differ on size.
Graph requires a different call sequence above 3 MB.
That sequence needs a different OAuth permission.
`sendMail` needs `Mail.Send`.
`createUploadSession` needs `Mail.ReadWrite` ([sendMail permissions](https://learn.microsoft.com/en-us/graph/api/user-sendmail), [createUploadSession permissions](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession)).
An app that only ever attaches small files needs only the narrower scope.
The difference is visible to callers, so Epistole should document it rather than hide it.

Check size before encoding.
Derive the encoded size arithmetically.
Epistole needs both numbers.
Neither requires encoding the bytes first.
Graph's 3 MB threshold applies to the raw file bytes.
Gmail's 25 MB account limit applies to the size before encoding.
The SMTP `SIZE` value, Graph's 4 MB request cap, and the Gmail API's 35 MiB upload cap all apply to the size after encoding.
For base64 the encoded size is `4 * ceil(n / 3)` characters, wrapped at 76 characters per line ([RFC 2045](https://datatracker.ietf.org/doc/html/rfc2045)).
With CRLF line endings that is `1.3333 * 78/76`, or about 1.37x.
That is exactly the "about a 37% increase" Google quotes ([Gmail receiving limits](https://knowledge.workspace.google.com/admin/gmail/gmail-receiving-limits-in-google-workspace)).
Epistole should use that number, not a flat 33 percent.

Normalize the content id at the boundary.
MIME requires angle brackets around it in the header.
Graph takes the bare value in JSON.
The `cid:` reference in the HTML body is bare in all three cases.
Store the bare form internally.
Add brackets only when writing a MIME header.

## Comparison table

| Aspect | SMTP (stdlib MIME) | Gmail API | Microsoft Graph |
| --- | --- | --- | --- |
| Attachment representation | MIME body part | MIME body part inside `raw` | `fileAttachment` JSON object |
| Encoding as sent | base64 body, 76-char lines | whole message base64url in `raw` | file base64 in `contentBytes` |
| Nesting under app control | yes | yes | no, Exchange builds the MIME |
| Small-file path | one `sendmail()` | one `messages.send` | `sendMail` with `attachments` array |
| Large-file path | same call, subject to `SIZE` | same call, up to the upload cap | draft, `createUploadSession`, ranged `PUT`, then send |
| Hard threshold that changes the call | none | none (upload style is a recommendation) | 3 MB |
| Transport limit | server-advertised `SIZE` | 36700160 bytes (35 MiB) for `messages.send` | 4 MB per write request |
| Account or tenant limit | server policy | 25 MB send (Workspace and personal) | 35 MB default, 1 MB to 150 MB configurable |
| Limit measured | after encoding | 35 MiB after, 25 MB before | 4 MB after, 3 MB before |
| Inline marker | `Content-Disposition: inline` | same | `isInline: true` |
| Inline identifier | `Content-ID: <value>` | same | `contentId: "value"`, no brackets |
| Container for inline images | `multipart/related` | same | not expressible, Exchange builds it |
| Filename field | `filename` parameter, RFC 2231 encoded | same | `name`, plain UTF-8 JSON string |
| Content type | set by caller | set by caller | optional, Graph sniffs the bytes |
| Documented oversize failure | SMTP `552` or `452` | none documented | HTTP 413 |

## SMTP and the Python stdlib

### MIME representation

An attachment is a MIME body part.
`EmailMessage.add_attachment` builds the part and attaches it.
If needed, it first promotes the message to `multipart/mixed` ([docs](https://docs.python.org/3/library/email.message.html)).
`add_related` promotes to `multipart/related`.
`add_alternative` promotes to `multipart/alternative`.
Each raises `TypeError` if the message is already a multipart of the wrong subtype.
So the order of calls matters.

`add_attachment` sets `Content-Disposition: attachment` when the part has no such header.
`add_related` sets `Content-Disposition: inline` when the part has no such header ([docs](https://docs.python.org/3/library/email.message.html)).

A filename overrides that inline default.
`raw_data_manager.set_content` sets the disposition itself: "If _disposition_ is set, use it as the value of the _Content-Disposition_ header.
If not specified, and _filename_ is specified, add the header with the value `attachment`" ([contentmanager docs](https://docs.python.org/3/library/email.contentmanager.html)).
The header is then already present, so `add_related` does not change it.
Verified locally on CPython 3.14.7: `add_related(data, maintype="image", subtype="png", cid="<a@b>", filename="logo.png")` produces `Content-Disposition: attachment; filename="logo.png"`.
Passing `disposition="inline"` explicitly restores the intended value.
Epistole must pass `disposition="inline"` whenever it passes both `filename` and `cid`.
Otherwise it sends inline images as ordinary attachments.

For `bytes` payloads, `set_content` raises `TypeError` unless the call passes `maintype` and `subtype`.
Their transfer encoding defaults to base64 ([contentmanager docs](https://docs.python.org/3/library/email.contentmanager.html)).

### Structure for an HTML mail with an inline image and a file attachment

`multipart/alternative` orders its parts "in increasing order of preference, that is, with the preferred format last" ([RFC 2046](https://datatracker.ietf.org/doc/html/rfc2046)).
So the plain text goes first.
The inline image belongs in a `multipart/related` wrapped around the HTML part, not around the whole message.
It belongs there because `multipart/related` groups "objects that are aggregates of related MIME body parts" ([RFC 2387](https://datatracker.ietf.org/doc/html/rfc2387)).
Its root is the first part unless a `start` parameter names another.
The file attachment goes at the `multipart/mixed` level.

A local run confirms that this call order produces the right tree:

```text
multipart/mixed
  multipart/alternative
    text/plain
    multipart/related
      text/html
      image/png            Content-ID: <logo123>, Content-Disposition: inline
  application/octet-stream Content-Disposition: attachment
```

Build it by calling `set_content`, then `add_alternative(subtype="html")`, then `add_related` on the returned HTML part, then `add_attachment` on the top-level message.

### Size limits and the SIZE extension

An SMTP server advertises its size limit through the `SIZE` service extension ([RFC 1870](https://datatracker.ietf.org/doc/html/rfc1870)).
The EHLO keyword takes "a decimal number indicating the fixed maximum message size in bytes that the server will accept".
"A parameter value of 0 (zero) indicates that no fixed maximum message size is in force".
If the server omits the parameter, "no information is conveyed about the server's fixed maximum message size".
A client may declare the size up front with `MAIL FROM ... SIZE=n`.
If the message is too large, the server replies "552 message size exceeds fixed maximium message size".
If the server is merely out of room right now, it replies "452 insufficient system storage".

`smtplib.SMTP.esmtp_features["size"]` holds the advertised value after `ehlo()`.
I probed these hosts live from this machine on 2026-09-07:

| Host | Advertised `SIZE` | Bytes |
| --- | --- | --- |
| `smtp.gmail.com:587` | 35882577 | about 34.2 MiB |
| `smtp-mail.outlook.com:587` | 157286400 | 150 MiB exactly |
| `smtp.office365.com:587` | 157286400 | 150 MiB exactly |

The `SIZE` value is a post-encoding number, because it covers the message as transmitted.
Gmail's 35882577 divided by 1.37 is about 26.2 MB.
That is consistent with a 25 MB pre-encoding limit after base64 plus line breaks.

Epistole should read `esmtp_features["size"]` and raise locally before writing the message, rather than write it and receive a 552.

## Gmail API

### Raw MIME representation

The Gmail API takes a whole MIME message.
The `raw` field is "The entire email message in an RFC 2822 formatted and base64url encoded string" ([users.messages resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages), confirmed verbatim in the [v1 discovery document](https://gmail.googleapis.com/$discovery/rest?version=v1)).
"Gmail messages are sent as base64URL encoded strings within the `raw` field of a `messages` resource" ([sending guide](https://developers.google.com/workspace/gmail/api/guides/sending)).

So Epistole builds the message the same way for Gmail and SMTP.
Epistole can send through Gmail anything it can express in MIME.
Attachment handling is explicitly the caller's responsibility: "Creating a message with an attachment is like creating any other message, but the process of uploading the file as a multi-part MIME message depends on the programming language" ([sending guide](https://developers.google.com/workspace/gmail/api/guides/sending)).

### Size limits

The prose docs do not state the API-level limit.
The machine-readable discovery document states it.
That document is the authoritative description of the same API.
Google serves it at `https://gmail.googleapis.com/$discovery/rest?version=v1`.
On 2026-09-07 it listed these limits:

| Method | `mediaUpload.maxSize` | Value |
| --- | --- | --- |
| `users.messages.send` | 36700160 | 35 MiB exactly |
| `users.drafts.create`, `users.drafts.send`, `users.drafts.update` | 36700160 | 35 MiB exactly |
| `users.messages.insert` | 157286400 | 150 MiB exactly |
| `users.messages.import` | 157286400 | 150 MiB exactly |

The 150 MB figure for `import` is also in the prose ([users.messages.import](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import)).
The `accept` list for all four is `message/*`.
The uploads guide names `message/rfc822` ([uploads guide](https://developers.google.com/workspace/gmail/api/guides/uploads)).

There is no hard threshold at which a multipart upload becomes mandatory.
The uploads guide describes three upload types ([uploads guide](https://developers.google.com/workspace/gmail/api/guides/uploads)).
Simple upload, with `uploadType=media`, is "For quick transfer of smaller files, for example, 5 MB or less".
Multipart upload, with `uploadType=multipart`, is for sending metadata alongside the data.
Resumable upload, with `uploadType=resumable`, is "For reliable transfer, especially important with larger files".
That 5 MB is advice about reliability, not a boundary the server enforces.
The boundary the server enforces is 35 MiB.
A resumable upload URI "expires after one week".

Account limits are lower than the API limit.
Google also measures them differently.

- Personal Gmail has a 25 MB limit.
  "If your total attachment size is greater than the limit, Gmail automatically removes the attachment and adds it as a Google Drive link in the email" ([Gmail help](https://support.google.com/mail/answer/6584)).
- Google Workspace sets a sending limit of 25 MB for Business, Education and Enterprise Standard, and up to 50 MB for Enterprise Plus (web only).
  "These values are the limits on the total size of the message content and attachments before encoding" ([sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace)).
- Google Workspace sets a receiving limit of 50 MB (Enterprise Standard) or 70 MB (Enterprise Plus).
  "These values are the limit after encoding, which adds about a 37% increase" ([receiving limits](https://knowledge.workspace.google.com/admin/gmail/gmail-receiving-limits-in-google-workspace)).

The send limit is pre-encoding and the receive limit is post-encoding.
Google states both explicitly, on adjacent pages.
Both pages use the same word, "values".
That asymmetry is real and easy to get wrong.

25 MB pre-encoding grows to about 34 MB post-encoding.
That fits under the 35 MiB API cap.
So in practice the API cap is rarely the binding constraint.

### Errors

Gmail's error guide documents 400, 401, 403, 404, 429, 500, 502, 503 and 504.
It mentions "The attachment is invalid" under 400.
It documents no size-specific error and no 413 ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)).
The usage-limits page covers quota units and a 500-recipient cap, not bytes ([usage limits](https://developers.google.com/workspace/gmail/api/reference/quota)).

## Microsoft Graph

### JSON representation

Graph does not accept a MIME tree on the JSON path.
It accepts a flat array of attachment objects.
A file attachment is `{"@odata.type": "#microsoft.graph.fileAttachment", "name": ..., "contentBytes": ...}`.
`name` and `contentBytes` are the required properties ([fileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment)).
`contentBytes` is `Edm.Binary`.
The docs describe it as "The base64-encoded contents of the file".
They add the note "Make sure to encode the file content in base64 before assigning it to **contentBytes**".
`size` is "The size in bytes of the attachment" and is `Int32`.

The `sendMail` call can include these attachments: "When using JSON format, you can include a [file attachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment) in the same **sendMail** action call" ([sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)).

Graph also accepts raw MIME.
Set `Content-Type: text/plain` and put the whole MIME message, base64-encoded, in the request body ([sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)).
For malformed input, Graph returns `400` with code `ErrorMimeContentInvalidBase64String` and message "Invalid base64 string for MIME content."
Raw MIME looks like a way for Epistole to use one MIME builder for all three backends.
It is not usable at any size, for two reasons.
The 4 MB request cap still applies.
The attachment bytes are also base64-encoded twice: once inside the MIME part, once around the whole message.
A 2 MB file becomes roughly 2.7 MB of MIME and roughly 3.7 MB of request body.

### The 3 MB threshold and why it exists

"Using the Microsoft Graph API, you can attach files up to 150 MB to an Outlook message or event item" ([large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)).
The same page splits attachments by size:

- Under 3 MB, it says to "do a single POST on the **attachments** navigation property of the Outlook item".
- Between 3 MB and 150 MB, it says to "create an upload session, and iteratively use `PUT` to upload ranges of bytes of the file until you have uploaded the entire file".

The add-attachment reference states it directly: "This operation limits the size of the attachment you can add to under 3 MB" ([add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments)).

A different page gives the reason and settles the before-or-after-encoding question for Graph ([use the API](https://learn.microsoft.com/en-us/graph/use-the-api)):

> Write requests in the Microsoft Graph API have a size limit of 4 MB.
>
> In some cases, the actual write request size limit is lower than 4 MB.
> For example, attaching a file to a user event by `POST /me/events/{id}/attachments` has a request size limit of 3 MB, because a file around 3.5 MB can become larger than 4 MB when encoded in base64.
>
> Requests exceeding the size limit fail with the status code HTTP 413, and the error message "Request entity too large" or "Payload too large".

So the 3 MB figure is a per-file, pre-encoding number.
Microsoft chose it so that the post-encoding request stays under a 4 MB post-encoding cap.
The failure above it is HTTP 413, not a mail-specific error.

The 4 MB cap applies to the whole request.
Several small attachments in one `sendMail` call count toward it together, along with the body and headers.
So Epistole should check the encoded total, not each attachment in isolation.

The one documented Graph error specific to attachment size is for a file that is too small.
`ErrorAttachmentSizeShouldNotBeLessThanMinimumSize` "is returned when attempting to create an upload session to attach a file smaller than 3 MB" ([large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)).
So Epistole cannot use the upload session for every attachment.
Below 3 MB, creating one returns this error.

### The large-file sequence

`createUploadSession` needs a message that already exists, because it posts to `/me/messages/{id}/attachments/createUploadSession` ([createUploadSession](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession)).
Both documented examples use a draft message.
The response contains an opaque pre-authenticated `uploadUrl` in the `outlook.office.com` domain, with an embedded token.
It also contains `expirationDateTime` and `nextExpectedRanges`.
Each `PUT` has `Content-Type: application/octet-stream`, a `Content-Length`, and a `Content-Range` of the form `bytes {start}-{end}/{total}`.
It has no `Authorization` header.
"For better performance, keep each byte range less than 4 MB", and "You must upload bytes in a file in order."
The final `PUT` returns `201 Created` with a `Location` header containing the attachment ID.

The sequence has two consequences for Epistole.

First, the flow becomes create-draft, upload, send-draft.
That is a different endpoint, a different number of round trips, and a different permission (`Mail.ReadWrite` rather than `Mail.Send`).

Second, Microsoft documents a known issue.
"An app with delegated permissions returns `HTTP 403 Forbidden` when attempting to attach large files to an Outlook message or event that is in a shared or delegated mailbox.
With delegated permissions, createUploadSession succeeds only if the message or event is in the signed-in user's mailbox" ([known issues](https://learn.microsoft.com/en-us/graph/known-issues)).
Sending from a shared mailbox with a large attachment does not work with delegated permissions.

### Tenant limits

Exchange Online caps the delivered message, independently of the API ([Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits)):

> The default maximum message size for Microsoft mailboxes is 35 MB for sending and 36 MB for receiving.
> Microsoft administrators can specify a custom limit between 1 MB and 150 MB.

The same page adds a caveat about routing:

> You can send and receive up to 150 MB messages between users (where the message never leaves the Microsoft datacenters).
> Messages that are routed outside of the Microsoft datacenters are subject to an additional 33% translation encoding increase, in which case the maximum message size is 112 MB.

Microsoft says 33 percent where Google says 37 percent.
Microsoft quotes the raw base64 ratio.
Google includes the line breaks.
Both describe the same expansion.
Google's arithmetic is safer.

The `createUploadSession` reference repeats the tenant default: "By default, this message size limit is 35 MB."
So on a default tenant, the attachment API accepts a 150 MB attachment and transport then rejects it.
Those are two different limits with two different failure points.
Only the first one fails fast.

## Inline images

### MIME, so SMTP and Gmail

Mark the part `Content-Disposition: inline`, because "A bodypart should be marked \`inline' if it is intended to be displayed automatically upon display of the message" ([RFC 2183](https://datatracker.ietf.org/doc/html/rfc2183)).
Give it a `Content-ID` header.
Its value is a `msg-id` and must be "world-unique" ([RFC 2045](https://datatracker.ietf.org/doc/html/rfc2045)).
Put it in a `multipart/related` alongside the HTML that references it ([RFC 2387](https://datatracker.ietf.org/doc/html/rfc2387)).

The HTML references it with a `cid:` URL.
The mapping is exact ([RFC 2392](https://datatracker.ietf.org/doc/html/rfc2392)):

> A "cid" URL is converted to the corresponding Content-ID message header by removing the "cid:" prefix, converting the % encoded character to their equivalent US-ASCII characters, and enclosing the remaining parts with an angle bracket pair, "<" and ">".
> For example, "cid:<foo4%25foo1@bar.net>" corresponds to
>
> `Content-ID: <foo4%25foo1@bar.net>`

So the header has brackets and the URL does not.
Any character in the Content-ID that is not URL-safe "must be hex-encoded using the %hh escape mechanism".

Python does not manage the brackets.
Verified locally: `set_content(..., cid="bare-id")` writes `Content-ID: bare-id`, with no brackets added.
Epistole must add them.

### Graph

Set `isInline: true` and `contentId` on the attachment.
The `attachmentItem` reference is the clearest statement of the format ([attachmentItem](https://learn.microsoft.com/en-us/graph/api/resources/attachmentitem)):

> contentId: The CID or Content-Id of the attachment for referencing for the in-line attachments using the `<img src="cid:contentId">` tag in HTML messages.
> Optional.

The worked example confirms the bare form ([createUploadSession](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession)):

> For an inline attachment, set _isInline_ property to `true` and use the _contentId_ property to specify a CID for the attachment as shown below.
> In the body of the draft message, use the same CID value to indicate the position where you want to include the attachment using a CID HTML reference tag, for example `<img src="cid:my_inline_picture">`.

The request body in that example is `"contentId": "my_inline_picture"`, with no angle brackets.
The body reference is `cid:my_inline_picture`.
So Graph's `contentId` holds the bare addr-spec, exactly what goes after `cid:` in the HTML.
That matches the URL side of RFC 2392.
It is the opposite of the MIME header side.

Graph's example also uses a Content-ID with no `@domain` part.
RFC 2045 specifies a `msg-id`, which has an addr-spec shape.
Graph does not enforce that.

### Does `cid:` resolve identically on all three?

For SMTP and Gmail it does, by construction.
Both send the identical MIME bytes Epistole produces.
So the recipient's client receives the same `multipart/related`, the same `Content-ID` and the same `cid:` reference.

For Graph, the HTML side is identical: the same `cid:value` reference works.
Epistole does not control the MIME side.
Graph accepts the attachment as a flat list entry.
Exchange serializes the message to MIME later, in transport step 3.
In that step, "the transport process serializes the message properties to construct MIME content" ([send mail process](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)).
Microsoft does not document whether the result is a `multipart/related`, where Exchange places the inline part relative to the `multipart/alternative`, or whether the emitted `Content-ID` matches the `contentId` verbatim.
I could not verify this from primary sources.
Confirming it needs a live send and an inspection of the received message.

## Content types, filenames and non-ASCII

### Content-type detection

Python's `mimetypes.guess_type` returns `None` for an unknown extension.
Verified locally: `a.png` gives `image/png`, `a.docx` gives `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `a.unknownext` gives `None`.
Epistole must supply a fallback.
`application/octet-stream` is the conventional one.
`set_content` requires an explicit `maintype` and `subtype` for `bytes` anyway ([contentmanager docs](https://docs.python.org/3/library/email.contentmanager.html)).

Graph's `contentType` is optional.
Graph fills it in from the content.
In the documented example, the request posts `{"name": "smile", "contentBytes": "R0lGODdhEAYEAA7"}` with no `contentType`.
The `201` response contains `"contentType": "image/gif"` ([add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments)).
The name `smile` has no extension, so Graph sniffed the bytes, not the name.
This is a behavioural difference between the backends.
If Epistole always sends an explicit `contentType`, the three backends use the same content type.
If it omits it, Graph may set a different content type from the one Epistole would have guessed.

### Filename encoding

The `filename` parameter is advisory ([RFC 2183](https://datatracker.ietf.org/doc/html/rfc2183)): "It is important that the receiving MUA not blindly use the suggested filename", and "The receiving MUA SHOULD NOT respect any directory path information that may seem to be present in the filename parameter.
The filename should be treated as a terminal component only."

RFC 2183 restricts the parameter to US-ASCII.
It refers to the successor mechanism.
That mechanism is RFC 2231.
It exists because the encoded-word form is not legal here ([RFC 2231](https://datatracker.ietf.org/doc/html/rfc2231)):

> MIME headers, like the RFC 822 headers they often appear in, are limited to 7bit US-ASCII, and the encoded-word mechanisms of RFC 2047 are not available to parameter values.

RFC 2047 states the prohibition directly ([RFC 2047](https://datatracker.ietf.org/doc/html/rfc2047)):

> An 'encoded-word' MUST NOT be used in parameter of a MIME Content-Type or Content-Disposition field, or in any structured field body except within a 'comment' or 'phrase'.

Python applies RFC 2231 by default.
A local run on CPython 3.14.7 produces:

```text
Content-Disposition: attachment;
 filename*=utf-8''rapport-financi%C3%A9r-2024.pdf
```

Long non-ASCII names get RFC 2231 continuations as well:

```text
 filename*0*=utf-8''tr%C3%A8s-long-nom-de-fichier-avec-des-accents-%C3%A9;
 filename*1*=%C3%A0%C3%BC-et-beaucoup-de-caract%C3%A8res-2024-final.pdf
```

So for SMTP and Gmail, Epistole passes the filename through.
The stdlib handles the encoding.
Some older clients only decode the encoded-word form.
Emitting that form would violate RFC 2047.
The stdlib also has no supported way to emit it.
Epistole should not try.

### What Graph does with `name`

Graph takes `name` as a plain UTF-8 JSON string.
Sending it to Graph needs no parameter encoding.

Graph's own docs contradict each other about what `name` means.

| Source | Wording |
| --- | --- |
| [attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment) | "The attachment's file name." |
| [fileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment) | "The name representing the text that is displayed below the icon representing the embedded attachment and doesn't need to be the actual file name." |
| [attachmentItem](https://learn.microsoft.com/en-us/graph/api/resources/attachmentitem) | "The display name of the attachment. This can be a descriptive string and doesn't have to be the actual file name." |

Two of the three call it a display label.
The base resource calls it a filename.
Epistole should treat it as a filename anyway, for two reasons.
It is the only field available.
It is also what recipients see.
But Epistole should not assume a round-trip through Graph preserves an exact filename.

Microsoft does not document what Exchange emits into the MIME `filename` parameter for a non-ASCII `name`.
I could not verify it.
Confirming it needs a live send.

### One documentation inconsistency worth noting

The `fileAttachment` prose says base64.
OData `Edm.Binary` in JSON is standard base64.
The auto-generated Python snippets on both the [add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments) and [sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail) pages call `base64.urlsafe_b64decode`.
Standard and URL-safe base64 differ in two characters.
The two statements cannot both be right.
I could not verify which alphabet Graph accepts.
Epistole should use standard base64, matching the prose and the OData type.

## What makes a uniform attachment API hard

1. Graph requires a different call sequence above 3 MB.
   That sequence needs a broader OAuth scope.
   Epistole cannot hide this difference from the caller.
   Epistole cannot guarantee that `Mail.Send` alone is enough without also capping attachment size.
2. Graph cannot express MIME nesting.
   Any Epistole API shaped like a MIME tree is unimplementable on Graph.
   A flat list of attachment descriptions is the only shape that works everywhere.
3. Content-ID brackets differ between the MIME header and the Graph JSON field.
   Normalize at the boundary.
4. Epistole does not control Graph's inline rendering.
   Microsoft does not document it.
   Epistole can guarantee identical `cid:` references in the HTML but not identical MIME structure.
5. The size limits apply to two different quantities, depending on the limit.
   Microsoft and Google also state the expansion factor differently (33 versus 37 percent).
   Epistole needs both the raw and encoded byte counts.
6. Graph's 4 MB cap applies to the whole request.
   So Epistole must check attachments together, not individually.
7. Each backend has two limits: an API limit and an account or tenant limit.
   Only the API limit fails fast.
   On a default 35 MB tenant, Graph's upload session accepts a 100 MB attachment and the message then bounces in transport.
8. Python's `filename` keyword silently overrides `add_related`'s inline default.
   This is a real bug source, not a theoretical one.
9. `mimetypes.guess_type` returns `None` for unknown extensions.
   Graph sniffs content rather than filenames.
   Always send an explicit content type.
10. Three Graph pages document `name` three different ways.
    Graph does not guarantee a filename round-trip.

## Not verified

These need a live send against each provider, or a source I could not find.

- Whether Graph emits `multipart/related` for `isInline` attachments, and where it places them relative to `multipart/alternative`.
- Whether the `Content-ID` Exchange emits matches the `contentId` submitted, verbatim.
- What Exchange writes into the MIME `filename` parameter for a non-ASCII Graph `name`.
- Whether Graph accepts standard base64, URL-safe base64, or both in `contentBytes`.
- Whether Gmail preserves a submitted MIME tree byte-for-byte, or normalizes it.
  Google documents no guarantee either way.
- Whether the Gmail API returns a distinct error for an over-limit message, or a generic 400.
  The error guide documents no size-specific error.
- Whether Graph's `sendMail` `attachments` array is subject to the same explicit "under 3 MB" wording as `POST /messages/{id}/attachments`.
  The 4 MB request cap certainly applies.
  Microsoft documents the 3 MB per-file wording only for the attachments navigation property.

## Sources

- [RFC 1870, SMTP Service Extension for Message Size Declaration](https://datatracker.ietf.org/doc/html/rfc1870)
- [RFC 2045, MIME Part One: Format of Internet Message Bodies](https://datatracker.ietf.org/doc/html/rfc2045)
- [RFC 2046, MIME Part Two: Media Types](https://datatracker.ietf.org/doc/html/rfc2046)
- [RFC 2047, MIME Part Three: Message Header Extensions for Non-ASCII Text](https://datatracker.ietf.org/doc/html/rfc2047)
- [RFC 2183, Communicating Presentation Information: the Content-Disposition Header Field](https://datatracker.ietf.org/doc/html/rfc2183)
- [RFC 2231, MIME Parameter Value and Encoded Word Extensions](https://datatracker.ietf.org/doc/html/rfc2231)
- [RFC 2387, The MIME Multipart/Related Content-type](https://datatracker.ietf.org/doc/html/rfc2387)
- [RFC 2392, Content-ID and Message-ID Uniform Resource Locators](https://datatracker.ietf.org/doc/html/rfc2392)
- [Python, email.message.EmailMessage](https://docs.python.org/3/library/email.message.html)
- [Python, email.contentmanager](https://docs.python.org/3/library/email.contentmanager.html)
- [Gmail API, sending guide](https://developers.google.com/workspace/gmail/api/guides/sending)
- [Gmail API, uploads guide](https://developers.google.com/workspace/gmail/api/guides/uploads)
- [Gmail API, users.messages resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages)
- [Gmail API, users.messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)
- [Gmail API, users.messages.import](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import)
- [Gmail API, error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)
- [Gmail API, usage limits](https://developers.google.com/workspace/gmail/api/reference/quota)
- [Gmail API, v1 discovery document](https://gmail.googleapis.com/$discovery/rest?version=v1)
- [Gmail help, send attachments](https://support.google.com/mail/answer/6584)
- [Google Workspace, Gmail sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace)
- [Google Workspace, Gmail receiving limits](https://knowledge.workspace.google.com/admin/gmail/gmail-receiving-limits-in-google-workspace)
- [Microsoft Graph, attachment resource](https://learn.microsoft.com/en-us/graph/api/resources/attachment)
- [Microsoft Graph, fileAttachment resource](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment)
- [Microsoft Graph, attachmentItem resource](https://learn.microsoft.com/en-us/graph/api/resources/attachmentitem)
- [Microsoft Graph, add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments)
- [Microsoft Graph, attachment createUploadSession](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession)
- [Microsoft Graph, user sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)
- [Microsoft Graph, attach large files to Outlook messages or events](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)
- [Microsoft Graph, use the API](https://learn.microsoft.com/en-us/graph/use-the-api)
- [Microsoft Graph, send mail process](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)
- [Microsoft Graph, known issues](https://learn.microsoft.com/en-us/graph/known-issues)
- [Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits)

# Attachment and inline-image rules across the three backends

Research for [issue #4](https://github.com/ozanozbeker/herma/issues/4).
Primary sources only.
Every factual claim below carries a URL.
Where a claim comes from a live probe or a local run rather than a document, the text says so.

## What this means for herma's design

Two of the three backends speak MIME.
The third does not.
SMTP and the Gmail API both take a complete RFC 5322 message that herma builds with `email.message.EmailMessage`.
Microsoft Graph takes a flat JSON array of `fileAttachment` objects and builds the MIME itself inside Exchange.
So herma's attachment API has to be a description of an attachment, not a MIME part.
An `Attachment` value object carrying `content: bytes`, `filename: str`, `content_type: str | None`, `inline: bool`, and `content_id: str | None` maps cleanly onto all three.
A MIME-tree-shaped API does not, because Graph has no way to express nesting.

Size is where the uniformity breaks.
Graph forces a different call sequence above 3 MB, and that sequence needs a different OAuth permission.
`sendMail` needs `Mail.Send`.
`createUploadSession` needs `Mail.ReadWrite` ([sendMail permissions](https://learn.microsoft.com/en-us/graph/api/user-sendmail), [createUploadSession permissions](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession)).
An app that only ever attaches small files can be granted the narrower scope.
That is user-visible, so herma should document it rather than hide it.

Check size before encoding, and derive the encoded size arithmetically.
Both numbers are needed, and neither requires actually encoding the payload.
Graph's 3 MB threshold is measured on the raw file bytes.
Gmail's 25 MB account limit is measured before encoding.
The SMTP `SIZE` value, Graph's 4 MB request cap, and the Gmail API's 35 MiB upload cap are all measured after encoding.
For base64 the encoded size is `4 * ceil(n / 3)` characters, wrapped at 76 characters per line ([RFC 2045](https://datatracker.ietf.org/doc/html/rfc2045)).
With CRLF line endings that is `1.3333 * 78/76`, or about 1.37x.
That is exactly the "about a 37% increase" Google quotes ([Gmail receiving limits](https://knowledge.workspace.google.com/admin/gmail/gmail-receiving-limits-in-google-workspace)), and it is the number herma should use, not a flat 33 percent.

Content-ID needs normalizing at the boundary.
MIME wants angle brackets in the header.
Graph wants the bare value in JSON.
The `cid:` reference in the HTML body is bare in all three cases.
Store the bare form internally and add brackets only when writing a MIME header.

## Comparison table

| Aspect | SMTP (stdlib MIME) | Gmail API | Microsoft Graph |
| --- | --- | --- | --- |
| Attachment representation | MIME body part | MIME body part inside `raw` | `fileAttachment` JSON object |
| Wire encoding | base64 body, 76-char lines | whole message base64url in `raw` | file base64 in `contentBytes` |
| Nesting under app control | yes | yes | no, Exchange builds the MIME |
| Small-file path | one `sendmail()` | one `messages.send` | `sendMail` with `attachments` array |
| Large-file path | same call, subject to `SIZE` | same call, up to the upload cap | draft, `createUploadSession`, ranged `PUT`, then send |
| Hard threshold that changes the call | none | none (upload style is a recommendation) | 3 MB |
| Transport ceiling | server-advertised `SIZE` | 36700160 bytes (35 MiB) for `messages.send` | 4 MB per write request |
| Account or tenant ceiling | server policy | 25 MB send (Workspace and personal) | 35 MB default, 1 MB to 150 MB configurable |
| Ceiling measured | after encoding | 35 MiB after, 25 MB before | 4 MB after, 3 MB before |
| Inline marker | `Content-Disposition: inline` | same | `isInline: true` |
| Inline identifier | `Content-ID: <value>` | same | `contentId: "value"`, no brackets |
| Container for inline images | `multipart/related` | same | not expressible, Exchange decides |
| Filename field | `filename` parameter, RFC 2231 encoded | same | `name`, plain UTF-8 JSON string |
| Content type | set by caller | set by caller | optional, Graph sniffs the bytes |
| Documented oversize failure | SMTP `552` or `452` | none documented | HTTP 413 |

## SMTP and the Python stdlib

### MIME representation

An attachment is a MIME body part.
`EmailMessage.add_attachment` builds the part and attaches it, promoting the message to `multipart/mixed` first if needed ([docs](https://docs.python.org/3/library/email.message.html)).
`add_related` promotes to `multipart/related`, and `add_alternative` promotes to `multipart/alternative`.
Each raises `TypeError` if the message is already a multipart of the wrong subtype, so the order of calls matters.

`add_attachment` sets `Content-Disposition: attachment` when the part has no such header.
`add_related` sets `Content-Disposition: inline` when the part has no such header ([docs](https://docs.python.org/3/library/email.message.html)).

There is a trap here.
`raw_data_manager.set_content` sets the disposition itself: "If _disposition_ is set, use it as the value of the _Content-Disposition_ header.
If not specified, and _filename_ is specified, add the header with the value `attachment`" ([contentmanager docs](https://docs.python.org/3/library/email.contentmanager.html)).
Because the header is then already present, `add_related` leaves it alone.
Verified locally on CPython 3.14.7: `add_related(data, maintype="image", subtype="png", cid="<a@b>", filename="logo.png")` produces `Content-Disposition: attachment; filename="logo.png"`.
Passing `disposition="inline"` explicitly restores the intended value. herma must pass `disposition="inline"` whenever it passes both `filename` and `cid`, or inline images arrive as ordinary attachments.

For `bytes` payloads, `maintype` and `subtype` are required or `set_content` raises `TypeError`, and the transfer encoding defaults to base64 ([contentmanager docs](https://docs.python.org/3/library/email.contentmanager.html)).

### Structure for an HTML mail with an inline image and a file attachment

`multipart/alternative` orders its parts "in increasing order of preference, that is, with the preferred format last" ([RFC 2046](https://datatracker.ietf.org/doc/html/rfc2046)), so the plain-text part goes first.
The inline image belongs in a `multipart/related` wrapped around the HTML part, not around the whole message, because `multipart/related` groups "objects that are aggregates of related MIME body parts" and its root is the first part unless a `start` parameter says otherwise ([RFC 2387](https://datatracker.ietf.org/doc/html/rfc2387)).
The file attachment goes at the `multipart/mixed` level.

Verified locally, this call order produces the right tree:

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

SMTP advertises its ceiling through the `SIZE` service extension ([RFC 1870](https://datatracker.ietf.org/doc/html/rfc1870)).
The EHLO keyword takes "a decimal number indicating the fixed maximum message size in bytes that the server will accept".
"A parameter value of 0 (zero) indicates that no fixed maximum message size is in force", and if the parameter is omitted "no information is conveyed about the server's fixed maximum message size".
A client may declare the size up front with `MAIL FROM ... SIZE=n`.
If it is too large the server replies "552 message size exceeds fixed maximium message size"; if the server is merely out of room right now it replies "452 insufficient system storage".

`smtplib.SMTP.esmtp_features["size"]` exposes the advertised value after `ehlo()`.
Live probe on 2026-09-07 from this machine:

| Host | Advertised `SIZE` | Bytes |
| --- | --- | --- |
| `smtp.gmail.com:587` | 35882577 | about 34.2 MiB |
| `smtp-mail.outlook.com:587` | 157286400 | 150 MiB exactly |
| `smtp.office365.com:587` | 157286400 | 150 MiB exactly |

The `SIZE` value covers the message as transmitted, so it is a post-encoding number.
Gmail's 35882577 divided by 1.37 is about 26.2 MB, which is where a 25 MB pre-encoding limit lands after base64 plus line breaks.

herma should read `esmtp_features["size"]` and refuse locally before writing the message, rather than discovering the ceiling from a 552.

## Gmail API

### Raw MIME representation

The Gmail API takes a whole MIME message.
The `raw` field is "The entire email message in an RFC 2822 formatted and base64url encoded string" ([users.messages resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages), confirmed verbatim in the [v1 discovery document](https://gmail.googleapis.com/$discovery/rest?version=v1)).
"Gmail messages are sent as base64URL encoded strings within the `raw` field of a `messages` resource" ([sending guide](https://developers.google.com/workspace/gmail/api/guides/sending)).

So Gmail and SMTP share the same construction path.
Anything herma can express in MIME, it can send through Gmail.
Attachment handling is explicitly the caller's problem: "Creating a message with an attachment is like creating any other message, but the process of uploading the file as a multi-part MIME message depends on the programming language" ([sending guide](https://developers.google.com/workspace/gmail/api/guides/sending)).

### Size limits

The API-level ceiling is not stated in the prose docs.
It is stated in the machine-readable discovery document that Google serves at `https://gmail.googleapis.com/$discovery/rest?version=v1`, which is the authoritative description of the same API.
Retrieved 2026-09-07:

| Method | `mediaUpload.maxSize` | Value |
| --- | --- | --- |
| `users.messages.send` | 36700160 | 35 MiB exactly |
| `users.drafts.create`, `users.drafts.send`, `users.drafts.update` | 36700160 | 35 MiB exactly |
| `users.messages.insert` | 157286400 | 150 MiB exactly |
| `users.messages.import` | 157286400 | 150 MiB exactly |

The 150 MB figure for `import` is also in the prose ([users.messages.import](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import)).
The `accept` list for all four is `message/*`; the uploads guide names `message/rfc822` ([uploads guide](https://developers.google.com/workspace/gmail/api/guides/uploads)).

There is no hard threshold at which a multipart upload becomes mandatory.
The uploads guide describes simple upload with `uploadType=media` as being "For quick transfer of smaller files, for example, 5 MB or less", multipart upload with `uploadType=multipart` for sending metadata alongside the data, and resumable upload with `uploadType=resumable` "For reliable transfer, especially important with larger files" ([uploads guide](https://developers.google.com/workspace/gmail/api/guides/uploads)).
That 5 MB is advice about reliability, not a boundary the server enforces.
The boundary the server enforces is 35 MiB.
A resumable upload URI "expires after one week".

Account limits are lower than the API limit, and they are measured differently.

- Personal Gmail: 25 MB.
  "If your total attachment size is greater than the limit, Gmail automatically removes the attachment and adds it as a Google Drive link in the email" ([Gmail help](https://support.google.com/mail/answer/6584)).
- Google Workspace sending: 25 MB for Business, Education and Enterprise Standard, up to 50 MB for Enterprise Plus (web only).
  "These values are the limits on the total size of the message content and attachments before encoding" ([sending limits](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace)).
- Google Workspace receiving: 50 MB (Enterprise Standard) or 70 MB (Enterprise Plus).
  "These values are the limit after encoding, which adds about a 37% increase" ([receiving limits](https://knowledge.workspace.google.com/admin/gmail/gmail-receiving-limits-in-google-workspace)).

The send limit is pre-encoding and the receive limit is post-encoding.
Google states both explicitly, on adjacent pages, using the same word "values".
That asymmetry is real and easy to get wrong.

25 MB pre-encoding grows to about 34 MB post-encoding, which fits under the 35 MiB API cap.
So the API cap will rarely be the binding constraint in practice.

### Errors

Gmail's error guide documents 400, 401, 403, 404, 429, 500, 502, 503 and 504, and mentions "The attachment is invalid" under 400.
It documents no size-specific error and no 413 ([error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors)).
The usage-limits page covers quota units and a 500-recipient cap, not bytes ([usage limits](https://developers.google.com/workspace/gmail/api/reference/quota)).

## Microsoft Graph

### JSON representation

Graph does not accept a MIME tree on the JSON path.
It accepts a flat array of attachment objects.
A file attachment is `{"@odata.type": "#microsoft.graph.fileAttachment", "name": ..., "contentBytes": ...}`, and `name` and `contentBytes` are the required properties ([fileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment)).
`contentBytes` is `Edm.Binary`, documented as "The base64-encoded contents of the file", with the note "Make sure to encode the file content in base64 before assigning it to **contentBytes**".
`size` is "The size in bytes of the attachment" and is `Int32`.

These attachments can ride along in the `sendMail` call: "When using JSON format, you can include a [file attachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment) in the same **sendMail** action call" ([sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)).

Graph also accepts raw MIME.
Set `Content-Type: text/plain` and put the whole MIME message, base64-encoded, in the request body ([sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail)).
Malformed input returns `400` with code `ErrorMimeContentInvalidBase64String` and message "Invalid base64 string for MIME content."
This looks like an escape hatch that would let herma use one MIME builder for all three backends.
It is not a usable one at any size, because the 4 MB request cap still applies and the payload now carries base64 twice: once inside the MIME part, once around the whole message.
A 2 MB file becomes roughly 2.7 MB of MIME and roughly 3.7 MB of request body.

### The 3 MB threshold and why it exists

"Using the Microsoft Graph API, you can attach files up to 150 MB to an Outlook message or event item" ([large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)).
The split:

- Under 3 MB: "do a single POST on the **attachments** navigation property of the Outlook item".
- Between 3 MB and 150 MB: "create an upload session, and iteratively use `PUT` to upload ranges of bytes of the file until you have uploaded the entire file".

The add-attachment endpoint states it directly: "This operation limits the size of the attachment you can add to under 3 MB" ([add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments)).

The reason is stated on a different page, and it settles the before-or-after-encoding question for Graph ([use the API](https://learn.microsoft.com/en-us/graph/use-the-api)):

> Write requests in the Microsoft Graph API have a size limit of 4 MB.
>
> In some cases, the actual write request size limit is lower than 4 MB.
> For example, attaching a file to a user event by `POST /me/events/{id}/attachments` has a request size limit of 3 MB, because a file around 3.5 MB can become larger than 4 MB when encoded in base64.
>
> Requests exceeding the size limit fail with the status code HTTP 413, and the error message "Request entity too large" or "Payload too large".

So the 3 MB figure is a per-file, pre-encoding number, chosen so that the post-encoding request stays under a 4 MB post-encoding cap.
The failure above it is HTTP 413, not a mail-specific error.

The 4 MB cap is on the whole request.
Several small attachments in one `sendMail` call sum against it, along with the body and headers. herma should therefore budget the encoded total, not check each attachment in isolation.

The one documented Graph error specific to attachment size goes the other way.
`ErrorAttachmentSizeShouldNotBeLessThanMinimumSize` "is returned when attempting to create an upload session to attach a file smaller than 3 MB" ([large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)).
The upload session is not a universal path that herma can always take.
Below 3 MB it is an error.

### The large-file sequence

`createUploadSession` posts to `/me/messages/{id}/attachments/createUploadSession`, so it needs a message that already exists ([createUploadSession](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession)).
Both documented examples use a draft message.
The response carries an opaque pre-authenticated `uploadUrl` in the `outlook.office.com` domain with an embedded token, plus `expirationDateTime` and `nextExpectedRanges`.
Each `PUT` sends `Content-Type: application/octet-stream`, a `Content-Length`, and a `Content-Range` of the form `bytes {start}-{end}/{total}`, with no `Authorization` header.
"For better performance, keep each byte range less than 4 MB", and "You must upload bytes in a file in order."
The final `PUT` returns `201 Created` with a `Location` header containing the attachment ID.

Two consequences for herma.

First, the flow becomes create-draft, upload, send-draft.
That is a different endpoint, a different number of round trips, and a different permission (`Mail.ReadWrite` rather than `Mail.Send`).

Second, there is a documented hole.
"An app with delegated permissions returns `HTTP 403 Forbidden` when attempting to attach large files to an Outlook message or event that is in a shared or delegated mailbox.
With delegated permissions, createUploadSession succeeds only if the message or event is in the signed-in user's mailbox" ([known issues](https://learn.microsoft.com/en-us/graph/known-issues)).
Sending from a shared mailbox with a large attachment does not work on the delegated path.

### Tenant ceilings

Exchange Online caps the delivered message, independently of the API ([Exchange Online limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits)):

> The default maximum message size for Microsoft mailboxes is 35 MB for sending and 36 MB for receiving.
> Microsoft administrators can specify a custom limit between 1 MB and 150 MB.

The same page adds a caveat about routing:

> You can send and receive up to 150 MB messages between users (where the message never leaves the Microsoft datacenters).
> Messages that are routed outside of the Microsoft datacenters are subject to an additional 33% translation encoding increase, in which case the maximum message size is 112 MB.

Note that Microsoft says 33 percent where Google says 37 percent.
Microsoft is quoting the raw base64 ratio and Google is including the line breaks.
Both describe the same expansion.
The safer arithmetic is Google's.

The `createUploadSession` reference repeats the tenant default: "By default, this message size limit is 35 MB."
So a 150 MB attachment is accepted by the attachment API and then rejected by transport on a default tenant.
Those are two different ceilings with two different failure points, and only the first one fails fast.

## Inline images

### MIME, so SMTP and Gmail

Mark the part `Content-Disposition: inline`, because "A bodypart should be marked `inline' if it is intended to be displayed automatically upon display of the message" ([RFC 2183](https://datatracker.ietf.org/doc/html/rfc2183)). Give it a `Content-ID` header, whose value is a `msg-id` and must be "world-unique" ([RFC 2045](https://datatracker.ietf.org/doc/html/rfc2045)). Put it in a `multipart/related` alongside the HTML that references it ([RFC 2387](https://datatracker.ietf.org/doc/html/rfc2387)).

The HTML references it with a `cid:` URL.
The mapping is exact ([RFC 2392](https://datatracker.ietf.org/doc/html/rfc2392)):

> A "cid" URL is converted to the corresponding Content-ID message header by removing the "cid:" prefix, converting the % encoded character to their equivalent US-ASCII characters, and enclosing the remaining parts with an angle bracket pair, "<" and ">".
> For example, "cid:<foo4%25foo1@bar.net>" corresponds to
>
> `Content-ID: <foo4%25foo1@bar.net>`

So the header carries brackets and the URL does not.
Any character in the Content-ID that is not URL-safe "must be hex-encoded using the %hh escape mechanism".

Python does not manage the brackets.
Verified locally: `set_content(..., cid="bare-id")` writes `Content-ID: bare-id`, with no brackets added. herma must add them.

### Graph

Set `isInline: true` and `contentId` on the attachment.
The `attachmentItem` reference is the clearest statement of the format ([attachmentItem](https://learn.microsoft.com/en-us/graph/api/resources/attachmentitem)):

> contentId: The CID or Content-Id of the attachment for referencing for the in-line attachments using the `<img src="cid:contentId">` tag in HTML messages.
> Optional.

The worked example confirms the bare form ([createUploadSession](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession)):

> For an inline attachment, set _isInline_ property to `true` and use the _contentId_ property to specify a CID for the attachment as shown below.
> In the body of the draft message, use the same CID value to indicate the position where you want to include the attachment using a CID HTML reference tag, for example `<img src="cid:my_inline_picture">`.

The request body in that example is `"contentId": "my_inline_picture"`, with no angle brackets, and the body reference is `cid:my_inline_picture`.
So Graph's `contentId` holds the bare addr-spec, exactly what goes after `cid:` in the HTML.
That is the same convention as the URL side of RFC 2392, and the opposite of the MIME header side.

Note also that Graph's example uses a Content-ID with no `@domain` part.
RFC 2045 asks for a `msg-id`, which has an addr-spec shape.
Graph does not enforce that.

### Does `cid:` resolve identically on all three?

For SMTP and Gmail, yes by construction.
Both carry the identical MIME bytes herma produces, so the receiving client sees the same `multipart/related`, the same `Content-ID` and the same `cid:` reference.

For Graph, the HTML side is identical: the same `cid:value` reference works.
The MIME side is not under herma's control.
Graph accepts the attachment as a flat list entry; Exchange serializes the message to MIME later, in transport step 3, where "the transport process serializes the message properties to construct MIME content" ([send mail process](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)).
Microsoft does not document whether the result is a `multipart/related`, where the inline part lands relative to the `multipart/alternative`, or whether the emitted `Content-ID` matches the `contentId` verbatim.
I could not verify this from primary sources.
Confirming it needs a live send and an inspection of the received message.

## Content types, filenames and non-ASCII

### Content-type detection

Python's `mimetypes.guess_type` returns `None` for an unknown extension.
Verified locally: `a.png` gives `image/png`, `a.docx` gives `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `a.unknownext` gives `None`. herma must supply a fallback.
`application/octet-stream` is the conventional one, and `set_content` requires an explicit `maintype` and `subtype` for `bytes` anyway ([contentmanager docs](https://docs.python.org/3/library/email.contentmanager.html)).

Graph's `contentType` is optional, and Graph fills it in from the content.
In the documented example, the request posts `{"name": "smile", "contentBytes": "R0lGODdhEAYEAA7"}` with no `contentType`, and the `201` response comes back with `"contentType": "image/gif"` ([add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments)).
The name `smile` has no extension, so Graph sniffed the bytes, not the name.
That is a behavioural difference worth knowing: if herma always sends an explicit `contentType`, the three backends agree; if it omits it, Graph may disagree with what herma would have guessed.

### Filename encoding

The `filename` parameter is advisory ([RFC 2183](https://datatracker.ietf.org/doc/html/rfc2183)): "It is important that the receiving MUA not blindly use the suggested filename", and "The receiving MUA SHOULD NOT respect any directory path information that may seem to be present in the filename parameter.
The filename should be treated as a terminal component only."

RFC 2183 restricts the parameter to US-ASCII and points at the successor mechanism.
That mechanism is RFC 2231, and it exists precisely because the encoded-word hack is not legal here ([RFC 2231](https://datatracker.ietf.org/doc/html/rfc2231)):

> MIME headers, like the RFC 822 headers they often appear in, are limited to 7bit US-ASCII, and the encoded-word mechanisms of RFC 2047 are not available to parameter values.

RFC 2047 states the prohibition directly ([RFC 2047](https://datatracker.ietf.org/doc/html/rfc2047)):

> An 'encoded-word' MUST NOT be used in parameter of a MIME Content-Type or Content-Disposition field, or in any structured field body except within a 'comment' or 'phrase'.

Python does the right thing without being asked.
Verified locally on CPython 3.14.7:

```text
Content-Disposition: attachment;
 filename*=utf-8''rapport-financi%C3%A9r-2024.pdf
```

Long non-ASCII names get RFC 2231 continuations as well:

```text
 filename*0*=utf-8''tr%C3%A8s-long-nom-de-fichier-avec-des-accents-%C3%A9;
 filename*1*=%C3%A0%C3%BC-et-beaucoup-de-caract%C3%A8res-2024-final.pdf
```

So for SMTP and Gmail, herma passes the filename through and the stdlib handles the encoding.
Some older clients only understand the encoded-word form, but emitting it would violate RFC 2047, and the stdlib gives no supported way to do so. herma should not try.

### What Graph does with `name`

Graph takes `name` as a plain UTF-8 JSON string.
There is no parameter encoding to worry about on the way in.

Graph's own docs disagree about what `name` means.

| Source | Wording |
| --- | --- |
| [attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment) | "The attachment's file name." |
| [fileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment) | "The name representing the text that is displayed below the icon representing the embedded attachment and doesn't need to be the actual file name." |
| [attachmentItem](https://learn.microsoft.com/en-us/graph/api/resources/attachmentitem) | "The display name of the attachment. This can be a descriptive string and doesn't have to be the actual file name." |

Two of the three call it a display label.
The base resource calls it a filename. herma should treat it as a filename anyway, because that is the only field available and because it is what recipients will see, but it should not assume a round-trip through Graph preserves an exact filename.

What Exchange emits into the MIME `filename` parameter for a non-ASCII `name` is not documented.
I could not verify it.
Confirming it needs a live send.

### One documentation inconsistency worth noting

The `fileAttachment` prose says base64, and OData `Edm.Binary` in JSON is standard base64.
The auto-generated Python snippets on both the [add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments) and [sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail) pages call `base64.urlsafe_b64decode`.
Standard and URL-safe base64 differ in two characters.
The two statements cannot both be right.
I could not verify which alphabet Graph accepts. herma should use standard base64, matching the prose and the OData type.

## What makes a uniform attachment API hard

1. Graph forces a different call sequence above 3 MB, and that sequence needs a broader OAuth scope.
   This one leaks: herma cannot promise `Mail.Send` alone is enough without also capping attachment size.
2. Graph cannot express MIME nesting.
   Any herma API shaped like a MIME tree is unimplementable on Graph.
   A flat list of attachment descriptions is the only shape that works everywhere.
3. Content-ID brackets differ between the MIME header and the Graph JSON field.
   Normalize at the boundary.
4. Graph's inline rendering is not under herma's control and is not documented. herma can guarantee identical `cid:` references in the HTML but not identical MIME structure.
5. Size is measured against two different quantities depending on which limit you are checking, and the two backends state their expansion factor differently (33 versus 37 percent). herma needs both the raw and encoded byte counts.
6. Graph's 4 MB cap applies to the whole request, so attachments must be budgeted together, not individually.
7. There are two ceilings per backend, an API ceiling and an account or tenant ceiling, and only the API ceiling fails fast.
   A 100 MB attachment is accepted by Graph's upload session and then bounces in transport on a default 35 MB tenant.
8. Python's `filename` keyword silently overrides `add_related`'s inline default.
   This is a real bug source, not a theoretical one.
9. `mimetypes.guess_type` returns `None` for unknown extensions, and Graph sniffs content rather than filenames.
   Always send an explicit content type.
10. Graph `name` is documented three different ways across three pages.
    Filename round-trips through Graph are not guaranteed.

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
  The 4 MB request cap certainly applies; the 3 MB per-file wording is documented only for the attachments navigation property.

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

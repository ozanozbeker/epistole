# A caller passes an attachment as a path, bytes, or a binary file object

`.attach()` and `.embed()` take one positional source and nothing else positionally.
The source is a `Path`, a `bytes`, or an object with `.read()` returning `bytes`.
A `Path` supplies its own filename.
Every other source must be given a `filename=`.
The content type is inferred from that filename and falls back to `application/octet-stream`.
Every backend writes it explicitly in the format it sends.
Bytes are never sniffed.
A `str` is never read as a path.
`.embed()` adds an inline image under a content id that must be unused.
Decided on [#30](https://github.com/ozanozbeker/epistole/issues/30), which found the whole block in `docs/spec.md` citing [#11](https://github.com/ozanozbeker/epistole/issues/11) and ADR-0003, neither of which covers any of it.

## Why

**A `str` is the one input that means two things.**
`docs/research/prior-art.md` warns about strings that could mean two things.
ADR-0003 already rejected reading a local path out of `<img src>` on that ground.
`.attach("report.pdf")` reads as a filename to one caller and as content to another.
Python has no type that distinguishes them.
So passing a `str` raises `TypeError`, and the error message says to wrap it in `Path()`.
That is one word at the call site, and it removes the ambiguity for good.

**`bytearray` and `memoryview` raise because a `Message` is a closed value.**
ADR-0002 makes a message hold nothing that can change under it.
Both of those are live views of memory the caller still owns.
Accepting one would mean either copying it silently or storing it.
Copying silently hides the cost.
Storing lets a caller mutate bytes that an earlier send in the loop already sent.
`bytes` is immutable and hashable.
That also keeps `Attachment` hashable and ADR-0002's equality rule intact.
A caller holding a `bytearray` writes `bytes(buf)`.

**A text-mode file raises rather than encoding.**
A file from `open(path)` returns `str` from `.read()`.
Guessing an encoding to turn that into bytes is a decision about the recipient's message, and Epistole has no basis for it.
The fix is one character, `"rb"`, and the error says so.

**`.name` on a file object is not read, because it is usually the wrong name.**
`io.BytesIO` has none.
`tempfile.NamedTemporaryFile` has a temp path the recipient should never see.
`gzip.GzipFile.name` is the compressed file, not the member.
A filename Epistole guessed is a name the recipient reads, so the caller supplies it or the call fails.

**The content type is declared, never sniffed.**
Sniffing means a dependency (`filetype`, `python-magic`) and a guess at meaning.
ADR-0003 rejected that for `data:` payloads, and this ADR rejects it for the same reason.
`mimetypes.guess_type` on the filename is a lookup, not a guess: it reads the extension the caller wrote.
The fallback is `application/octet-stream` because RFC 2046 makes it the default.
Every client renders it as a file to download, which is the correct result for bytes nobody labelled.
Epistole does not accept media-type parameters.
A `content_type=` of `text/csv; charset=utf-8` is a `ValueError`, not a value Epistole must handle in three backend formats.
The content type is written explicitly on every backend, because without it the receiving client guesses instead.

**`.embed()` is a second method, not a flag on `.attach()`.**
An inline image has two requirements an attachment does not.
Its content type must be `image/*`, and the HTML must be able to name it by a content id.
A `.attach(inline=True)` would hold both as runtime conditions on a flag.
The signature would then stop describing what the call needs.
With two methods, `cid=` appears only on the method that needs it, and `.attach()`'s signature stays accurate.

**A content id already in use is a `ValueError`, with no exception for identical bytes.**
`CONTEXT.md` says a content id is unique within one message.
`cid` defaults to the filename, so `.embed(Path("a/logo.png")).embed(Path("b/logo.png"))` is the ordinary way to break that rule.
Two images under one id cannot both be resolved, whatever they hold.
So the rule has no special case.
The rewrite in ADR-0003 runs at construction, and `.embed()` runs after it.
So a caller who names an id the rewrite generated gets the same error.
This does not amend ADR-0002's append rule.
`.embed()` still appends, and it raises only on an append that would be unresolvable.

## Rules

- **`source` is `Path`, `bytes`, or a binary file object with `.read()`.**
  `str` is a `TypeError` naming `Path()`.
  `bytearray`, `memoryview`, and a text-mode file are each a `TypeError`.
- **Bytes are read when the method is called.**
  A file object is read once and left open for the caller (ADR-0002).
- **A `Path` supplies its own filename, and every other source needs `filename=`.**
  Its absence is a `TypeError`.
  `.name` on a file object is never read.
- **The content type is inferred from the filename and falls back to `application/octet-stream`.**
  `content_type=` overrides the inference.
  A media type with parameters is a `ValueError`.
  The type is written explicitly on SMTP, Gmail, and Graph alike.
  Bytes are never inspected.
- **`.embed()` defaults `filename` and `cid` to each other**, so `.embed(Path("logo.png"))` matches `<img src="cid:logo.png">`.
  Supplying neither, with a source that is not a `Path`, is a `TypeError`.
- **`.embed()` requires an `image/*` content type** after inference or override, and raises `ValueError` otherwise.
- **A content id already held is a `ValueError`** that names the id.
  This includes one the `data:` rewrite generated at construction.
- **`Attachment` is a frozen dataclass**: `filename`, `content_type`, `data`, `content_id`.
  `content_id` is `None` on an attachment and set on an inline image.
- **`attachments` holds what `.attach()` added, and `inline_images` holds what `.embed()` added and what the rewrite made**, each in insertion order.
  Neither name takes ADR-0007's underscore, because no method uses that name.
- **No method removes anything.**
  ADR-0002's rule holds here with no addition: a message without an attachment is built without it.

## Considered options

- **Accept `str` as a path.**
  Every other library does.
  A caller types it first.
  Rejected above: the same value reads as content to the next caller, and the failure is silent.
- **Accept `str` as content and encode it.**
  Rejected on the same ambiguity in reverse, plus an encoding Epistole would have to choose.
- **Sniff the bytes with `filetype` or `python-magic`.**
  Rejected above: it adds a dependency and a guess, where a lookup already works.
- **Infer the filename from a file object's `.name`.**
  It is convenient for the `open(path, "rb")` case, which is the common one.
  Rejected above: it is absent or wrong on the other three cases.
  The caller does not see the mistake until the message is delivered.
- **Use one `.attach(..., inline=True)` instead of `.embed()`.**
  It gives one method and one mental model.
  Rejected above: the flag carries two requirements the signature then stops describing.
- **A repeated content id replaces, or appends silently.**
  Rejected above: replacing contradicts ADR-0002's append rule, and appending produces HTML that cannot resolve.
- **Accept media-type parameters and pass them through.**
  Rejected because the three backend formats spell them differently and none of the three needs one in v1.

## Consequences

- A caller holding a `bytearray`, a `memoryview`, or a text-mode file writes one conversion.
  The error message names it.
- `.attach(BytesIO(pdf))` without `filename=` fails at the line that wrote it, not at send.
- `mimetypes.guess_extension` finds no extension for an unregistered media type.
  So the rewrite's generated content id and filename are the bare digest (ADR-0003).
- `docs/spec.md` no longer holds a rule block whose only citation is a closed issue.
  Its own reading rules call that a defect.
- [#21](https://github.com/ozanozbeker/epistole/issues/21) tells authors to `.embed()` rather than write `data:`.
  It can now cite a rule for filenames and content types.

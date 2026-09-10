# An attachment enters as a path, bytes, or a binary file object

`.attach()` and `.embed()` take one positional source and nothing else positionally: a `Path`, a `bytes`, or an object with `.read()` returning `bytes`.
A `Path` names itself; every other source must be given a `filename=`.
The content type is inferred from that filename, falls back to `application/octet-stream`, and is written explicitly on every wire.
Bytes are never sniffed and a `str` is never read as a path.
`.embed()` adds an inline image under a content id that must be free.
Decided on [#30](https://github.com/ozanozbeker/epistole/issues/30), which found the whole block in `docs/spec.md` citing [#11](https://github.com/ozanozbeker/epistole/issues/11) and ADR-0003, neither of which decides any of it.

## Why

**A `str` is the one input that means two things.**
`docs/research/prior-art.md` warns about strings that could mean two things, and ADR-0003 already refused to read a local path out of `<img src>` on that ground.
`.attach("report.pdf")` reads as a filename to one caller and as content to another, and Python has no type to tell them apart.
So `str` raises `TypeError` and the message says to wrap it in `Path()`, which is one word at the call site and removes the ambiguity for good.

**`bytearray` and `memoryview` raise because a `Message` is a closed value.**
ADR-0002 makes a message hold nothing that can change under it, and both of those are live views of memory the caller still owns.
Accepting one would mean either copying it silently, which hides the cost, or storing it, which lets a caller mutate bytes that already went out on an earlier send in the loop.
`bytes` is immutable and hashable, which is also what keeps `Attachment` hashable and ADR-0002's equality rule intact.
A caller holding a `bytearray` writes `bytes(buf)`.

**A text-mode file raises rather than encoding.**
`open(path)` yields `str` on `.read()`, and guessing an encoding to turn that into bytes is a decision about the recipient's mail that Epistole has no basis for.
The fix is one character, `"rb"`, and the error says so.

**`.name` on a file object is not read, because it is usually the wrong name.**
`io.BytesIO` has none.
`tempfile.NamedTemporaryFile` has a temp path the recipient should never see.
`gzip.GzipFile.name` is the compressed file, not the member.
A filename Epistole guessed is a name the recipient reads, so the caller supplies it or the call fails.

**The content type is declared, never sniffed.**
Sniffing means a dependency (`filetype`, `python-magic`) and a guess at meaning, which ADR-0003 refused for `data:` payloads and this refuses for the same reason.
`mimetypes.guess_type` on the filename is a lookup, not a guess: it reads the extension the caller wrote.
The fallback is `application/octet-stream` because RFC 2046 makes it the default and every client renders it as a file to download, which is the honest answer for bytes nobody labelled.
Parameters are dropped, so a `content_type=` of `text/csv; charset=utf-8` is a `ValueError` rather than a value Epistole has to reason about at three wire formats.
It is written explicitly on every backend, because leaving it off hands the guess to the receiving client instead.

**`.embed()` is a second method, not a flag on `.attach()`.**
An inline image has two requirements an attachment does not: the content type must be `image/*`, and it must answer to a content id the HTML can name.
A `.attach(inline=True)` would carry both as runtime conditions on a flag, and the signature would stop describing what the call needs.
Two methods put `cid=` where it belongs and leave `.attach()`'s signature honest.

**A content id already in use is a `ValueError`, with no exception for identical bytes.**
`CONTEXT.md` says a content id is unique within one message, and `cid` defaults to the filename, so `.embed(Path("a/logo.png")).embed(Path("b/logo.png"))` is the ordinary way to break it.
Two images under one id cannot both be honoured, whatever they hold, so the rule has no special case.
The rewrite in ADR-0003 runs at construction and `.embed()` runs after it, so a caller who names an id the rewrite generated hits the same error.
This does not amend ADR-0002's append rule: `.embed()` still appends, and it refuses only the append that would be unresolvable.

## Rules

- **`source` is `Path`, `bytes`, or a binary file object with `.read()`.**
  `str` is a `TypeError` naming `Path()`.
  `bytearray`, `memoryview`, and a text-mode file are each a `TypeError`.
- **Bytes are read when the method is called.**
  A file object is read once and left open for the caller (ADR-0002).
- **A `Path` names itself; every other source needs `filename=`.**
  Its absence is a `TypeError`.
  `.name` on a file object is never read.
- **The content type is inferred from the filename and falls back to `application/octet-stream`.**
  `content_type=` overrides the inference.
  A media type carrying parameters is a `ValueError`.
  The type is written explicitly on SMTP, Gmail, and Graph alike, and bytes are never inspected.
- **`.embed()` defaults `filename` and `cid` to each other**, so `.embed(Path("logo.png"))` answers `<img src="cid:logo.png">`.
  Supplying neither, with a source that is not a `Path`, is a `TypeError`.
- **`.embed()` requires an `image/*` content type** after inference or override, else `ValueError`.
- **A content id already held is a `ValueError`**, naming it, including one the `data:` rewrite generated at construction.
- **`Attachment` is a frozen dataclass**: `filename`, `content_type`, `data`, `content_id`.
  `content_id` is `None` on an attachment and set on an inline image.
- **`attachments` holds what `.attach()` added, `inline_images` what `.embed()` added and what the rewrite made**, each in insertion order.
  Neither name takes ADR-0007's underscore, because no method claims it.
- **Nothing removes.**
  ADR-0002's rule holds here with no addition: a message without an attachment is built without it.

## Considered options

- **Accept `str` as a path.**
  Every other library does, and it is what a caller types first.
  Rejected above: the same value reads as content to the next caller, and the failure is silent.
- **Accept `str` as content and encode it.**
  Rejected on the same ambiguity, from the other side, plus an encoding Epistole would have to choose.
- **Sniff the bytes with `filetype` or `python-magic`.**
  Rejected above: a dependency and a guess, against a lookup that already works.
- **Infer the filename from a file object's `.name`.**
  Convenient for the `open(path, "rb")` case, which is the common one.
  Rejected above: it is absent or wrong on the other three cases, and the caller never sees the mistake until the mail arrives.
- **One `.attach(..., inline=True)` instead of `.embed()`.**
  One method, one mental model.
  Rejected above: the flag carries two requirements the signature then stops describing.
- **A repeated content id replaces, or appends silently.**
  Rejected above: replacing contradicts ADR-0002's append rule, and appending produces HTML that cannot resolve.
- **Accept media-type parameters and pass them through.**
  Rejected because the three wire formats spell them differently and none of the three needs one in v1.

## Consequences

- A caller holding a `bytearray`, a `memoryview`, or a text-mode file writes one conversion, and the error message names it.
- `.attach(BytesIO(pdf))` without `filename=` fails at the line that wrote it, not at send.
- An unregistered media type leaves `mimetypes.guess_extension` with no answer, so the rewrite's generated content id and filename are the bare digest (ADR-0003).
- `docs/spec.md` stops carrying a rule block whose only citation is a closed issue, which its own reading rules call a defect.
- [#21](https://github.com/ozanozbeker/epistole/issues/21) tells authors to `.embed()` rather than write `data:`, and now has a rule to point at for filenames and content types.

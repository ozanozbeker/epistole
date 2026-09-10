# Readbacks carry a trailing underscore

`.to()`, `.cc()`, `.bcc()`, `.reply_to()`, and `.subject()` are the builder methods (ADR-0002), so `message.to` is a bound method and the value needs a second name.
The value reads back as the same name plus a trailing underscore: `to_`, `cc_`, `bcc_`, `reply_to_`, `subject_`.
`recipients` has no underscore, because no method claims it; it is `to_ + cc_ + bcc_` in that order with duplicates kept, as Django's `recipients()`.
Decided on [#14](https://github.com/ozanozbeker/epistole/issues/14).

## Why

PEP 8 reserves the trailing underscore for keyword clashes (`class_`), and Polars and SQLAlchemy use it only for `and_`, `or_`, `not_`, so a Python reader pauses on `to_`. scikit-learn's `coef_` and `classes_` trained the analyst audience to read `name_` as the value the object now holds, which is exactly this.
One mechanical rule beats five invented words (`to_addresses`, `subject_line`) or a sub-object (`message.headers.to`, where `bcc` under "headers" teaches a falsehood, since Bcc is stripped from the sent message).
The readbacks exist for tests against `MemoryBackend`'s outbox; that is the only place the suffix is typed.

The class docstring states the rule in one sentence so nobody "fixes" it to PEP 8.
Duplicates are kept because dedupe would make the readback disagree with the message as built and with what SMTP writes on the wire.

# A builder method's value is an attribute named for the method plus a trailing underscore

`.to()`, `.cc()`, `.bcc()`, `.reply_to()`, `.subject()`, and `.headers()` are the builder methods (ADR-0002).
So `message.to` is a bound method, and the value needs a second name.
The value is an attribute with the same name plus a trailing underscore: `to_`, `cc_`, `bcc_`, `reply_to_`, `subject_`, `headers_`.
`recipients` has no underscore, because no method uses that name.
It is `to_ + cc_ + bcc_` in that order with duplicates kept, as Django's `recipients()` is.
Decided on [#14](https://github.com/ozanozbeker/epistole/issues/14).
Amended on [#27](https://github.com/ozanozbeker/epistole/issues/27): `.headers()` is now a builder method, so `headers_` is now one of these attributes.
The mechanical rule produces it with no exception (ADR-0016).
Amended on [#28](https://github.com/ozanozbeker/epistole/issues/28): a test reaches these attributes one level deeper, as `submissions[0].message.to_`.
That is still the only place the suffix is typed (ADR-0015).
Amended on [#29](https://github.com/ozanozbeker/epistole/issues/29): the `attachments` and `inline_images` attributes hold what `.attach()` and `.embed()` added.
They have no underscore, because neither method uses those names.
The same reasoning gives `recipients` none.

## Why

PEP 8 reserves the trailing underscore for keyword clashes (`class_`).
Polars and SQLAlchemy use it only for `and_`, `or_`, `not_`.
So a Python reader pauses on `to_`.
The analyst audience knows `name_` from scikit-learn's `coef_` and `classes_`, where it means the value the object now holds.
This ADR uses it in exactly that sense.
One mechanical rule is better than five invented words (`to_addresses`, `subject_line`) or a sub-object (`message.headers.to`).
Putting `bcc` under "headers" implies something false, since Bcc is stripped from the sent message.
These attributes exist for tests against `MemoryBackend.submissions`, read as `submissions[0].message.to_` (ADR-0015).
That is the only place the suffix is typed.

The class docstring states the rule in one sentence so nobody "fixes" it to PEP 8.
Each attribute keeps duplicates, because dedupe would make it differ from the message as built and from what SMTP sends.

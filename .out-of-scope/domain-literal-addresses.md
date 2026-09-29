# Domain-literal addresses

Epistole does not accept an address whose domain is a domain literal, such as `a@[127.0.0.1]` or `a@[IPv6:2001:db8::1]`.
The address check raises `ValueError` for one, and Epistole does not work around it.

## Why this is out of scope

The check reads each address with `email.utils.getaddresses`.
Its default strict parser returns `('', '')` for any addr-spec that holds a `[`, so every domain literal fails the check.
Accepting one would mean replacing that parser, or passing `strict=False`, which brings back the parsing that CVE-2023-27043 fixed.
Either change would also change every other place Epistole reads an addr-spec: the SMTP envelope, Graph's recipients, the `Message-ID` domain, and the keys of `MemoryBackend(refuse=)`.

ADR-0014 keeps the check to an address's shape.
Epistole is not a validation library, and it does not cover every form RFC 5322 allows.
A caller passes the mailbox's domain name instead of an address literal.

## Prior requests

- #65: "The address check rejects every domain-literal address, such as `a@[127.0.0.1]`"

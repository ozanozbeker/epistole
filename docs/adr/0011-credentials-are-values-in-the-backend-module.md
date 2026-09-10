# Credentials are values in each backend's module, and Epistole builds the vendor object

Every backend takes `credential=`, a frozen value from that backend's own module: `epistole.smtp.Password` and `epistole.smtp.OAuth`, `epistole.graph.ClientSecret`, `epistole.graph.Certificate`, and `epistole.graph.ManagedIdentity`, `epistole.gmail.ServiceAccount` and `epistole.gmail.AuthorizedUser`.
`credential=None` on SMTP is anonymous submission.
An object with `get_token` in the shape `azure.core.credentials.TokenCredential` defines passes through unchanged, and nothing else does: no bare token string, no callable, no vendor client.
The value holds inputs only; `connect()` builds the `msal` or `google-auth` object and adapts it to Epistole's private token-source shape.
SMTP OAuth takes a Graph or Gmail value and derives its scope from that value's issuer.
Consent flows and token storage stay out of scope, as [#2](https://github.com/ozanozbeker/epistole/issues/2) says.
Decided on [#18](https://github.com/ozanozbeker/epistole/issues/18).

## Why

**The caller should not have to import `msal` or `google-auth`.**
The prototype on #8 made the caller build `msal.ConfidentialClientApplication(...)` and `Credentials.from_authorized_user_file(...)` and hand them in.
That is vendor knowledge every user pays for, and it is the opposite of the one-interface promise the library makes for messages.
The inputs are the same either way: tenant, client id, and a secret or certificate; a service account file and the mailbox to act as; a saved user token.
Holding those in a Epistole value and building the vendor object inside `connect()` costs Epistole about two hundred lines and the caller nothing.

**Values live with the backend, not in one `creds` namespace.**
A single `epistole.creds` module was rejected because the values are not interchangeable: a `Password` means nothing to Graph and a `ManagedIdentity` means nothing to SMTP.
Putting each value in the module of the backend that issues its tokens makes the valid set visible at the import.
SMTP OAuth is the one crossover, because an Exchange Online SMTP token comes from the same Entra app that Graph uses and a Gmail SMTP token from the same Google credential Gmail uses, so `epistole.smtp.OAuth` takes the other module's value rather than duplicating it.

**Tagged values, not loose keyword arguments.**
SMTP alone has three shapes, anonymous, password, and OAuth, and loose `username=` / `password=` / `credential=` / `scope=` arguments spell several invalid combinations.
Two of the five shapes across the three backends appeared only after the first prototype draft, which is the sign that an open argument list will keep growing.

**The public token shape is Azure's, and it is the only door.**
`get_token(*scopes) -> AccessToken` is what `azure-identity` implements, managed identity included, so those objects work with no dependency on `azure-core`.
`google-auth` and `msal` do not implement it; Epistole adapts both privately, as ADR-0009 already requires.
A bare token string is rejected because it expires within an hour and a scheduled job would fail silently on its second run.
A bare callable is rejected because it carries no expiry and no type.

**Scope comes from the issuer, never from the host.**
Graph fixes `https://graph.microsoft.com/.default`.
SMTP OAuth needs `https://outlook.office365.com/.default` for a Graph value and `https://mail.google.com/` for a Gmail value, which the value's module already tells Epistole.
A foreign `get_token` object has no issuer Epistole knows, so `OAuth(..., scope=...)` is required there and `TypeError` otherwise.
Inferring scope from `host=` would be a guess.

**Consent flows and storage stay out.**
Owning them means `google-auth-oauthlib` and `msal-extensions`, an encrypted store per operating system (DPAPI, Keychain, libsecret, which headless Linux often lacks), a cache rewrite after any send that refreshed, and a Google Cloud OAuth client per user because a shipped client secret is public.
`gmail.send` is a Sensitive scope, so an external app needs Google's verification, and while the project sits in Testing its refresh tokens expire after seven days.
That is the silent Monday failure the issue was written to prevent, arriving from the other side.
The values here are the door: a future `Login` value would be one more constructor returning the same shape, and no backend changes.

## Rules

- `SmtpBackend(..., credential=None | Password | OAuth)`.
  `Password(username, password)`.
  `OAuth(username, credential, scope=None)`, where `credential` is a Graph value, a Gmail value, or a `get_token` object; `scope` is required for the last and forbidden for the first two.
  XOAUTH2 through `smtplib.SMTP.auth`, auth string `user={username}\x01auth=Bearer {token}\x01\x01`.
- `GraphBackend(from_address, credential)` with `ClientSecret(tenant_id, client_id, client_secret)`, `Certificate(tenant_id, client_id, pfx=, passphrase=None)` or `Certificate(tenant_id, client_id, private_key=, thumbprint=)`, the two forms `msal` accepts and mutually exclusive, `ManagedIdentity(client_id=None)` for system- or user-assigned, or any `get_token` object.
- `GmailBackend(from_address, credential)` with `ServiceAccount(path, subject)` for domain-wide delegation or `AuthorizedUser(path)` for a saved user consent.
  The API path is always `users/me`; with a delegated service account `me` resolves to `subject`.
  Application Default Credentials are not offered: sending as a mailbox from ADC needs a signed delegation JWT that keyless ADC cannot produce.
- Every value is a frozen dataclass of inputs.
  Importing a value imports no vendor library; the backend constructor raises `ImportError` naming the extra (ADR-0009), and `connect()` builds the vendor object.
- `msal.ManagedIdentityClient` needs an `http_client` with the `requests.Session` shape, so the `httpx2` adapter from ADR-0009 satisfies that shape too.
- No password-file or keyring helpers.
  `os.environ[...]` is one line, and `keyring` is a library the caller can call.
- No `provider=` presets for SMTP host and port.
  A preset table is guidance, and it belongs in `docs/choosing-a-backend.md`, not in the constructor.

## Considered options

- **Caller builds the vendor object, Epistole adapts.**
  The prototype's shape and #2's literal wording.
  Rejected above: vendor knowledge on every user.
- **One `epistole.creds` namespace.**
  Rejected above: hides which values a backend accepts.
- **`epistole.microsoft` and `epistole.google` modules shared by two backends each.**
  Would spare `epistole.smtp` an import from `epistole.graph`.
  Rejected for now because it names companies where the glossary names backends; additive if the crossover grows.
- **Loose keyword arguments on `SmtpBackend`.**
  Rejected above.
- **Accept a bare token or a callable.**
  Rejected above.
- **Epistole owns consent flows and storage.**
  Rejected above and by #2.
- **Blastula's password file and keyring helpers.**
  Rejected: the file is unencrypted JSON and the keyring path needs an OS keyring that servers lack.

## Consequences

- The Exchange Online basic-auth shutoff at the end of December 2026 is a credential change, `Password` to `OAuth`, not a backend change.
- `Password` is not deprecated anywhere in Epistole; it is disabled on one tenant type, and the documentation names the tenant, not the mechanism.
- Epistole maintains the input formats of two vendor constructors.
- The glossary's *Credential* widens to cover a password and none at all, and gains *Token source* for what `connect()` builds.
- Whether Gmail's `me` resolves to the delegated subject on the `send` endpoint needs a live test, alongside the other Gmail fog on #2.

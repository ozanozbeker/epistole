# Credentials are values in each backend's module, and Epistole builds the vendor object

Every backend takes `credential=`, a frozen value from that backend's own module.
The SMTP values are `epistole.smtp.Password` and `epistole.smtp.OAuth`.
The Graph values are `epistole.graph.ClientSecret`, `epistole.graph.Certificate`, and `epistole.graph.ManagedIdentity`.
The Gmail values are `epistole.gmail.ServiceAccount` and `epistole.gmail.AuthorizedUser`.
`credential=None` on SMTP is anonymous submission.
Epistole also accepts an object with `get_token` in the shape `azure.core.credentials.TokenCredential` defines, and uses it unchanged.
It accepts nothing else: no bare token string, no callable, no vendor client.
The value holds inputs only.
`connect()` builds the `msal` or `google-auth` object and adapts it to Epistole's private token-source shape.
SMTP OAuth takes a Graph or Gmail value and derives its scope from that value's issuer.
Consent flows and token storage stay out of scope, as [#2](https://github.com/ozanozbeker/epistole/issues/2) says.
Decided on [#18](https://github.com/ozanozbeker/epistole/issues/18).
Amended on [#30](https://github.com/ozanozbeker/epistole/issues/30), which made four changes.
A confidential client requests a scope, and a managed identity requests a resource.
The Gmail REST backend requests `gmail.send` rather than the SMTP scope.
`Certificate` requires one complete form.
`TokenCredential` and `AccessToken` are exported as Protocols.

## Why

**The caller should not have to import `msal` or `google-auth`.**
The prototype on #8 made the caller build `msal.ConfidentialClientApplication(...)` and `Credentials.from_authorized_user_file(...)` and pass them in.
That requires vendor knowledge from every user.
It is also the opposite of the one interface the library provides for messages.
The inputs are the same either way: tenant, client id, and a secret or certificate; a service account file and the mailbox to act as; a saved user token.
Holding those in an Epistole value and building the vendor object inside `connect()` takes about two hundred lines in Epistole and none in the caller's code.

**Values are defined in the backend's module, not in one `creds` namespace.**
A single `epistole.creds` module was rejected because the values are not interchangeable.
The Graph backend takes no `Password`, and the SMTP backend takes no `ManagedIdentity`.
Putting each value in the module of the backend that issues its tokens makes the valid set visible at the import.
SMTP OAuth is the one crossover.
An Exchange Online SMTP token comes from the same Entra app that Graph uses.
A Gmail SMTP token comes from the same Google credential that Gmail uses.
So `epistole.smtp.OAuth` takes the other module's value rather than duplicating it.

**Credentials are tagged values, not loose keyword arguments.**
SMTP alone has three shapes: anonymous, password, and OAuth.
Loose `username=`, `password=`, `credential=`, and `scope=` arguments can express several invalid combinations.
Two of the five shapes across the three backends appeared only after the prototype's first version.
That shows an open argument list will keep growing.

**The public token shape is Azure's, and Epistole accepts no other.**
`azure-identity` implements `get_token(*scopes) -> AccessToken`, managed identity included.
So those objects work with no dependency on `azure-core`.
`google-auth` and `msal` do not implement it.
Epistole adapts both privately, as ADR-0009 already requires.
Both names are exported as `typing.Protocol`s, because they annotate three public constructors.
A name a caller cannot import is not a usable annotation.
The shape is fixed outside this repo, so the commitment needs no maintenance.
A bare token string is rejected because it expires within an hour and a scheduled job would fail silently on its second run.
A bare callable is rejected because it carries no expiry and no type.

**The audience comes from the issuer, never from the host.**
Each issuer fixes one audience: `https://graph.microsoft.com` for Graph, `https://outlook.office365.com` for SMTP against Exchange Online, and `https://mail.google.com/` for SMTP against Gmail.
Epistole cannot read an issuer from a foreign `get_token` object.
So `OAuth(..., scope=...)` is required there, and leaving it out raises `TypeError`.
Inferring an audience from `host=` would be a guess.

**One audience has two spellings, because msal has two clients.**
`ConfidentialClientApplication.acquire_token_for_client` takes `scopes=["<audience>/.default"]`.
`ManagedIdentityClient.acquire_token_for_client` takes `resource="<audience>"` and does not accept a scope at all.
So a single declared scope for all three Graph credentials leaves `ManagedIdentity` with no token path.
The private token-source adapter picks the spelling from the credential's own type.
The same rule covers `smtp.OAuth(credential=graph.ManagedIdentity(...))`.

**The Gmail REST backend requests less than SMTP does.**
`messages.send` needs `https://www.googleapis.com/auth/gmail.send`.
SMTP XOAUTH2 needs `https://mail.google.com/`, which Google's own SMTP page requires.
That scope grants full mailbox read and delete.
Using the wider one on both paths would give a library that only sends the right to empty a mailbox.
So the two paths request different scopes.
An administrator granting domain-wide delegation for both grants two.

**Consent flows and storage stay out.**
Owning them means depending on `google-auth-oauthlib` and `msal-extensions`.
It means an encrypted store per operating system (DPAPI, Keychain, libsecret, which headless Linux often lacks).
It means a cache rewrite after any send that refreshed.
It also means a Google Cloud OAuth client per user, because a shipped client secret is public.
`gmail.send` is a Sensitive scope, so an external app needs Google's verification.
While the project is in Testing, its refresh tokens expire after seven days.
That reintroduces the silent Monday failure the issue was written to prevent, through a different cause.
These values are the extension point: a future `Login` value would be one more constructor returning the same shape.
No backend would change.

## Rules

- `SMTPBackend(..., credential=None | Password | OAuth)`.
  `Password(username, password)`.
  `OAuth(username, credential, scope=None)`, where `credential` is a Graph value, a Gmail value, or a `get_token` object.
  `scope` is required for the last and forbidden for the first two.
  XOAUTH2 uses `smtplib.SMTP.auth` with the auth string `user={username}\x01auth=Bearer {token}\x01\x01`.
- `GraphBackend(from_address=, credential=)` takes `ClientSecret(tenant_id, client_id, client_secret)`, a certificate, `ManagedIdentity(client_id=None)` for a system- or user-assigned identity, or any `get_token` object.
  The certificate is `Certificate(tenant_id, client_id, pfx=, passphrase=None)` or `Certificate(tenant_id, client_id, private_key=, thumbprint=)`, the two mutually exclusive forms `msal` accepts.
- **`Certificate` takes exactly one complete form.**
  It takes either `pfx` with an optional `passphrase`, or `private_key` and `thumbprint` together.
  Neither form, both forms, either half of the second form alone, and `passphrase` without `pfx` each raise `TypeError` at construction.
  All four fields default to `None`, so without the enumeration, half the combinations a caller can write have no rule.
- **A confidential client requests a scope, and a managed identity requests a resource.**
  `ClientSecret` and `Certificate` request `<audience>/.default`.
  `ManagedIdentity` requests `<audience>`.
  The audience is `https://graph.microsoft.com` on `GraphBackend` and `https://outlook.office365.com` on `smtp.OAuth` with a Graph value.
  The adapter picks the spelling.
  Neither spelling appears in a signature.
- `GmailBackend(from_address=, credential=)` takes `ServiceAccount(path, subject)` for domain-wide delegation or `AuthorizedUser(path)` for a saved user consent.
  The API path is always `users/me`.
  With a delegated service account, `me` resolves to `subject`.
  It requests `https://www.googleapis.com/auth/gmail.send`.
  `smtp.OAuth` with a Gmail value requests `https://mail.google.com/`.
  Application Default Credentials are not offered: sending as a mailbox from ADC needs a signed delegation JWT that keyless ADC cannot produce.
- Every value is a frozen dataclass of inputs.
  Importing a value imports no vendor library.
  The backend constructor raises `ImportError` naming the extra (ADR-0009).
  `connect()` builds the vendor object.
- The SMTP scope derivation covers application-flow Graph values only, which is every Graph value Epistole provides.
  The SMTP onboarding page tells an app to request `https://outlook.office365.com/.default`.
  It also tells the app to add no claims at all, because including an `SMTP.SendAsApp` claim triggers a mailbox-permission check the app does not need.
  Whether Exchange Online exposes a delegated equivalent is undetermined, and it does not need to be determined.
  No delegated Graph value exists here.
  Epistole receives a delegated Exchange token only as a foreign `get_token` object, and that path takes its own explicit `scope=`.
  A future `Login` value would be the first delegated Graph value.
  It would reopen the question.
- `msal.ManagedIdentityClient` needs an `http_client` with the `requests.Session` shape, so the `httpx2` adapter from ADR-0009 satisfies that shape too.
- Epistole ships no password-file or keyring helpers.
  `os.environ[...]` is one line.
  `keyring` is a library the caller can call.
- There are no `provider=` presets for SMTP host and port.
  A preset table is guidance, so it belongs in `docs/choosing-a-backend.md`, not in the constructor.

## Considered options

- **The caller builds the vendor object, and Epistole adapts it.**
  It is the prototype's shape and #2's literal wording.
  Rejected above: it requires vendor knowledge from every user.
- **Use one `epistole.creds` namespace.**
  Rejected above: it hides which values a backend accepts.
- **Add `epistole.microsoft` and `epistole.google` modules, each shared by two backends.**
  It would remove the import of `epistole.graph` from `epistole.smtp`.
  Rejected for now because it names companies where the glossary names backends.
  It remains an additive change if the crossover grows.
- **Take loose keyword arguments on `SMTPBackend`.**
  Rejected above.
- **Accept a bare token or a callable.**
  Rejected above.
- **Epistole owns consent flows and storage.**
  Rejected above and by #2.
- **Copy blastula's password file and keyring helpers.**
  Rejected: the file is unencrypted JSON and the keyring path needs an OS keyring that servers lack.

## Consequences

- The Exchange Online basic-auth shutoff at the end of December 2026 is a credential change, `Password` to `OAuth`, not a backend change.
- `Password` is not deprecated anywhere in Epistole.
  It is disabled on one tenant type.
  The documentation names the tenant, not the mechanism.
- Epistole maintains the input formats of two vendor constructors.
- The glossary's *Credential* entry now covers a password and none at all.
  The glossary adds *Token credential* for what `connect()` builds.
- Two Gmail facts need a real send, so implementation settles them.
  The first is whether `me` resolves to the delegated subject on the `send` endpoint.
  The second is whether `messages.send` preserves a client-supplied `Message-ID`.
  Neither changes a rule here.
  `SendResult.message_id` is the id Epistole set either way (ADR-0004), so the answer to the second sets one docstring sentence about what a recipient sees.

# Prior art: one API across many mail backends

Research for [#6](https://github.com/ozanozbeker/herma/issues/6).
Everything below comes from reading the source, not from summaries of it.

## What was read, and at what version

| Library | Version read | Source |
| --- | --- | --- |
| Django | `main` at `e2a3da14`, `VERSION = (6, 2, 0, "alpha", 0)` | [django/core/mail](https://github.com/django/django/tree/main/django/core/mail) |
| django-anymail | 15.2, released 2026-09-05 | [anymail/django-anymail](https://github.com/anymail/django-anymail) |
| redmail | 0.6.0 sdist, released 2023-02-25 | [Miksus/red-mail](https://github.com/Miksus/red-mail/tree/v0.6.0) |
| blastula | 0.3.6 on CRAN, published 2025-04-03 | [rstudio/blastula](https://github.com/rstudio/blastula) |

Django is mid-migration.
The email API herma should study is not the one in the 5.2 docs.
See "Django is replacing `get_connection()` right now" below.

## Django

Django splits the work in one sentence, and states it plainly in the docs:

> `EmailMessage` is responsible for creating the email message itself.
> The email backend is then responsible for sending the email.

Source: `docs/topics/email.txt` around line 476.

### The message owns everything except the wire

`django/core/mail/message.py`, line 260:

```python
def __init__(
    self,
    subject="",
    body="",
    from_email=None,
    to=None,
    *,
    bcc=None,
    connection=None,
    attachments=None,
    headers=None,
    cc=None,
    reply_to=None,
):
```

`EmailMultiAlternatives` adds one argument, `alternatives`, and one method (`message.py`, line 657):

```python
def attach_alternative(self, content, mimetype):
    """Attach an alternative content representation."""
```

Recipients, subject, body, attachments and extra headers all live on the message.
Only the transport lives on the backend.

Django refuses a bare string for every address list.
`message.py`, line 278:

```python
if to:
    if isinstance(to, str):
        raise TypeError('"to" argument must be a list or tuple')
    self.to = list(to)
```

The same four-line block repeats for `cc`, `bcc` and `reply_to`.
The message never parses an address.
It stores the string and hands it to `email.headerregistry` at serialization time.
Only the SMTP backend parses, in `prep_address()` (`backends/smtp.py`, line 227), and only to get the addr-spec for the envelope.

`recipients()` is the seam that makes this work (`message.py`, line 375):

```python
def recipients(self):
    return [email for email in (self.to + self.cc + self.bcc) if email]
```

The docs call this out as the extension point: a subclass that invents a new way to name recipients must override `recipients()`, because the SMTP envelope needs the full list.

### Attachments are a three-tuple or a `MIMEPart`

`message.py`, lines 236 and 422:

```python
EmailAlternative = namedtuple("EmailAlternative", ["content", "mimetype"])
EmailAttachment = namedtuple("EmailAttachment", ["filename", "content", "mimetype"])

def attach(self, filename=None, content=None, mimetype=None):
def attach_file(self, path, mimetype=None):
```

`attach()` overloads on the type of its first argument.
Pass a `MIMEPart` and it goes in whole; pass a filename and content and Django guesses the mimetype from the filename.
`attach_file(path)` is the filesystem convenience: it reads the bytes and delegates to `attach()`.

Django has no inline-image helper.
The documented way to get a `cid:` reference is nine lines of `email.message.MIMEPart` by hand, quoted in full in `docs/topics/email.txt` around line 655.
Anymail exists partly to fix this.

### The backend owns the connection, and only three methods

`django/core/mail/backends/base.py`:

```python
def open(self):
def close(self):
def __enter__(self):
def __exit__(self, exc_type, exc_value, traceback):
def send_messages(self, email_messages):
```

`send_messages()` is the only method a subclass must implement.
`open()` and `close()` default to no-ops, which is why the console, locmem and dummy backends are 10 to 46 lines each.

The lifecycle rule is worth copying exactly.
From `backends/smtp.py`, line 183:

```python
with self._lock:
    new_conn_created = self.open()
    ...
    finally:
        if new_conn_created:
            self.close()
```

`send_messages()` opens the connection if it is closed and closes it again only if it opened it.
A caller who opened the connection keeps it.
That single rule gives both the one-off send and the batch loop without a separate API for each.
The docs say it out loud: "`send_messages()` will not open or close the connection if it is already open".

`__enter__` returns `self`, and `__exit__` closes.
`__enter__` also closes on a failed `open()`, so a broken connect does not leak a socket.

### Two objects can call `send`, and only one of them means it

`EmailMessage.send()` exists as sugar (`message.py`, line 382).
It builds a one-element list and calls the backend:

```python
return connection.send_messages([self])
```

Django's own comment shows where this is heading:

```python
# RemovedInDjango2028Warning: replace the remainder of this method
# with:
#   from django.core.mail import mailers
#   mailer = mailers.default if using is None else mailers[using]
#   return mailer.send_messages([self])
```

So `message.send()` will survive, but only as a lookup plus a delegation.
The backend stays the thing that sends.

### Django is replacing `get_connection()` right now

This is the most useful thing in the survey, and it postdates every tutorial.

Django 6.1 added a `MAILERS` setting shaped like `DATABASES` and `CACHES`, and deprecated the whole `EMAIL_*` family.
From the 6.1 release notes:

> The `EMAIL_BACKEND`, `EMAIL_FILE_PATH`, `EMAIL_HOST`, `EMAIL_HOST_PASSWORD`, `EMAIL_HOST_USER`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_SSL_CERTFILE`, `EMAIL_SSL_KEYFILE`, and `EMAIL_TIMEOUT` settings are deprecated.
>
> `mail.get_connection()` is deprecated.
>
> The `connection` argument to `send_mail()`, `send_mass_mail()`, `mail_admins()`, `mail_managers()`, and `EmailMessage` is deprecated.
> The `EmailMessage.connection` attribute is also deprecated.
> Switch to the `using` argument with a `MAILERS` alias.
>
> Directly constructing and using instances of the smtp.EmailBackend class is deprecated.
> Use `mail.mailers` to obtain email backend instances.

The replacement is an alias registry.
`django/core/mail/handler.py`:

```python
DEFAULT_MAILER_ALIAS = "default"
DEFAULT_MAILER_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


class MailersHandler:
    def __getitem__(self, /, alias): ...
    def __contains__(self, /, alias): ...
    def __iter__(self): ...
    def get(self, alias, /, default=None): ...
    @property
    def default(self): ...
    def create_connection(self, alias, /, *, _deprecated_kwargs=None): ...
```

and the call site becomes `email.send(using="notifications")`.

Three details are worth stealing whole.

**A named alias beats an object handle.**
Fifteen years of `connection=` taught Django that threading a backend instance through call sites couples the caller to construction.
An alias is a string; it survives serialization, config files, and being passed to a logging handler.

**Config errors get their own exception type, with the alias in the message.**
`django/core/mail/exceptions.py`:

```python
class InvalidMailer(ImproperlyConfigured):
    """A settings.MAILERS entry has a configuration error."""

    def __init__(self, msg, *, alias=None):
        if alias is not None:
            msg = f"MAILERS[{alias!r}]: {msg}"
        super().__init__(msg)


class MailerDoesNotExist(InvalidMailer, KeyError):
    """The requested alias is not defined in settings.MAILERS."""
```

Every backend validates its own options at construction and raises `InvalidMailer` with the alias attached.
`backends/smtp.py` line 84: `raise InvalidMailer("OPTIONS must define 'host'.", alias=self.alias)`.
Compare the pre-`MAILERS` path, which silently ignored unknown kwargs.

**Unknown options are an error, not a shrug.**
`backends/base.py` raises `InvalidMailer(f"Unknown options {kwarg_names}.", alias=alias)` when a mailer config carries a key the backend does not know.
A typo in `use_tsl` fails at startup instead of sending unencrypted.

Django also deprecated `fail_silently`, which is a verdict on the pattern: an argument that turns exceptions into a silent `return 0` was not worth its cost.

### The test backends

`locmem` is 37 lines and does one thing well (`backends/locmem.py`):

```python
def send_messages(self, messages):
    """Redirect messages to the dummy outbox"""
    msg_count = 0
    for message in messages:
        message.message()  # Trigger header validation.
        msg_copy = copy.deepcopy(message)
        msg_copy.sent_using = self.alias
        mail.outbox.append(msg_copy)
        msg_count += 1
    return msg_count
```

Three decisions in ten lines.
It calls `message.message()` first so header validation still fires, meaning a test catches a malformed address even though nothing goes on the wire.
It deep-copies, so a test asserting on `outbox[0]` cannot be fooled by later mutation of the original.
It stamps `sent_using = self.alias`, so a test can assert *which* mailer a code path chose.
That third one is new in 6.1 and directly answers herma's open question about what `MemoryBackend` should record.

`EmailMultiAlternatives.body_contains(text)` (`message.py`, line 687) is a test helper on the message: it returns `False` unless the text appears in the plain body *and* in every `text/*` alternative.
It exists because the classic bug is updating the HTML and forgetting the plain-text fallback.

`filebased` subclasses `console` and overrides only `open`, `close` and `write_message`.
`console` holds a `threading.RLock` and flushes after each message.
`dummy` is five lines: `return len(list(email_messages))`.

## django-anymail

Not in the issue's list, and it should be.
Anymail is the working answer to herma's exact premise: send through fourteen different providers with the calling code unchanged.
Version 15.2 shipped 2026-09-05, so it is live prior art, not a museum piece.

Its shape: it does not invent a message class.
It ships `EmailBackend` subclasses and reads Django's own `EmailMessage`, plus optional attributes.
`anymail/message.py` line 12:

```python
class AnymailMessageMixin(EmailMessage):
    def __init__(self, *args, **kwargs):
        self.esp_extra = kwargs.pop("esp_extra", UNSET)
        self.envelope_sender = kwargs.pop("envelope_sender", UNSET)
        self.metadata = kwargs.pop("metadata", UNSET)
        self.send_at = kwargs.pop("send_at", UNSET)
        self.tags = kwargs.pop("tags", UNSET)
        self.track_clicks = kwargs.pop("track_clicks", UNSET)
        self.track_opens = kwargs.pop("track_opens", UNSET)
        self.template_id = kwargs.pop("template_id", UNSET)
        self.merge_data = kwargs.pop("merge_data", UNSET)
        self.merge_global_data = kwargs.pop("merge_global_data", UNSET)
        self.merge_headers = kwargs.pop("merge_headers", UNSET)
        self.merge_metadata = kwargs.pop("merge_metadata", UNSET)
        self.anymail_status = AnymailStatus()
```

The docstring says the mixin is optional and exists for type checkers.
Setting the bare attributes on a plain `EmailMessage` works identically.

### Three ideas herma will need

**A named escape hatch.**
`esp_extra` is a dict passed through to the provider's API untouched.
It gives users provider-specific features without herma promising to normalize them, and it keeps them off the shared surface.

**An explicit failure when a backend cannot do what the message asks.**
`anymail/backends/base.py` line 401:

```python
def unsupported_feature(self, feature):
    if not self.backend.ignore_unsupported_features:
        raise AnymailUnsupportedFeature(
            f"{self.esp_name} does not support {feature}",
            email_message=self.message,
            payload=self,
            backend=self.backend,
        )
```

The exception docstring states the policy precisely:

> This is typically raised when attempting to send a Django EmailMessage that uses options or values you might expect to work, but that are silently ignored by or can't be communicated to the ESP's API.
>
> It's generally *not* raised for ESP-specific limitations, like the number of tags allowed on a message.
> Anymail expects the ESP to return an API error for these where appropriate, and tries to avoid duplicating each ESP's validation logic locally.

Loud by default, silenceable by setting.
That second paragraph is the harder half: Anymail refuses to re-implement each provider's validation locally, and lets the provider's own error surface.
Herma faces the identical choice for `from_`, which SMTP lets you set freely and which Gmail and Graph derive from the authenticated account.

**A normalized result object attached to the message.**
`anymail/message.py` lines 103 and 113:

```python
ANYMAIL_STATUSES = [
    "sent",  # the ESP has sent the message (though it may or may not get delivered)
    "queued",  # the ESP will try to send the message later
    "invalid",  # the recipient email was not valid
    "rejected",  # the recipient is blacklisted
    "failed",  # the attempt to send failed for some other reason
    "unknown",  # anything else
]

class AnymailRecipientStatus:
    """Information about an EmailMessage's send status for a single recipient"""

    def __init__(self, message_id, status):
```

`AnymailStatus` aggregates per-recipient statuses and collapses `message_id` to a scalar when every recipient shares one.
Django's `send()` returns an `int`.
Anymail keeps that return value and puts the real answer on `message.anymail_status`.
Herma is designing this return value from scratch and does not have to inherit the `int`.

### The inline-image helper Django lacks

`anymail/message.py` line 67:

```python
def attach_inline_image(
    message, content, filename=None, subtype=None, idstring="img", domain=None
):
    """Add inline image to an EmailMessage, and return its content id"""
    if domain is None:
        # Avoid defaulting to hostname that might end in '.com', because some ESPs
        # use Content-ID as filename, and Gmail blocks filenames ending in '.com'.
        domain = "inline"  # valid domain for a msgid; will never be a real TLD
    ...
    return unquote(content_id)  # Without <...>, for use as the <img> tag src
```

Two details herma will otherwise rediscover the hard way.
The function returns the content id already stripped of angle brackets, because that is what goes in `src="cid:..."`, and forgetting to strip is the classic bug.
And the default `domain` is the literal string `"inline"` rather than the hostname, because Gmail blocks a Content-ID ending in `.com` when the provider reuses Content-ID as a filename.
`attach_inline_image_file(path)` is the path-taking sibling.

## redmail

Read from the 0.6.0 sdist.
Treat it as a record, not a model.

**Staleness, confirmed.**
Last release v0.6.0 on 2023-02-25.
Last commit 2024-04-18, and it fixes a broken link in the docs index.
26 open issues, not archived.

### One class, and defaults on the instance

`redmail/email/sender.py` line 153:

```python
def __init__(self,
             host:str,
             port:int,
             username:str=None,
             password:str=None,
             cls_smtp:smtplib.SMTP=smtplib.SMTP,
             use_starttls:bool=True,
             domain:Optional[str]=None,
             **kwargs):
```

Line 194:

```python
def send(self,
         subject:Optional[str]=None,
         sender:Optional[str]=None,
         receivers:Union[List[str], str, None]=None,
         cc:Union[List[str], str, None]=None,
         bcc:Union[List[str], str, None]=None,
         headers:Optional[Dict[str, str]]=None,
         html:Optional[str]=None,
         text:Optional[str]=None,
         html_template:Optional[str]=None,
         text_template:Optional[str]=None,
         body_images:Optional[Dict[str, Union[str, bytes, 'plt.Figure', 'Image']]]=None,
         body_tables:Optional[Dict[str, 'pd.DataFrame']]=None,
         body_params:Optional[Dict[str, Any]]=None,
         attachments:Optional[Dict[str, Union[str, os.PathLike, 'pd.DataFrame', bytes]]]=None) -> EmailMessage:
```

There is no message class.
Everything is a `send()` keyword.
`send()` calls `get_message()`, which returns a stdlib `email.message.EmailMessage`, then calls `send_message(msg)`.

Every field can also be set as a default on the sender instance, and `send()` wins:

```python
subject = subject or self.subject
sender = self.get_sender(sender)
receivers = self.get_receivers(receivers)
```

with

```python
def get_sender(self, sender: Union[str, None]) -> str:
    """Get sender of the email"""
    return sender or self.sender or self.username
```

The three-level fallback for `sender` is the good part: an explicit argument, then an instance default, then the authenticated username.
Herma has the same problem and can reuse that precedence.

The bad part is that the defaults are plain mutable attributes with no `__init__` parameters and no validation.
`EmailSender.__init__` sets nine of them to `None` by hand.
The logging handler has to work around this with `getattr` checks (`redmail/log.py` line 45):

```python
for attr, value in kwargs.items():
    if not hasattr(self.email, attr):
        raise AttributeError(f"EmailSender has no attribute {attr}")
    setattr(self.email, attr, value)
```

### The preconfigured senders are process-global mutable singletons

`redmail/email/__init__.py`:

```python
gmail = EmailSender(
    host="smtp.gmail.com",
    port=587,
)

outlook = EmailSender(
    host="smtp.office365.com",
    port=587,
)
```

and the documented way to use them is:

```python
from redmail import gmail

gmail.username = "example@gmail.com"
gmail.password = "<APP PASSWORD>"
```

Setting a password on a module-level singleton makes credentials process-wide state.
Two libraries in one process cannot both use `redmail.gmail`.
Herma wants the convenience (`host` and `port` presets for Gmail and Outlook are genuinely useful) without the singleton.
A factory function or a frozen preset constant gives the same ergonomics with none of the aliasing.

### Attachments: real type dispatch, and one trap

`redmail/email/attachment.py`.
The dispatch is keyed on the *container*, and a `str` means two different things depending on it.

In a list or as a bare value, `_get_bytes()` treats `str` as a path:

```python
def _get_bytes(self, item) -> bytes:
    if isinstance(item, str):
        # Considered as path
        if Path(item).is_file():
            return Path(item).read_bytes()
        else:
            raise ValueError(f"Unknown attachment '{item}'. Perhaps a mistyped path?")
```

As a dict value, `_get_bytes_named()` treats the same `str` as raw content:

```python
def _get_bytes_named(self, item, name: str) -> bytes:
    if isinstance(item, str):
        # Considered as raw document
        return item
```

That is a real trap.
`attachments=["report.csv"]` reads a file; `attachments={"report.csv": "report.csv"}` attaches the six characters `report`.

The pandas and matplotlib support is confirmed, and it dispatches on the *file extension in the dict key*:

```python
elif has_pandas and isinstance(item, (pd.DataFrame, pd.Series)):
    buff = io.BytesIO()
    if name.endswith(".xlsx"):
        item.to_excel(buff)
        return buff.getvalue()
    elif name.endswith(".csv"):
        return item.to_csv().encode(self.encoding)
    elif name.endswith(".html"):
        return item.to_html().encode(self.encoding)
    elif name.endswith('.txt'):
        return str(item)
    else:
        raise ValueError(f"Unknown dataframe conversion for '{name}'")
elif isinstance(item, (bytes, bytearray)):
    return item
elif has_pillow and isinstance(item, PIL.Image.Image):
    buf = io.BytesIO()
    item.save(buf, format='PNG')
    ...
elif has_matplotlib and isinstance(item, plt.Figure):
    buf = io.BytesIO()
    item.savefig(buf, format=Path(name).suffix[1:])
```

So `attachments={'data.xlsx': df}` writes Excel and `attachments={'data.csv': df}` writes CSV from the identical object.
The filename carries the format decision.
That reads beautifully in a report script and it is the single best ergonomic idea in the library.

The optional imports that make it work are three lines (`redmail/email/utils.py`):

```python
plt: "plt_lib" = import_from_string("matplotlib.pyplot", if_missing="ignore")
PIL: "PIL_lib" = import_from_string("PIL", if_missing="ignore")
pd: "pandas_lib" = import_from_string("pandas", if_missing="ignore")
css_inline: "css_inline_lib" = import_from_string("css_inline", if_missing="ignore")
```

Every dispatch branch is guarded by `has_pandas`, `has_pillow`, `has_matplotlib`.
The core stays dependency-free and the branch simply does not exist when the package is absent.
That is exactly herma's zero-dependency-core constraint, solved.

### Embedded images go through Jinja variable names, not `cid:`

`body_images` is a dict.
The key is a Jinja variable in the HTML; the value is the image.
`redmail/email/body.py` line 176:

```python
cids = {name: make_msgid(domain=domain) for name in images}
html_images = {
    name: BodyImage(cid=cid[1:-1], name=name, obj=images[name])
    for name, cid in cids.items()
}
```

`BodyImage.__str__` renders `<img src="cid:...">`, so `{{ my_plot }}` in the HTML becomes a complete `img` tag.
The user never types `cid:`.
`attach_imgs()` then dispatches the value: bytes, `BytesIO`, a dict of `{"maintype", "subtype", "content"}`, a `Path`, a path-like `str`, a `plt.Figure`, or a `PIL.Image.Image`.

The cost is that the HTML must be a Jinja template.
`use_jinja` defaults to `True` and every body is rendered:

```python
if self.use_jinja:
    text = self.render(text, **kwargs)
```

Herma's brief is "takes an email you have already composed as HTML".
Running caller-supplied HTML through a template engine by default would break any body containing a literal `{{`, and it is a template injection surface if the HTML came from anywhere but the developer.
The redmail approach only works because templating is the whole point of the library.

### The `css-inline` extra is much narrower than it sounds

The extra is named `style`, not `css-inline` (`pyproject.toml`):

```toml
style = [
    'css_inline',
]
```

And it is used in exactly one place, on pandas `Styler` objects only (`redmail/email/body.py` line 70):

```python
if isinstance(tbl, Styler):
    if css_inline is None:
        raise ImportError(
            "Missing package 'css_inline'. Prettifying tables with Pandas styler requires css_inline."
        )
    inliner = css_inline.CSSInliner()
    return inliner.inline(tbl.to_html())
```

redmail never inlines CSS on the email body.
It inlines CSS on the HTML that `Styler.to_html()` produces, because pandas emits a `<style>` block that mail clients drop.

The underlying problem is real and general.
[`css-inline`](https://pypi.org/project/css-inline/) is a Rust library with Python bindings, built on components from Mozilla's Servo, and its README states it is "designed for scenarios such as preparing HTML emails or embedding HTML into third-party web pages".
It claims 10x to 500x the speed of `premailer`.
For herma the decision is not "copy redmail".
The library never solved this.
The question is whether herma inlines the whole body, warns, or does nothing, and it is unresolved by prior art.

### Connection reuse works, but the context manager is broken

`redmail/email/sender.py` lines 479 to 503:

```python
def send_message(self, msg: EmailMessage):
    "Send the created message"
    if self.is_alive:
        self.connection.send_message(msg)
    else:
        # The connection was opened for this message
        # thus it is also closed with this message
        with self:
            self.connection.send_message(msg)


def __enter__(self):
    self.connect()


def __exit__(self, *args):
    self.close()
```

The open-if-closed rule matches Django's, and it is the right rule.
But `__enter__` returns `None`.
`with sender as s:` binds `s = None`.
The docs quietly work around it by writing `with email:` and never `as`.
Django's base backend gets this right with `return self`.

## blastula

The stated inspiration.
Read from `main`; CRAN has 0.3.6, published 2025-04-03.

### The compose and send split is unusually clean

`R/compose_email.R` line 56:

```r
compose_email <- function(
    body = NULL,
    header = NULL,
    footer = NULL,
    title = NULL,
    ...,
    template = blastula_template
) {
```

`R/smtp_send.R` line 129:

```r
smtp_send <- function(
    email,
    to,
    from,
    subject = NULL,
    cc = NULL,
    bcc = NULL,
    credentials = NULL,
    creds_file = "deprecated",
    verbose = FALSE,
    login_options = NULL,
    ...
) {
```

Read the two lists side by side.
`compose_email()` takes *content only*: three body regions plus an HTML `<title>`.
No recipients, no subject, no sender, no credentials.

`smtp_send()` takes *everything addressed or authenticated*: `to`, `from`, `subject`, `cc`, `bcc`, `credentials`.

Note where `subject` landed.
Most libraries treat the subject as part of the message.
Here it counts as addressing, alongside `to` and `from`, which lets one composed body go to two audiences with two subjects and no recomposition.
That is the whole argument for the split, and it is the design question herma has to answer first.

The result of `compose_email()` is an object with a class tag and four fields (`R/utils-html_manipulation.R` line 414):

```r
structure(
  class = c("blastula_message", "email_message"),
  list(
    html_str = html_cid,
    html_html = HTML(html_data_uri),
    attachments = list(),
    images = as.list(images)
  )
)
```

Two HTML renderings are kept: one with `cid:` references for sending, one with data URIs for previewing.
Printing the object shows the preview in the R viewer, so a user can look at the email before anyone else does.

### `smtp_send()` validates the message type up front

```r
if (!inherits(email, "email_message")) {
  stop(
    "The object provided in `email` must be an ",
    "`email_message` object.\n",
    " * This can be created with the `compose_email()` function.",
    call. = FALSE
  )
}
```

Every error message names the function that produces the missing thing.
The `credentials = NULL` error lists all three helpers with a pointer to each help page.

### Credentials are a first-class object with several constructors

`R/creds_helpers.R`:

```r
creds <- function(
    user = NULL,
    provider = NULL,
    host = NULL,
    port = NULL,
    use_ssl = TRUE
) {

creds_envvar <- function(
    user = NULL,
    pass_envvar = "SMTP_PASSWORD",
    provider = NULL,
    host = NULL,
    port = NULL,
    use_ssl = TRUE
) {

creds_key <- function(id) {

creds_file <- function(file) {
```

Plus `creds_anonymous()`.
All five return a list tagged `c("<specific>", "blastula_creds")`, and `smtp_send()` checks for the shared tag, not the specific one:

```r
if (!inherits(credentials, "blastula_creds")) {
```

So `credentials` is one parameter, and where the secret comes from is a separate, swappable decision.
Five sources, one argument, one type check.
This is the cleanest thing in the survey.

Two supporting details.

`provider` is a preset that fills in `host`, `port` and `use_ssl` (`R/utils.R` line 4):

```r
smtp_settings <- function() {
  # use_ssl means STARTTLS, not smtps://
  dplyr::tribble(
    ~short_name,   ~server,                    ~port, ~use_ssl, ~user,   ~long_name,
    "gmail",       "smtp.gmail.com",           465,   FALSE,    "email", "Gmail",
    "outlook",     "smtp-mail.outlook.com",    587,   TRUE,     "email", "Outlook.com",
    "office365",   "smtp.office365.com",       587,   TRUE,     "email", "Office365.com",
  )
}
```

A named preset that fills defaults beats a mutable preconfigured instance.
It is a value, not shared state.

The credentials object masks its own secret when printed (`R/creds_helpers.R` line 166):

```r
format.blastula_creds <- function(x, ...) {
  if (!is.null(x$password)) {
    x$password <- "****"
  }
```

Herma should write the `__repr__` that does this on day one, before anything gets pasted into an issue.

`creds()` never takes a `password` argument.
It reaches `create_credentials_list()`, whose default is `password = get_password()`, and R evaluates default arguments lazily, so it prompts on demand through `getPass::getPass()`.
That trick has no Python equivalent and should not be emulated.

The write-side functions are separate verbs: `create_smtp_creds_file(file, user, provider, ...)` and `create_smtp_creds_key(id, user, provider, ..., overwrite = FALSE)`, with `view_credential_keys()`, `delete_credential_key()` and `delete_all_credential_keys()` alongside.
Storing a credential and reading one are different operations with different names.

### `add_image()` is a text helper, not a message method

This is the design herma should look at hardest, because herma's premise is caller-supplied HTML.

`R/add_image.R` line 50:

```r
add_image <- function(file, alt = "", width = 520,
  align = c("center", "left", "right", "inline"),
  float = c("none", "left", "right")) {
```

Its documented return value:

> A character object with an HTML fragment that can be placed inside the message body wherever the image should appear.

It takes no email.
It returns an `<img>` tag whose `src` is a base64 data URI (`R/add_image.R` line 82):

```r
get_image_uri <- function(file) {
  if (grepl("^(https?:)?//", file, ignore.case = TRUE)) {
    return(file)
  }
  ...
  paste0(
    "data:", mime::guess_type(file = file), ";base64,",
    base64enc::base64encode(image_raw, 0)
  )
}
```

The conversion to `cid:` happens once, at the end of `compose_email()`, in `cid_images()`.
It walks every `<img src>` in the finished HTML, turns relative paths into data URIs, then rewrites every data URI into a `cid:` reference and collects the bytes:

```r
html_data_uri <-
  replace_attr(html, tag_name = "img", attr_name = "src", function(src) {
    src_to_datauri(src, basedir)
  })
...
cids_key <- digest::digest(src)
cid <- cids[[cids_key]]

if (is.null(cid)) {
  cid <- next_cid(content_type = content_type)
  images[[cid]] <- structure(data, "content_type" = paste0("image/", content_type))
  cids[[cids_key]] <- cid
}

paste0("cid:", cid)
```

Three consequences.
The user never invents or tracks a Content-ID.
Duplicate images are deduplicated by digest, so the same logo used four times is attached once.
And the same code path handles `add_image()`, a hand-written `<img src="logo.png">`, and an image produced by a chart helper, because all three are just HTML by the time `compose_email()` sees them.

The Content-ID format is deliberately non-standard, and the comment explains why:

```r
# According to the spec there should be an @domain on this, but it makes
# attachment UI show up for Outlook.com (e.g. AT00001.bin)
paste0("img", idx, ".", content_type)
```

Anymail hit the same class of bug from the other direction and chose a fake domain.
Both are evidence that the Content-ID string is a compatibility surface, not an implementation detail.

`add_ggplot(plot_object, width = 5, height = 5, alt = NULL, ...)` writes a plot to a temp PNG and returns the same kind of HTML fragment, which is how the chart case stays uniform.

### `add_attachment()` takes the email first, and returns a new one

`R/add_attachment.R` line 22:

```r
add_attachment <- function(
    email,
    file,
    content_type = mime::guess_type(file),
    filename = basename(file)
) {
  ...
  email$attachments <- c(email$attachments, list(attachment_list))
  email
}
```

Email first, return the email.
That is what makes `email %>% add_attachment(...) %>% smtp_send(...)` read.
R's copy-on-modify semantics mean the caller's original object is untouched, so the pipeline builds a new value at each step.

Note the asymmetry with images.
Attachments are a method on the message.
Inline images are a function on text.
That asymmetry is correct: an attachment has no position in the body, an inline image does.

### blastula has three backends and no backend protocol

This is the mistake, and it is the one most relevant to herma.

`R/smtp_send.R`:

```r
smtp_send <- function(email, to, from, subject = NULL, cc = NULL, bcc = NULL, credentials = NULL, ...)
```

`R/send_by_mailgun.R` line 52:

```r
send_by_mailgun <- function(
    message,
    subject = NULL,
    from,
    recipients,
    url,
    api_key
) {
```

Different name for the message (`message` versus `email`).
Different name for the recipients (`recipients` versus `to`).
No `cc`, no `bcc`.
Credentials as two bare arguments instead of a `blastula_creds` object.
Different argument order.

The Posit Connect path is a third shape entirely: `attach_connect_email()` attaches the message to an R Markdown render and Connect sends it later.

So the package that inspired herma has exactly the problem herma exists to solve.
Switching from SMTP to Mailgun in blastula means rewriting the send call.
The message object is portable; the send is not.
Every argument that appears on more than one backend must be spelled identically, or the promise fails on the second backend.

## The skim four

Read from sdists: yagmail 0.16.0 (2026-05-26), Envelopes 0.4 (2013-11-13), emails 1.1.2 (2026-05-18), flanker 0.9.11 (2019-12-05).

### yagmail: everything at the send call, and too much magic

`yagmail/sender.py` line 150:

```python
def send(
    self,
    to: Optional[AddressInput] = None,
    subject: Optional[Union[str, List[str]]] = None,
    contents: Optional[Any] = None,
    attachments: Optional[Any] = None,
    cc: Optional[AddressInput] = None,
    bcc: Optional[AddressInput] = None,
    preview_only: bool = False,
    headers: Optional[Dict[str, str]] = None,
    prettify_html: bool = True,
    message_id: Optional[str] = None,
    group_messages: bool = True,
) -> Union[Tuple[List[str], str], Dict[str, Any], bool]:
```

There is no message object at all.
The client holds only the sender identity and the connection.

`contents` is one argument that means five things.
The dispatch lives in `get_mime_object` (`yagmail/message.py` line 200):

```python
is_raw = type(content_string) is raw
try:
    is_file = os.path.isfile(content_string)
except ValueError:
    is_file = False
    ...
if not is_raw and is_file:
    with open(content_string, "rb") as f:
        content_object["encoding"] = "base64"
        content = f.read()

elif isinstance(content_string, io.IOBase):
    ...
else:
    content_object["main_type"] = "text"

    if is_raw:
        content_object["mime_object"] = MIMEText(content_string, _charset=encoding)
    else:
        content_object["mime_object"] = MIMEText(
            content_string, "html", _charset=encoding
        )
        content_object["sub_type"] = "html"
```

A string is an attachment if `os.path.isfile()` says so, and otherwise it is HTML.
That means the meaning of `yag.send(to, subject, "report.csv")` depends on the working directory.
Create the file and the argument silently changes from body text to an attachment.

The escape hatches are `str` subclasses (`yagmail/utils.py` line 5):

```python
class raw(str):
    """Ensure that a string is treated as text and will not receive 'magic'."""


class inline(str):
    """Only needed when wanting to inline an image rather than attach it"""
```

and the dispatch tests `type(x) is raw`, not `isinstance`.
Needing a marker type to turn the guessing off is the tell that the guessing was wrong.

`attachments` is not a separate path.
It validates that each item is a path or an `io.IOBase`, then concatenates into `contents` and runs the identical dispatch (`message.py` line 66).

Inline images work but you do not control placement (`message.py` line 126):

```python
if type(content_string) is inline:
    htmlstr += f'<img src="cid:{hashed_ref}" title="{alias}"/>'
    content_object["mime_object"].add_header("Content-ID", f"<{hashed_ref}>")
```

The tag is appended to the end of the HTML.
The Content-ID is `str(abs(hash(alias)))`, derived from Python's salted `str.__hash__`, so it changes between runs.

Recipients accept four shapes (`yagmail/headers.py` line 46), and the display-name form is a dict, `{addr: alias}`:

```python
if isinstance(x, str):
    addresses["recipients"].append(x)
    addresses[which] = x
elif isinstance(x, (list, tuple)):
    ...
    addresses[which] = ",".join(x)
elif isinstance(x, dict):
    addresses["recipients"].extend(x.keys())
    addresses[which] = ",".join(x.values())
```

`"Name <a@b.com>"` is not parsed and fails validation, because `validate_email_with_regex` anchors on addr-spec only.
And a bare username gets a domain appended (`headers.py` line 35):

```python
if isinstance(email_addr, str):
    if "@" not in email_addr:
        email_addr += "@gmail.com"
```

Credentials are the best part of the library.
`yagmail/password.py` line 9 reads `keyring.get_password("yagmail", user)`, prompts if that is empty, then offers to save.
`register(username, password)` writes to the keyring.
`oauth2_file=` (`yagmail/oauth2.py` line 98) reads a JSON file, and walks a full Google consent flow if the file is missing, writing the refresh token back.
It is the only library in the survey with a real OAuth story, which matters because two of herma's three backends are OAuth-only.

`SMTP = Client` at `sender.py` line 288 keeps the old name working.

### Envelopes: the cleanest split, and dead since 2013

`envelopes/envelope.py` line 92:

```python
def __init__(self, to_addr=None, from_addr=None, subject=None,
             html_body=None, text_body=None, cc_addr=None, bcc_addr=None,
             headers=None, charset='utf-8'):
```

`envelopes/conn.py` line 82:

```python
def send(self, envelope):
    """Sends an *envelope*."""
    if not self.is_connected:
        self._connect()

    msg = envelope.to_mime_message()
    to_addrs = [
        envelope._addrs_to_header([addr])
        for addr in envelope._to + envelope._cc + envelope._bcc
    ]

    return self._conn.sendmail(msg["From"], to_addrs, msg.as_string())
```

The connection carries no addresses.
The envelope carries no transport.
Of the four skimmed, this is the cleanest division, and it matches Django's.

`Envelope.send()` also exists as sugar, and it is honest about what it does (`envelope.py` line 322):

```python
def send(self, *args, **kwargs):
    """Sends the envelope using a freshly created SMTP connection. *args*
    and *kwargs* are passed directly to :py:class:`envelopes.conn.SMTP`
    constructor.

    Returns a tuple of SMTP object and whatever its send method returns."""
    conn = SMTP(*args, **kwargs)
    send_result = conn.send(self)
    return conn, send_result
```

It returns the connection it made, so the caller can reuse it.
That is a reasonable answer to "the one-off send should not be a dead end", though returning a 2-tuple is a poor shape for it.

Attachments are a path and nothing else (`envelope.py` line 298):

```python
def add_attachment(self, file_path, mimetype=None):
```

No inline images at all.
The root container is `MIMEMultipart('alternative')` with attachments appended as siblings, so there is no `multipart/related` subtree to hang a `cid:` part on.

Address forms are documented in the class docstring (`envelope.py` line 69):

```text
* ``"user@server.com"`` - just the e-mail address part as a string,
* ``"Some User <user@server.com>"`` - name and e-mail address parts as a string,
* ``("user@server.com", "Some User")`` - e-mail address and name parts as a tuple.
```

Note the tuple order is `(address, name)`, which is backwards from `email.utils.parseaddr` and from every other library here.
Worse, the `"Name <addr>"` string form is only split on the non-ASCII path, so an ASCII display-name string reaches `sendmail()` unsplit and goes into the SMTP envelope as `"Some User <a@b.com>"`.

The preconfigured connections are classes, not instances (`conn.py` lines 99 to 121): `GMailSMTP`, `SendGridSMTP`, `MailcatcherSMTP`.
That is the right shape.
`GMailSMTP('user', 'pass')` gives you a fresh object with the host and TLS already filled in, and no shared state.
Compare redmail's `redmail.gmail` singleton.

`envelopes/connstack.py` adds a thread-local connection stack borrowed from rq: `push_connection`, `pop_connection`, `use_connection`, `get_current_connection`, and a `Connection(conn)` context manager.
It solves "the web request handler should not know which SMTP server is configured" without a global settings module.
Django solved the same problem with a settings alias instead.

### emails: the transformer is the reason to read it

`emails/message.py` line 38:

```python
def __init__(self,
             charset: str | None = None,
             message_id: str | MessageID | bool | None = None,
             date: str | datetime | float | bool | Callable[..., str | datetime | float] | None = None,
             subject: str | None = None,
             mail_from: _Address = None,
             mail_to: _AddressList = None,
             headers: dict[str, str] | None = None,
             html: str | IO[str] | None = None,
             text: str | IO[str] | None = None,
             attachments: list[dict[str, Any] | BaseFile] | None = None,
             cc: _AddressList = None,
             bcc: _AddressList = None,
             headers_encoding: str | None = None,
             reply_to: _AddressList = None) -> None:
```

`emails.html(**kwargs)` (`message.py` line 565) is a bare alias for `Message(**kwargs)`, so the friendly-looking constructor is not doing anything.

`Message.send` (`message.py` line 425):

```python
def send(self,
         to: _AddressList = None,
         set_mail_to: bool = True,
         mail_from: _Address = None,
         set_mail_from: bool = False,
         render: dict[str, Any] | None = None,
         smtp_mail_options: list[str] | None = None,
         smtp_rcpt_options: list[str] | None = None,
         smtp: dict[str, Any] | SMTPBackend | None = None) -> Any:
```

Recipients live on the message, but `send(to=...)` overwrites them by default (`message.py` line 396):

```python
if to:
    if set_mail_to:
        self.set_mail_to(to)
    else:
        to_addrs = [a[1] for a in parse_name_and_email_list(to)]
```

So the same `Message` object sent twice to two people ends up mutated, and the second send has the first recipient's `To:` header gone.
`set_mail_to=False` gets envelope-only delivery.
A boolean that changes whether an argument mutates the receiver is a bad shape.
The underlying need is real and herma will hit it: sending one composed body to many recipients individually.

Attachments are kwargs-only (`message.py` line 203):

```python
def attach(self, **kwargs: Any) -> None:
    if "content_disposition" not in kwargs:
        kwargs["content_disposition"] = "attachment"
    self.attachments.add(kwargs)
```

The real signature is `BaseFile.__init__`'s kwarg reads (`emails/store/file.py` line 34): `uri`, `absolute_url`, `filename`, `data`, `mime_type`, `headers`, `content_id`, `content_disposition`, `subtype`, `local_loader`.
`data` takes bytes, str, or anything with `.read()`.
There is no path argument; you open the file yourself.
MIME type resolution is three-tier: explicit, then `mimetypes.guess_type(filename)`, then content sniffing with `puremagic` on the first 128 bytes.

Inline images are the same object with a different disposition (`store/file.py` line 138):

```python
@property
def is_inline(self):
    return self.content_disposition == "inline"


@property
def content_id(self) -> str | None:
    if self._content_id is None:
        self._content_id = self.filename
    return self._content_id
```

The Content-ID defaults to the filename.
So the author writes `<img src="cid:logo.png">` and attaches `filename="logo.png"`, and it works with no generated identifier anywhere.
That is a genuinely nice trade: readable HTML, at the cost of a filename collision being a cid collision.
Placement in the MIME tree follows the disposition (`message.py` line 330): inline parts go in the `multipart/related` subtree, the rest onto the root.

The transformer is the capability nothing else here has.
`emails/transformer.py` line 290:

```python
def load_and_transform(self,
                       css_inline=True,
                       remove_unsafe_tags=True,
                       make_links_absolute=True,
                       set_content_type_meta=True,
                       update_stylesheet=False,
                       load_images=True,
                       images_inline=False,
                       **kw):
```

Five steps: run premailer to inline external and `<style>` CSS onto `style=` attributes, download every `<img src>` and CSS `url()` into the attachment store and rewrite the src, strip `UNSAFE_TAGS = ['script', 'object', 'iframe', 'frame', 'base', 'meta', 'link', 'style']`, inject a content-type meta tag, and optionally flip every image to inline and rewrite to `cid:`.

The rewrite is bidirectional (`transformer.py` line 360):

```python
def _src_update_func(src, **kw):
    if src.startswith("cid:"):
        content_id = src[4:]
        if content_id in non_inline_names:
            return non_inline_names[content_id]
    else:
        if src in inline_names:
            return "cid:" + inline_names[src]
    return src
```

`emails/loader/__init__.py` builds on it: `from_html`, `from_url`, `from_directory`, `from_file`, `from_zip`, `from_rfc822`.
Every loader runs the transformer during construction (`loader/__init__.py` line 54), so `from_url("https://.../campaign.html")` returns a `Message` whose CSS is already inlined and whose images are already downloaded.
The whole thing needs lxml, premailer, requests and cssutils, which puts it outside herma's zero-dependency core.
It is the reference for what a `herma[html]` extra could do.

Address parsing is the most permissive here, and it has one genuine ambiguity (`emails/utils.py` line 137):

```python
if len(elements) == 2:
    # Oops, it may be pair (name, email) or pair of emails [email1, email2]
    # Let's do some guesses
    if isinstance(elements, tuple):
        n, e = elements
        if isinstance(e, str) and (not n or isinstance(n, str)):
            # It is probably a pair (name, email)
            return [
                parse_name_and_email(elements, encoding),
            ]
```

A 2-tuple is `(name, email)`; a 2-list is two addresses.
The comment says "Let's do some guesses", which is the correct level of confidence and the wrong design.
Tuple order here is `(name, email)`, the reverse of Envelopes.

`"Name <addr@x.com>"` is parsed with stdlib `parseaddr`.
Header injection is blocked explicitly (`message.py` line 245):

```python
if "\n" in value or "\r" in value:
    raise BadHeaderError(
        "Header values can't contain newlines (got %r for header %r)" % (value, key)
    )
```

The send result is a real object (`emails/backend/response.py` line 31):

```python
class SMTPResponse(Response):
    def __init__(self, exception: Exception | None = None, backend: Any = None) -> None:
        super(SMTPResponse, self).__init__(exception=exception, backend=backend)
        self.responses: list[list] = []
        self.esmtp_opts: list[str] | None = None
        self.rcpt_options: list[str] | None = None
        self.status_code: int | None = None
        self.status_text: bytes | None = None
        self.last_command: str | None = None
        self.refused_recipients: dict[str, tuple[int, bytes]] = {}
```

`success` is `self._finished and self.status_code == 250`, and the base carries `.error` and `.raise_if_needed()`.
`refused_recipients` is the field herma will want: partial failure is the normal case when sending to a list.
The bad part is that `fail_silently=True` is the backend default, so errors land on the response instead of raising, and the send can return `None` when there are no recipients.

### flanker: not a sender, and the only real address parser

`grep -rn "smtplib\|sendmail\|SMTP"` over `flanker/` hits five comments about how SMTP servers mangle line endings, and nothing else.
`setup.py` describes it as `'Mailgun Parsing Tools'`.
It is here for two things.

**Address parsing** (`flanker/addresslib/address.py` line 67):

```python
@metrics_wrapper()
def parse(address, addr_spec_only=False, strict=False, metrics=False):
```

It returns an `EmailAddress`, a `UrlAddress`, or `None`.
It never raises on bad input.
The parser is a real PLY lex/yacc grammar under `flanker/addresslib/_parser/`, with pre-generated tables committed, not a regex.

The relaxed fallback is worth noting (`address.py` line 117):

```python
if addr_obj is None and not strict:
    addr_parts = address.split(" ")
    addr_spec = addr_parts[-1]
```

so `'Foo foo@example.com'` parses with `Foo` as the display name.

`parse_list(address_list, strict=False, as_tuple=False, metrics=False)` (`address.py` line 188) returns an `AddressList`, or `(AddressList, unparsed)` with `as_tuple=True`.
Returning the failures alongside the successes is better than raising on the first bad address in a list of a thousand.

`EmailAddress` carries `.address`, `.display_name`, `.mailbox`, `.hostname`, `.ace_address`, `.ace_hostname`, `.full_spec()`, `.to_unicode()`, `.contains_non_ascii()`, `.requires_non_ascii()`, and defines `__eq__` and `__hash__`, so addresses work as set members and dict keys.
`AddressList.__add__` returns a new `AddressList`, which is the only new-instance-returning operator anywhere in this survey.

Validation is a separate tier, not part of parsing: `validate_address()` and `validate_list()` add DNS and MX lookups plus per-provider grammar plugins for aol, gmail, google, hotmail, icloud and yahoo, behind a `validator` extra.
Splitting "is this a well-formed address" from "does this mailbox plausibly exist" is the right seam, and it is exactly the distinction herma's open question about build-time versus send-time validation is groping for.

**MIME construction** (`flanker/mime/create.py`):

```python
def multipart(subtype):
def message_container(message):
def text(subtype, body, charset=None, disposition=None, filename=None):
def binary(maintype, subtype, body, filename=None,
           disposition=None, charset=None, trust_ctype=False):
def attachment(content_type, body, filename=None,
               disposition=None, charset=None):
def from_string(string):
```

`attachment()` sniffs: filename extension first, then `imghdr.what()` on the first 32 bytes for images, then audio detection.
`body` is bytes or str, never a path.
There is no cid helper.

The package docstring states the selling point: about 50ms to parse an 11MB message against about 1s for the stdlib parser, and unchanged parts round-trip byte-identical.
The tradeoff is stated too: the parser is strict and raises `MimeError` on broken MIME, with `mime.recover` as the lenient fallback.

## Where each thing lives

M = on the message object.
S = on the sender or backend.
C = at the send call.

| Library | Recipients | Subject | Body | Attachments | Credentials | Who owns `send` |
| --- | --- | --- | --- | --- | --- | --- |
| Django | M | M | M | M | S (`MAILERS` alias) | Backend. `message.send(using=...)` delegates |
| django-anymail | M | M | M | M | S (`MAILERS` alias) | Backend, same as Django |
| redmail | S or C | S or C | S or C | C | S | Sender. One object does both |
| blastula | C | C | M | M (`add_attachment`) | C (`credentials=`) | Free function `smtp_send(email, ...)` |
| yagmail | C | C | C | C | S (constructor, keyring, OAuth file) | Client |
| Envelopes | M | M | M | M | S (connection) | Connection. `envelope.send(...)` builds one |
| emails | M, overwritten by C | M | M | M | C (`smtp=` dict) or S (`SMTPBackend`) | Message, given a backend |
| flanker | n/a | n/a | n/a | n/a | n/a | Does not send |

Three patterns, and they are not equally good.

**Message holds content and addressing, backend holds transport.**
Django, Anymail and Envelopes.
The message is a portable value.
Any backend can send it.
This is the only arrangement that survives the second backend.

**Sender holds everything, with per-send overrides.**
Seen in redmail and yagmail.
Convenient for a script, and it collapses the moment you want to hand a composed message to something else.
There is no object to hand.

**Content on the message, addressing at the send.**
Only blastula does this.
It buys a genuine capability: one composed body, many audiences, without recomposing.
It costs a longer send signature and it puts `subject` somewhere nobody expects.

## Method chaining

Almost nobody chains, and the two that do are instructive.

| Library | Chains | Mutates or returns new |
| --- | --- | --- |
| Django | No. `attach`, `attach_file`, `attach_alternative` all return `None` | Mutates |
| django-anymail | No. `attach_inline_image` returns the content id, not the message | Mutates |
| redmail | No. Attributes are set by assignment | Mutates |
| blastula | Yes, with `%>%` | Returns a new value, by R's copy-on-modify |
| yagmail | No. There is nothing to chain | n/a |
| Envelopes | No. `add_to_addr`, `add_attachment` return `None` | Mutates |
| emails | Partly. `Message.sign()` returns `self`; the transformer methods return `self`. `attach()` and the setters return `None` | Mutates |
| flanker | Only `AddressList.__add__`, which returns a new `AddressList` | New instance |

So there is no Python precedent for a chaining email builder.
Chaining works in blastula because the R pipe makes `f(x, ...)` read as `x %>% f(...)`, and because R copies values on modify, so each step is a new object for free.

That matters for herma.
A `return self` builder chains but mutates.
Reusing a half-built message then becomes a foot-gun: two chains from the same base share state.
R has no such problem, so copying blastula's *feel* without copying its *semantics* imports the bug.

Two honest options.
Either build a frozen message with a `replace`-style API where every step returns a new instance, or drop chaining and take Django's route of a constructor plus a few mutating methods.
`emails` shows the halfway house is confusing: `sign()` chains and `attach()` does not, so the reader has to memorize which is which.

One more data point.
`attach_inline_image()` in Anymail returns the content id, not the message, and it has to, because the caller needs that id for the `src` attribute.
Any inline-image method that returns `self` cannot also hand back the identifier.
The question never arises in blastula, which generates no id the user sees.

## Names worth stealing

**`backend`, for the thing that sends.**
Django, Anymail and every third-party ESP package use it.
`EmailBackend` is the class name in all five of Django's own modules.
`transport` is smtplib's word and means the protocol; `sender` collides with the From address, which is exactly the collision redmail lives with (`EmailSender.sender`).

**`using=`, for choosing a backend at the send call.**
Django 6.1 chose it to match `QuerySet.using()`.
It is short, it reads in place (`email.send(using="notifications")`), and it takes a string, so it survives config.

**A configured backend gets an alias, not a variable.**
Django's `MAILERS` dict with a `"default"` key.
The alias is the stable name a caller refers to; the object is created on demand.
`DEFAULT_MAILER_ALIAS = "default"` is a named constant, not a bare string.

**`credentials`, as one argument taking a tagged object with several constructors.**
From blastula: `creds()`, `creds_key()`, `creds_file()`, `creds_envvar()`, `creds_anonymous()`.
Where the secret lives is orthogonal to which backend uses it, so it should not be five backend arguments.

**`provider`, for a host and port preset.**
In blastula, `creds(provider = "gmail")` fills `host`, `port` and `use_ssl` from a table.
A preset is data.
Compare redmail's `redmail.gmail`, which is a preset baked into a mutable singleton.

**`attach_alternative(content, mimetype)`.**
Django's name for the second body representation.
It says what MIME calls it and it does not privilege HTML over text.

**`recipients()`, as a method that unions to, cc and bcc.**
Django.
The envelope needs the union; the headers need them apart.
Naming the union makes the SMTP backend's job one call, and gives subclasses one thing to override.

**`sent_using`, on a recorded message.**
Django's locmem backend stamps the alias onto each copy in the outbox.
A test can then assert which mailer a code path chose, not just that it sent something.

**`esp_extra`, for the provider-specific escape hatch.**
Anymail. herma's equivalent would name the concept, not a vendor: something like `backend_extra`.

**`unsupported_feature(feature)`, as a method on the backend.**
Anymail.
One place to route "this backend cannot do that", one exception type, one setting to silence it.

**`raw()` and `inline()` as marker types is a name worth stealing from a design worth avoiding.**
They exist because yagmail guesses.
If herma never guesses, it never needs them, but the words are the right words if a marker is ever necessary.

## Mistakes worth avoiding

**Do not guess what a string means.**
In yagmail, a string is an attachment when `os.path.isfile()` is true, and HTML otherwise.
The meaning of the call changes with the working directory.
Distinct arguments (`html=`, `text=`, `attachments=`) cost nothing and never surprise.

**Do not let the same type mean different things in different containers.**
In redmail, a `str` is a path inside a list and raw content as a dict value.
`attachments=["report.csv"]` reads a file; `attachments={"report.csv": "report.csv"}` attaches six characters.

**Do not ship preconfigured mutable singletons.**
`redmail.gmail` is a module-level `EmailSender`, and the documented usage is `gmail.password = '...'`.
That makes credentials process-global.
Envelopes gets this right with `GMailSMTP` as a class.

**Do not let a send-call argument silently mutate the message.**
`emails.Message.send(to=...)` rewrites `mail_to` unless you pass `set_mail_to=False`.
The second send from the same object is not the message you built.

**Do not name the same thing differently on two backends.**
Compare blastula's `smtp_send(email, to, from, subject, cc, bcc, credentials, ...)` against `send_by_mailgun(message, subject, from, recipients, url, api_key)`.
Different word for the message, different word for the recipients, no cc or bcc, credentials as loose arguments.
The composed message is portable and the send is not, which is the exact failure herma exists to prevent.
Fix it by writing the send signature once, as a protocol, and making every backend implement that signature and nothing else.

**Do not invent a new tuple order for `(name, address)`.**
Envelopes uses `(address, name)`; emails uses `(name, address)`; stdlib `parseaddr` returns `(name, address)`.
Follow the stdlib or use a named type.

**Do not return `self` from `__enter__` by accident.**
In redmail, `__enter__` returns `None`, so `with sender as s:` binds nothing, and the docs quietly avoid `as`.

**Do not offer `fail_silently`.**
Django deprecated it in 6.1 after fifteen years.
An argument that turns an exception into a silent `return 0` moves the failure to the next person to read the logs.
`emails` has the same problem with `fail_silently=True` as the backend default.

**Do not accept a bare string where a list of addresses is meant.**
Django raises `TypeError('"to" argument must be a list or tuple')` for all four address fields.
The alternative is `to="a@b.com"` iterating into eleven single-character recipients on the day someone passes the wrong variable.
Herma may want to accept a bare string deliberately, but it should be a decision with a normalization function behind it, not an accident.

**Do not run caller-supplied HTML through a template engine by default.**
In redmail, `use_jinja=True` is the default and every body gets rendered.
The brief for herma is HTML the caller already composed.
Rendering it breaks any literal `{{`, and it is an injection surface when the HTML did not come from the developer.

**Do not silently ignore unknown configuration keys.**
Django's pre-`MAILERS` backends accepted any kwarg.
The new path raises `InvalidMailer(f"Unknown options {kwarg_names}.", alias=alias)`.
A typo in `use_tsl` should fail at startup, not send in the clear.

## Capabilities herma has not yet considered

Ordered by how likely each is to force a change to the v1 surface.

**A normalized send result with per-recipient status.**
Anymail's `ANYMAIL_STATUSES` is `sent`, `queued`, `invalid`, `rejected`, `failed`, `unknown`, and `AnymailRecipientStatus(message_id, status)` carries one per recipient.
`emails`' `SMTPResponse.refused_recipients` is a dict of address to `(code, text)`.
Partial failure is the normal case for a multi-recipient send, and all three of herma's backends report it differently.
Django's `send()` returns an `int`, which is the answer herma should not copy.

**An explicit unsupported-feature policy.**
Anymail's `unsupported_feature()` raises by default and can be silenced with a setting.
Its docstring also draws the line herma needs: raise for things the API cannot express, but let the provider report its own limits rather than duplicating each provider's validation locally.
This is the mechanism for herma's open `from_` question.

**A named escape hatch for provider-specific fields.**
`esp_extra`.
Without one, every provider-only feature either bloats the shared surface or forces users off herma entirely.

**Content-ID as a compatibility surface, not an implementation detail.**
Anymail defaults the cid domain to the literal `"inline"` because Gmail blocks Content-IDs ending in `.com` when a provider reuses the cid as a filename.
The `@domain` is omitted entirely in blastula, because including it makes Outlook.com show a phantom `AT00001.bin` attachment.
Two independent projects hit client-specific bugs in the same three-character string.
Whatever herma generates needs a test against these two known cases.

**Harvesting `cid:` references out of finished HTML.**
In blastula, `cid_images()` walks every `<img src>` in the rendered body, converts local paths and data URIs into `cid:` references, attaches the bytes, and deduplicates identical images by digest.
The user never types a Content-ID.
Given that herma takes caller-supplied HTML, this is the most directly applicable idea in the survey, and it is not on herma's list.
`emails`' transformer does the same walk and adds downloading remote images.

**Deduplicating repeated inline images.**
The key in blastula is `digest::digest(src)`.
A logo used in a header and a footer attaches once.

**A file-format-from-filename convention for structured attachments.**
Compare redmail's `attachments={'data.xlsx': df}` against `{'data.csv': df}`.
The extension picks the serializer.
Behind an optional-import guard this costs the core nothing, and it is the difference between herma being usable in a report script and not.

**Optional-dependency dispatch as a general pattern.**
In redmail, `import_from_string(..., if_missing="ignore")` returns `None`, and every dispatch branch is guarded by `has_pandas` and friends.
This is how a zero-dependency core grows type-aware conveniences without taking a dependency.

**A test backend that records more than the messages.**
Django's locmem calls `message.message()` first so header validation still fires, deep-copies so later mutation cannot fool an assertion, and stamps `sent_using = self.alias`.
`body_contains(text)` checks the plain body and every `text/*` alternative, because the classic bug is updating the HTML and forgetting the fallback.

**Splitting address parsing from address validation.**
In flanker, `parse()` (grammar, never raises, returns `None`) is separate from `validate_address()` (DNS and MX lookups, provider-specific grammars).
`parse_list(..., as_tuple=True)` returns the successes and the failures together instead of raising on the first bad one.
That shape answers herma's open build-time-versus-send-time question directly.

**Rendering the composed message for preview before sending.**
In blastula the message carries two HTML strings: one with `cid:` for sending and one with data URIs for viewing, and printing the object shows the preview.
There is a `preview_only=True` in yagmail, which returns `(recipients, message_string)` without connecting.
Both are cheap and both catch the mistake before it reaches an inbox.

**A connection stack, as an alternative to a settings alias.**
`envelopes.connstack` gives `push_connection` / `get_current_connection` and a context manager over a thread-local.
Django solved the same problem with a named alias in settings.
There is no settings module in herma, so the stack is worth knowing about even if the answer is to pass the backend explicitly.

**HTML preparation as an extra: CSS inlining, unsafe-tag stripping, absolute links.**
`emails`' `load_and_transform()` does all of it, plus downloading remote images into attachments.
None of this happens in redmail: its `style` extra only inlines CSS on pandas `Styler` output, never on the email body.
So herma's open CSS-inlining question has no prior art in redmail at all, and the real reference is `emails` plus the `css-inline` package itself.

**A logging handler that emails records.**
There is `EmailHandler` and `MultiEmailHandler` in redmail; Django ships `AdminEmailHandler` with a `using` option.
Out of scope for v1, but it is the strongest argument for making the backend constructible from a plain dict of options: a logging config is a dict.

## Sources

Read directly, not summarized.

Django, `main` at `e2a3da142687c3b3dfa9cbc63c1a1a4433a8f842`:

- [`django/core/mail/__init__.py`](https://github.com/django/django/blob/main/django/core/mail/__init__.py)
- [`django/core/mail/message.py`](https://github.com/django/django/blob/main/django/core/mail/message.py)
- [`django/core/mail/handler.py`](https://github.com/django/django/blob/main/django/core/mail/handler.py)
- [`django/core/mail/exceptions.py`](https://github.com/django/django/blob/main/django/core/mail/exceptions.py)
- [`django/core/mail/backends/`](https://github.com/django/django/tree/main/django/core/mail/backends): `base.py`, `smtp.py`, `console.py`, `filebased.py`, `locmem.py`, `dummy.py`
- [`docs/topics/email.txt`](https://github.com/django/django/blob/main/docs/topics/email.txt) and `docs/ref/settings.txt`
- [Django 6.1 release notes](https://docs.djangoproject.com/en/dev/releases/6.1/)

django-anymail 15.2:

- [`anymail/message.py`](https://github.com/anymail/django-anymail/blob/main/anymail/message.py)
- [`anymail/exceptions.py`](https://github.com/anymail/django-anymail/blob/main/anymail/exceptions.py)
- [`anymail/backends/base.py`](https://github.com/anymail/django-anymail/blob/main/anymail/backends/base.py)
- [ESP feature matrix](https://anymail.dev/en/stable/esps/)

redmail 0.6.0 sdist:

- [`redmail/email/sender.py`](https://github.com/Miksus/red-mail/blob/v0.6.0/redmail/email/sender.py)
- [`redmail/email/attachment.py`](https://github.com/Miksus/red-mail/blob/v0.6.0/redmail/email/attachment.py)
- [`redmail/email/body.py`](https://github.com/Miksus/red-mail/blob/v0.6.0/redmail/email/body.py)
- [`redmail/email/utils.py`](https://github.com/Miksus/red-mail/blob/v0.6.0/redmail/email/utils.py), `redmail/email/__init__.py`, `redmail/log.py`
- `pyproject.toml`, `docs/tutorials/attachments.rst`, `docs/tutorials/jinja_support.rst`, `docs/tutorials/embed/table.rst`, `docs/tutorials/sending.rst`, `docs/tutorials/testing.rst`
- [redmail docs](https://red-mail.readthedocs.io/en/stable/tutorials/config.html)

blastula, `main`:

- [`R/compose_email.R`](https://github.com/rstudio/blastula/blob/main/R/compose_email.R)
- [`R/smtp_send.R`](https://github.com/rstudio/blastula/blob/main/R/smtp_send.R)
- [`R/creds_helpers.R`](https://github.com/rstudio/blastula/blob/main/R/creds_helpers.R), `R/create_credentials.R`
- [`R/add_image.R`](https://github.com/rstudio/blastula/blob/main/R/add_image.R), `R/add_attachment.R`, `R/add_ggplot.R`
- [`R/utils-html_manipulation.R`](https://github.com/rstudio/blastula/blob/main/R/utils-html_manipulation.R), `R/utils.R`, `R/send_by_mailgun.R`, `R/connect_email.R`

Skimmed, from sdists:

- yagmail 0.16.0: `yagmail/sender.py`, `message.py`, `headers.py`, `utils.py`, `password.py`, `oauth2.py`, `validate.py`, `README.md`
- Envelopes 0.4: `envelopes/envelope.py`, `conn.py`, `connstack.py`, `README.rst`, `examples/example_flask.py`
- emails 1.1.2: `emails/message.py`, `transformer.py`, `utils.py`, `store/file.py`, `store/store.py`, `backend/response.py`, `backend/smtp/backend.py`, `loader/__init__.py`, `README.rst`
- flanker 0.9.11: `flanker/addresslib/address.py`, `flanker/mime/create.py`, `flanker/mime/message/part.py`, `flanker/mime/__init__.py`, `README.rst`

Other:

- [`css-inline` on PyPI](https://pypi.org/project/css-inline/)

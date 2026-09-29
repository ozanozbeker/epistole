# A README example for every public name

The README does not show every public name in an example.
It shows the names a caller writes in the scenarios it walks through.

## Why this is out of scope

The README is a user guide, ordered by scenario.
An example for every public name would make it a reference manual.
Some public names matter to no scenario: a caller reads `AccessToken`, `Attachment` and `Message.inline_images`, and never writes them.
`Backend`, `Transport` and `Submission` matter only to a third-party backend.

The docs website will document every public name in its API reference.
`great-docs` builds that reference from the docstrings, so a name's example goes in its docstring.

## Prior requests

- #61: "Show every public name in a README example that runs"

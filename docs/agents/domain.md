# Domain Docs

This file sets how the engineering skills read this repo's domain documentation when they explore the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, or
- **`CONTEXT-MAP.md`** at the repo root, if it exists.
  It points at one `CONTEXT.md` per context.
  Read each one relevant to the topic.
- **`docs/adr/`**: read the ADRs that concern the area you're about to work in.
  In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.

If any of these files don't exist, **proceed silently**.
Don't flag their absence.
Don't suggest creating them upfront.
The `/domain-modeling` skill creates them lazily, when terms or decisions get resolved.
`/grill-with-docs` and `/improve-codebase-architecture` both run it.

## File structure

Most repos are single-context and look like this:

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

A multi-context repo has a `CONTEXT-MAP.md` at the root:

```text
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`.
Don't switch to synonyms the glossary explicitly lists as avoided.

If the concept you need isn't in the glossary yet, one of two things is true.
Either you're inventing language the project doesn't use, so reconsider.
Or the glossary really lacks the term, so note it for `/domain-modeling`.

## Flag ADR conflicts

If your output contradicts an existing ADR, state the conflict explicitly rather than silently overriding the ADR:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_

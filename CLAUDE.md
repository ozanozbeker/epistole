# CLAUDE.md

## Agent skills

### Issue tracker

Agents manage GitHub Issues on `ozanozbeker/epistole` with the `gh` CLI.
See `docs/agents/issue-tracker.md`.

### Triage labels

The tracker uses the five canonical triage role names as its labels.
See `docs/agents/triage-labels.md`.

### Domain docs

The repo has one context, so `CONTEXT.md` and `docs/adr/` are at the repo root.
See `docs/agents/domain.md`.

## Writing

These rules cover every piece of prose I read: docstrings, comments, error messages, config comments, documentation, commit messages, issues and chat.

### Plain language

ISO 24495-1 sets the standard.
It requires four things of every piece of prose: the reader gets what they need, finds it fast, understands it on one pass, and can act on it.

In practice, that means:

- Write one idea per sentence.
  A sentence that needs two commas to join its clauses should be two sentences.
- Use active voice and the present tense.
  Name the thing that acts, and name it first.
- Use common words.
  Write `because`, not `on the grounds that`.
  Write `so`, not `which is what makes`.
- Avoid cleft constructions.
  Write `Sharing it stops two checks disagreeing`, not `sharing it is what stops two checks from disagreeing`.
- Put the point first.
  The first sentence gives the answer.
  The rest gives the reason.
- Keep the domain word.
  Simplify the grammar, not the vocabulary: `quarantine`, `partition` and `materialization` stay.

### Say what happens, without figures of speech

Do not use metaphors, analogies or personification.
Code does not refuse, decide, know, learn, ask, answer or promise: it raises, sets, reads, receives, returns and guarantees.
Data does not land, arrive, ride or survive: the code writes, passes, copies and keeps it.

Give every sentence a verb, including a heading's description or a caption.
"The decorator, and the spec that puts a quarantine in the graph" becomes "`dd.asset` builds an asset, and `quarantine_spec` adds its quarantine to the asset graph".

Use the word an upstream library already uses, in the meaning it has there.
A step is Dagster's, a member is Dataframely's, and Polars collects a plan.
Coin a term only for something the code names, such as a function, a class or a setting.
Where the repo keeps a glossary, define the term there and list the words it replaces beside it.

### Never use em dashes

Do not write `—`, or a `--` that stands in for one.
This applies everywhere: code, comments, docstrings, commit messages, issues, PR descriptions, and prose written for me to read.

Use a colon, a semicolon, a comma, or a second sentence.
An em dash almost always brackets an aside that reads better as its own sentence.

### Voice

Write in Hadley Wickham's voice: short declarative sentences, plain words, active voice, concrete over abstract.

Weight the content differently than he does, though.
His readers are end users who will never open the source, so his docs cover "how do I use this".
My reader is a future engineer, usually me, so prefer implementation rationale: why this library or base class was chosen over the alternative, why a name deviates from convention, why a check runs at this layer.
Keep "how to use this" for genuinely public surface.

State what a reader cannot infer from the code, in as few plain sentences as it needs.
A reader can reconstruct usage.
They cannot reconstruct rationale.

### Never write down the obvious

My reader is an engineer.
Anything they can determine by looking at the thing in front of them does not need saying.
Saying it makes the sentence that does need saying harder to find.

This matters most in prose addressed to me: PR bodies, issue comments, release notes, chat.
Before writing a justification, ask whether it is reconstructable from `git log`, the repo's own docs, or a config or workflow file I wrote.
If it is, delete it.
A release PR body is one line naming what the bump changes, not an argument for why the version is what I already told you it is.

Write what was measured, what surprised you, and what I could not have known.
Write nothing else.

### Keep prose short

Across a source tree, docstrings and comments stay under 40% of the characters.
Measure it when a rewrite is the point.
These limits keep it there:

- A private function's docstring is its summary line.
  Add a sentence only for a reason that the name, the annotation and the body do not show.
- A module docstring is at most three sentences: what the module holds, how it relates to the modules beside it, and the one constraint a maintainer must know.
- A comment is one line, and only for a reason the code does not show.
  It records no history and does not restate the code.
- A test's docstring is one sentence naming the behaviour under test.
- A measurement or a declined design goes in the repo's own record, and the docstring links to it in one sentence.

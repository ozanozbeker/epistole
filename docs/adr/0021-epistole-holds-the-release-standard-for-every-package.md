# Epistole holds the release standard for every package

Epistole's `CONTRIBUTING.md` holds the release standard for the maintainer's Python packages.
A package that follows it copies the standard's files, records the Epistole commit it copied, and lists where it departs.
A change to a standard file merges in Epistole first, then in each package that follows it.
Decided on 2026-10-15, after the maintainer decided on 2026-10-11 to delete oxyscraper, the previous reference repo.
[The CI/CD research note](../research/ci-cd-standard.md) holds the review behind this decision and oxyscraper's decision record.

## Why

- Three standards existed by 2026-10-11, because each repo copied a template or another repo once and then changed on its own.
  The maintainer set up dagster-dataframely's CI on 2026-08-07, Epistole's release flow on 2026-09-07, and oxyscraper's standard, the most complete of the three, on 2026-09-28.
- Epistole copied oxyscraper's standard on 2026-09-30 at 04:22 UTC.
  From 18:26 UTC that day, oxyscraper merged 9 more CI changes.
  None reached Epistole before 2026-10-15, including the fix that let a `deps:` pull request title pass the `title` check.
- Epistole is the package that stays.
  Its `CLAUDE.md` already imports `CONTRIBUTING.md`, so every session reads the rules from the one copy.
- With the recorded commit, one `git diff` lists the standard changes a package lacks.
  The merge-order rule sets which repo changes first.

## Considered options

- **A copier template, kept up to date with `copier update`.**
  Rejected because the template is a third copy to maintain.
  `copier update` checks out the newest PEP 440 tag.
  Epistole's tags are package releases, so every update needs `--vcs-ref=HEAD`.
  Dependabot reads only `*.yml` and `*.yaml` files in `.github/workflows`, so the action pins inside a `ci.yml.jinja` would never move.
- **Reusable workflows called with `workflow_call`.**
  Rejected because PyPI does not accept trusted publishing from a reusable workflow, so the publish job stays in each repo.
  A called job's check is named `<caller> / <called>`, so every ruleset changes.
  Of the 7 missed commits that changed files every package shares, a reusable workflow would have carried the workflow half of 4 and none of the `prek.toml` changes.
- **A composite action for the checkout, setup-uv and sync steps.**
  Rejected because it adds one pin per job to save about 6 lines, and it carries none of the missed changes.
- **A required CI job that compares each package's shared files with Epistole's.**
  A 119-line stdlib prototype passed at Epistole's copy point and failed at oxyscraper#83 and #91, the first two missed changes to shared files.
  Deferred because, with one follower, the job would fail every Dependabot and release pull request there after each Epistole change.
  Add it when a third package follows the standard.

## Consequences

- `CONTRIBUTING.md` holds the standard first and Epistole's departures last.
  An agent in a follower imports the whole file, reads the standard's rules first, and can skip the last section.
- A package in maintenance applies only the security settings that `CONTRIBUTING.md` names, and owes no catch-up pull request.
- The maintainer's global `CLAUDE.md` names `~/Dev/epistole` as the reference repo for new packages.

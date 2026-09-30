# Contributing

This file follows the release standard for the maintainer's Python packages, and oxyscraper is its reference repo.
[How is oxy versioned, documented and released?](https://github.com/ozanozbeker/oxyscraper/issues/22) records each decision and the evidence for it.
Epistole departs from it in one place: its [Python versions](#python-versions).
A repo that adopts the standard follows the one-time setup in [oxyscraper's copy](https://github.com/ozanozbeker/oxyscraper/blob/main/CONTRIBUTING.md#a-new-repo).

## Setup

You need [uv](https://docs.astral.sh/uv/) and the [GitHub CLI](https://cli.github.com/).

```sh
uv sync
uv run prek install
```

`prek install` writes a `pre-commit` hook, which runs the linters, and a `commit-msg` hook, which checks the message format.
The tests run in CI, not in a hook.

## Pull requests

Every change reaches `main` through a pull request, the maintainer's included.
CI then runs before the change lands.

```sh
git switch main && git pull
git switch -c <branch>
git commit
git push
gh pr create --fill
gh pr merge --auto --squash
```

- `git commit` runs the `pre-commit` and `commit-msg` hooks.
  A hook that fixes a file stops the commit, so run `git add -A` and commit again.
- `gh pr create --fill` copies the message of a single commit into the pull request.
  With several commits, pass `--title` yourself.
- `gh pr merge --auto --squash` merges the pull request once the required checks pass.
  `gh pr checks --watch` shows them.

Pull requests merge by squash only, and the squash commit takes the pull request's title and description.
Since release-please reads that commit:

- The title follows [Conventional Commits](https://www.conventionalcommits.org/).
  The `title` check runs the `commit-msg` hook from `prek.toml` against it.
- A breaking change ends the description with a one-line `BREAKING CHANGE:` footer that links to its section of the upgrade page.
- To correct a merged entry, edit the merged pull request's description.
  Put the corrected message between `BEGIN_COMMIT_OVERRIDE` and `END_COMMIT_OVERRIDE`, and release-please uses it on its next run.

## Pull requests from bots

- Dependabot opens `chore: bump the uv group` and `ci: bump the actions group` on Mondays.
- `prek-update.yml` opens `chore: update prek hooks` on the first of each month.
- release-please opens `chore(main): release X.Y.Z`, and it updates that pull request after each merge that users would see.

Their types start no release, so merge the first two with `gh pr merge <number> --auto --squash` once they pass.
The release pull request waits until you want to release.

## What the rulesets block

- The `main` ruleset blocks every push to `main`, and a merge before `all-green` and `title` pass.
  The admin can still merge a failing pull request with **Merge without waiting for requirements to be met**, so keep that for emergencies.
- The `version tags` ruleset lets only the App and the admin create, update or delete a `v*` tag.

## Versions

Versions follow [SemVer](https://semver.org/).
Below 1.0, a new minor always means a breaking change.

| Commit | Changelog | Bump below 1.0 |
| --- | --- | --- |
| `feat`, `fix`, `perf`, `docs`, `deps`, `revert` | visible | patch |
| `refactor`, `test`, `build`, `ci`, `style`, `chore` | hidden | none on its own |
| any type with `!`, or a `BREAKING CHANGE:` footer | visible | minor |

`bump-minor-pre-major` and `bump-patch-for-minor-pre-major` in `release-please-config.json` set the last column.
No commit reaches 1.0 on its own.
Leaving `0.x` takes a `Release-As: 1.0.0` footer, and the policy for after 1.0 is set then.

## Breaking changes

The pull request that makes a break also writes its migration into [`user_guide/upgrading.qmd`](user_guide/upgrading.qmd), under the next minor's heading, such as `## 0.4`.
Every break before a release goes into the same next minor, so the heading is known when the pull request opens.
Below 1.0, a break needs no deprecation period.

## CI

`ci.yml` runs on each pull request and each push to `main`:

- `test` runs on Ubuntu, macOS and Windows, on every supported Python, against the built wheel.
- `next-python` runs the next CPython from its first beta, and it may fail.
- `lowest` runs the floor Python with each dependency at its floor.
- `lint` runs every prek hook on every file.
- `docs` builds the site.
  Epistole's examples send mail, so the build runs none of them.
- `all-green` passes when the jobs above pass.
  The `main` ruleset requires only this job and `title`, so a change to the jobs never touches the ruleset.

pytest turns warnings into errors, so a new upstream deprecation fails the Dependabot pull request that brings it in.

## Tests

Tests are in `tests/`, and `uv run pytest` runs them.
CI runs them against the built wheel, so `test_packaging.py` fails a change that drops `py.typed` from it.

Annotate every test parameter, including fixtures and `parametrize` values.
Ruff never enforces this, because `ruff.toml` turns off `ANN` under `**/tests/**`.
Pyrefly does enforce it, because `preset = "strict"` reports an unannotated parameter as `implicit-any-parameter`.
`pyrefly.toml` sets no exception for tests.
That difference is deliberate.
An annotated fixture lets pyrefly check the test body against the real type, so a misspelled field name fails `pyrefly check` before the tests run.

Skip the return-annotation part of `ANN`.
`-> None` on every test function adds no information.

## Dependencies

Each floor in `pyproject.toml` is as low as the `lowest` job proves.
A floor rises only in a `deps:` commit, which the changelog shows to users.
Dependabot moves `uv.lock` and the pinned actions weekly, after a 7-day cooldown.
Its `chore` and `ci` prefixes keep those pull requests out of the changelog.
Dependabot does not read `prek.toml`, so `prek-update.yml` updates the hooks monthly.

## Python versions

Epistole supports every CPython from 3.13 on that has not reached its end of life.
The standard starts at the oldest CPython still supported, and three facts, measured on 2026-09-29, hold Epistole at 3.13:

- `typing.override` needs 3.12, and 8 modules use it.
- `mimetypes.guess_file_type` needs 3.13.
- The address check needs the strict `email.utils.getaddresses` from the CVE-2023-27043 fix.
  3.11 gained it only in 3.11.10 and 3.12 only in 3.12.6, and `requires-python` cannot exclude the earlier patch releases without one `!=` for each.

The rest of the policy is the standard's:

- A version joins at its final release.
  Add its classifier in `pyproject.toml` and its entry in the `test` matrix, and point `next-python` at the version after it.
- A version leaves in the first release after its end of life, in a `feat!:` commit.
  Raise `requires-python`, `.python-version`, ruff's `target-version`, `default_language_version` in `prek.toml` and the Python of the `lowest` job.
  Then remove the version's classifier and its matrix entry.

## Releasing

1. release-please keeps a release pull request open with the next version, `CHANGELOG.md` and `uv.lock`.
2. Merging it makes the App create the tag and the GitHub release.
3. `release.yml` builds the distributions, and its `pypi` job waits for approval.
   On the run's page, click **Review deployments**, tick `pypi`, then click **Approve and deploy**.
   The job then uploads the distributions to PyPI with attestations.
4. `docs.yml` deploys the site.

A release published by hand starts the same two workflows, which makes it the recovery path.

## When something fails

- **A CI job fails.**
  `gh pr checks` names the job, and `gh run view <run-id> --log-failed` prints its log.
  Push a fix to the same branch, and auto-merge stays on.
- **The title check fails.**
  Fix the title with `gh pr edit --title`, and the check runs again.
- **A changelog entry is wrong after the merge.**
  Use `BEGIN_COMMIT_OVERRIDE`, as [Pull requests](#pull-requests) describes.
- **`release.yml` or `docs.yml` fails after the tag exists.**
  `gh run rerun <run-id> --failed` runs the failed jobs again.

## Traps

- Never pass `release-type` to `release-please-action`.
  The action then ignores `release-please-config.json`, and it prints no warning.
- The `uv.lock` JSONPath in `release-please-config.json` reads `@.name.value`, not `@.name`.
  release-please parses each TOML value into an object, and without `.value` it updates nothing.
- An edit to the release pull request's body is lost when `main` moves before the merge, and it never reaches `CHANGELOG.md`.
  Migration notes go in the upgrade page.
- `GITHUB_TOKEN` cannot run CI on a pull request it opens, and a release it creates starts no workflow.
  So release-please and `prek-update.yml` use the App's token.
- The `pypi` and `github-pages` environments accept `v*` tags only, and both release workflows run on the release's tag.
- A numpydoc `Returns` block starts with a `:` line.
  griffe, which great-docs uses, reads a bare description line as the return type.

## Prose

The package has two spellings in prose.
Each means one thing.

- **Epistole** is the name.
  Use it in running text: "Epistole sends the same message through any backend."
- **`epistole`** is the identifier, in code formatting.
  Use it for the distribution, the module, and the command: `uv add epistole`, `import epistole`.

Never write bare "epistole" in a sentence.
Never write any other variation, such as "EPISTOLE" or "epistole.py".

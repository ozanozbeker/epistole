# Contributing

This file holds the release standard for the maintainer's Python packages, and Epistole is its reference repo.
[ADR 0021](docs/adr/0021-epistole-holds-the-release-standard-for-every-package.md) records the decision, and [the CI/CD research note](docs/research/ci-cd-standard.md) holds the evidence.
A package that adopts the standard follows [Adopting the standard](#adopting-the-standard), and [Epistole's departures](#epistoles-departures) lists where Epistole itself differs.

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
- `prek-update.yml` opens `chore: update prek hooks and uv.lock` on the first of each month.
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
- `next-python` runs the newest CPython that has reached its first beta, and it may fail.
- `lowest` runs the floor Python with each dependency at its floor, and fails under 100% line coverage.
- `lint` runs every prek hook on every file except `gitleaks` and `check-added-large-files`, which read staged changes only.
  It then runs `gitleaks-ci` on each commit the pull request adds.
- `docs` builds the site.
  The build runs every example.
  An example with side effects, such as sending mail, runs in a test against a fake instead.
- `all-green` passes when the jobs above pass.
  The `main` ruleset requires only this job and `title`, so a change to the jobs never touches the ruleset.

pytest turns warnings into errors, so a new upstream deprecation fails the Dependabot pull request that brings it in.

## Tests

Tests are in `tests/`, and `uv run pytest` runs them.
CI runs them against the built wheel, not `src/`, so a test that reads a package file, such as `py.typed`, checks what the wheel holds.

`coverage report` fails under 100% line coverage.
A line that no test can reach takes `# pragma: no cover` and a one-line comment that says why.

Annotate every test parameter, including fixtures and `parametrize` values.
Ruff never enforces this, because `ruff.toml` turns off `ANN` under `**/tests/**`.
Pyrefly does enforce it, because `preset = "strict"` reports an unannotated parameter as `implicit-any-parameter`.
`pyrefly.toml` sets no exception for tests.
That difference is deliberate.
An annotated fixture lets pyrefly check the test body against the real type, so a misspelled field name fails `pyrefly check` before the tests run.

Skip the return-annotation part of `ANN`.
`-> None` on every test function adds no information.

## Dependencies

Each runtime floor in `pyproject.toml` is as low as the `lowest` job proves.
A runtime floor rises only in a `deps:` commit, which the changelog shows to users.
Set a `dev` floor to the newest release at least 7 days old.
Raise it by hand in a `chore:` commit with `uv add --dev "<name>>=<version>"`, because users never install the group.

Dependabot moves `uv.lock` and the pinned actions weekly, after a 7-day cooldown.
Its `chore` and `ci` prefixes keep those pull requests out of the changelog.
Dependabot does not read `prek.toml`, and its version updates move only the dependencies `pyproject.toml` declares.
So `prek-update.yml` updates the hooks and runs `uv lock --upgrade` monthly, with the same 7-day cooldown.

## Python versions

A package supports every CPython that has not reached its end of life.

- A version joins at its final release.
  Add its classifier in `pyproject.toml` and its entry in the `test` matrix.
  `next-python` stays on it until the next version reaches its first beta.
- A version leaves in the first release after its end of life, in a `feat!:` commit.
  Raise `requires-python`, `.python-version` and `default_language_version` in `prek.toml`.
  Then remove the version's classifier and its matrix entry.

## Releasing

1. release-please keeps a release pull request open with the next version, `CHANGELOG.md` and `uv.lock`.
2. Merging it makes the App create the tag and the GitHub release.
3. `release.yml` builds the distributions, and its `pypi` job waits for approval.
   Before approving, read `git log <previous tag>..<new tag>`.
   The `main` ruleset requires no review, so this approval is the last check a person makes.
   On the run's page, click **Review deployments**, tick `pypi`, then click **Approve and deploy**.
   The job then uploads the distributions to PyPI with attestations.
4. After the upload, `release.yml` builds the site and deploys it.

A release published by hand starts the same workflow, which makes it the recovery path.

## When something fails

- **A CI job fails.**
  `gh pr checks` names the job, and `gh run view <run-id> --log-failed` prints its log.
  Push a fix to the same branch, and auto-merge stays on.
- **The title check fails.**
  Fix the title with `gh pr edit --title`, and the check runs again.
- **A changelog entry is wrong after the merge.**
  Use `BEGIN_COMMIT_OVERRIDE`, as [Pull requests](#pull-requests) describes.
- **`release.yml` fails after the tag exists.**
  `gh run rerun <run-id> --failed` runs the failed jobs again.
  The `pypi` job sets `skip-existing`, so a rerun after a partial upload skips the files PyPI already has.
- **`build` fails the ancestor check.**
  The tag points at a commit that `main` does not contain, so nothing was published.

## Traps

- Never pass `release-type` to `release-please-action`.
  The action then ignores `release-please-config.json`, and it prints no warning.
- The `uv.lock` JSONPath in `release-please-config.json` reads `@.name.value`, not `@.name`.
  release-please parses each TOML value into an object, and without `.value` it updates nothing.
- An edit to the release pull request's body is lost when `main` moves before the merge, and it never reaches `CHANGELOG.md`.
  Migration notes go in the upgrade page.
- `GITHUB_TOKEN` cannot run CI on a pull request it opens, and a release it creates starts no workflow.
  So release-please and `prek-update.yml` use the App's token.
- The `pypi` and `github-pages` environments accept `v*` tags only, and `release.yml` runs on the release's tag.
- Turn on auto-merge with `gh pr merge --auto --squash`, not the web form.
  The web form appears to save the squash title it shows (untested), so a later title fix may never reach the commit.
- A numpydoc `Returns` block starts with a `:` line.
  griffe, which great-docs uses, reads a bare description line as the return type.

## Adopting the standard

1. Copy these from Epistole and replace `epistole` in each:
   - `.github/dependabot.yml` and `.github/workflows/{ci,pr-title,release-please,release,prek-update}.yml`;
   - `release-please-config.json`, `prek.toml`, `ruff.toml`, `rumdl.toml`, `tombi.toml`, `pyrefly.toml` and `user_guide/upgrading.qmd`;
   - from `great-docs.yml`, the `parser`, `dynamic`, `authors` and `seo` keys and the `upgrading.qmd` entry;
   - from `pyproject.toml`, the `[build-system]`, `[tool.pytest.ini_options]` and `[tool.coverage.*]` tables, the `docs` group, and the `dev` group's tools: `coverage`, `prek`, `pyrefly`, `pytest`, `ruff`, `rumdl` and `tombi`;
   - from `.gitignore`, the `great-docs/`, `_great_docs_build/` and `_freeze/` lines.
2. Write the package's own parts:
   - its floor CPython in `.python-version`, `default_language_version` in `prek.toml`, the `test` matrix and `requires-python`;
   - a self-reference in the `dev` group that installs every extra, and a `src/<package>/py.typed`;
   - the rest of `great-docs.yml`, and the comments in `ci.yml` and `release.yml` that name Epistole's examples and tests.
3. Write `.release-please-manifest.json` as `{".": "<last released version>"}`, or `{".": "0.0.0"}` in a repo with no release.
   That repo also sets `bootstrap-sha` to the commit before the one that adds release-please, and its first pull request ends with a `Release-As: 0.0.1` footer.
4. In the package's `CONTRIBUTING.md`, write `Copied from Epistole at <sha>` and a table of where the package departs.
   In its `CLAUDE.md`, import `@~/Dev/epistole/CONTRIBUTING.md`, then `@CONTRIBUTING.md`.
5. Apply [Repository settings](#repository-settings).

A package follows the standard in full or in maintenance:

| Package | Follows |
| --- | --- |
| dagster-dataframely | maintenance |

A change to a standard file merges in Epistole first, then as a pull request with the same title in each package that follows in full.
To catch up, run `git -C ~/Dev/epistole diff <sha> HEAD -- .github release-please-config.json prek.toml ruff.toml rumdl.toml tombi.toml pyrefly.toml great-docs.yml user_guide/upgrading.qmd pyproject.toml CONTRIBUTING.md`, port the diff, and update the SHA.
A package in maintenance keeps Dependabot's `uv` entry and applies steps 3, 4 and 6 to 9 of Repository settings, with rulesets that require the checks its pull requests report.
It owes no catch-up pull request.

## Repository settings

Appendix C of [the CI/CD research note](docs/research/ci-cd-standard.md) holds each command in full, with `R=ozanozbeker/<repo>`.

1. Install the release App, `ozanozbeker-release` (Integration 5110076), on the repo.
   It holds Contents, Issues and Pull requests read and write, and Metadata read.
   Generate a private key for the new repo on the App's page, and keep no `.pem` on disk.
2. Create the `release` environment: branch policy `main`, variable `APP_CLIENT_ID`, secret `APP_PRIVATE_KEY`.
3. Create the `pypi` environment: tag policy `v*`, the maintainer as required reviewer, self-review allowed, admin bypass off.
   Self-review stays allowed, because a release published by hand makes the maintainer its initiator.
4. On pypi.org, add the trusted publisher: owner `ozanozbeker`, the repo, workflow `release.yml`, environment `pypi`.
5. Set Pages to deploy from GitHub Actions, limit the `github-pages` environment to tags `v*`, and run `gh api -X PUT repos/$R/pages -F https_enforced=true`.
6. Allow squash merges only, titled and described from the pull request, with auto-merge on and head branches deleted.
7. Require actions pinned to a full SHA, keep the default token read-only, and stop GitHub Actions approving pull requests.
8. Turn on Dependabot alerts and security updates, private vulnerability reporting, and CodeQL default setup for `actions` and `python`.
   Check that secret scanning and push protection read `enabled` under `security_and_analysis` in `gh api repos/$R`.
9. After `all-green` and `title` have run on a pull request, copy Epistole's `main` and `version tags` rulesets to the new repo.
10. In a repo with no release, release once: the `Release-As: 0.0.1` pull request from Adopting the standard, then the release pull request, then approve `pypi`.
    Check that PyPI shows one attestation per file and that the site serves HTTPS.

## Epistole's departures

### Python 3.13 floor

The standard starts at the oldest CPython still supported, and three facts hold Epistole at 3.13:

- `typing.override` needs 3.12, and 10 modules use it (2026-10-15).
- `mimetypes.guess_file_type` needs 3.13.
- The address check needs the strict `email.utils.getaddresses` from the CVE-2023-27043 fix.
  3.11 gained it only in 3.11.10 and 3.12 only in 3.12.6, and `requires-python` cannot exclude the earlier patch releases without one `!=` for each.

### Examples

Epistole's examples send mail, so the docs build runs none of them.
`tests/test_examples.py` runs each one against `MemoryBackend` instead.

### Prose

The package has two spellings in prose.
Each means one thing.

- **Epistole** is the name.
  Use it in running text: "Epistole sends the same message through any backend."
- **`epistole`** is the identifier, in code formatting.
  Use it for the distribution, the module, and the command: `uv add epistole`, `import epistole`.

Never write bare "epistole" in a sentence.
Never write any other variation, such as "EPISTOLE" or "epistole.py".

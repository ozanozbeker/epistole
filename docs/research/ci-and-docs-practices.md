# How six Python libraries run CI, protect their default branch and publish docs

This note records how six large Python libraries check pull requests, protect their default branch and publish their docs.
It also compares four docs tools for a typed library with a CLI.
It answers [#28](https://github.com/ozanozbeker/oxyscraper/issues/28) for [#22](https://github.com/ozanozbeker/oxyscraper/issues/22).
It covers the commits in the table below, read on 2026-09-25.
Repository settings come from GitHub's REST and GraphQL APIs without admin access, and the note marks each setting those APIs hide.

| Library | Repository | Default branch | Commit read |
| --- | --- | --- | --- |
| FastAPI | `fastapi/fastapi` | `master` | [`50113da`][fa-tree], 2026-09-01 |
| Pydantic | `pydantic/pydantic` | `main` | [`a9a0e1d`][pd-tree], 2026-09-25 |
| pytest | `pytest-dev/pytest` | `main` | [`8721173`][pt-tree], 2026-09-24 |
| attrs | `python-attrs/attrs` | `main` | [`8f76777`][at-tree], 2026-09-01 |
| urllib3 | `urllib3/urllib3` | `main` | [`ed0ed07`][u3-tree], 2026-09-25 |
| Polars | `pola-rs/polars` | `main` | [`efba0b7`][pl-tree], 2026-09-25 |

## Answer

- **Required checks.**
  Five libraries require status checks on the default branch, and Polars requires none.
  FastAPI, Pydantic, pytest and attrs require one `re-actors/alls-green` job per workflow instead of each test job, so a change to the test matrix leaves the required list unchanged.
  Classic protection in urllib3 lists 30 job names instead.
  GitHub keeps a required check Pending when a path filter skips its whole workflow, and it counts a job skipped by an `if:` condition as a success.
  FastAPI therefore filters paths with a job inside its test and docs workflows, not with the workflow trigger.
- **Rules on the default branch.**
  FastAPI, Pydantic and pytest use a ruleset, and attrs, urllib3 and Polars use classic branch protection.
  Each ruleset requires a pull request and blocks force pushes and deletion.
  FastAPI and Pydantic require no approving review, and pytest requires one.
  No ruleset requires a branch to be up to date before merging.
  The API returns `bypass_actors: null` to a non-admin, so no bypass list is readable.
  Direct pushes still happen: the Latest Changes app pushed 15 of FastAPI's last 30 commits, and attrs' maintainer pushed 21 of its last 30.
- **Merge methods.**
  FastAPI, Pydantic, attrs and Polars allow only squash merges, and all four title the squash commit with the pull request title.
  Of the other two, pytest allows merge and squash, and urllib3 allows squash and rebase.
  FastAPI and Pydantic also restrict their ruleset to squash and require linear history.
- **Pull request titles.**
  Only Polars checks titles, against a Conventional Commits pattern, and no rule requires that check.
  FastAPI requires one release-notes label on each pull request, through the Latest Changes app.
  Both pytest and urllib3 require a towncrier changelog fragment.
- **Matrix.**
  FastAPI, Pydantic, pytest and urllib3 test Linux, macOS and Windows on pull requests, in 15 to 30 test jobs.
  The attrs suite runs on Ubuntu only, with one job per Python version listed in its trove classifiers.
  Polars tests Ubuntu and Windows in 9 jobs, and only for pull requests that touch its code.
  Only Pydantic tests more for a release: it tests its wheels on ARM and emulated architectures on `main` and on tags.
- **Lint.**
  Only pytest runs its hooks on pre-commit.ci, and it requires that status.
  FastAPI and attrs run prek in Actions, Pydantic and urllib3 run pre-commit in Actions, and Polars calls each tool directly.
  The pre-commit.ci service reads only `.pre-commit-config.yaml`, and its free tier allows no network access while hooks run.
- **Scheduled runs.**
  Pydantic tests the earliest and latest release of each dependency twice a week, and 18 downstream projects daily.
  FastAPI reruns its tests weekly.
  On every pull request, pytest, Pydantic, FastAPI and urllib3 also test against a dependency's git `main` or a downstream suite.
  Neither attrs nor Polars schedules a test run.
- **Dependency updates.**
  All six use Dependabot, and none uses Renovate.
  Five set a 7-day `cooldown`, and Dependabot applies 3 days when `cooldown` is unset.
  Only FastAPI and Polars set a commit prefix, and the prefix also sets the pull request title.
  Dependabot's `pre-commit` ecosystem updates `.pre-commit-config.yaml` only, and FastAPI updates its hooks with a monthly `prek auto-update --freeze --cooldown-days 7` workflow instead.
- **Workflow security.**
  Five libraries pin all 380 of their action references to a full commit SHA, and Polars pins none of its 108.
  The same five set `permissions` in every workflow and `persist-credentials` on every checkout, and Polars sets `permissions` in 4 of 19 workflows.
  Five run zizmor, as an action, a hook or both.
  For CodeQL, urllib3 runs it on every pull request and requires it, FastAPI uses default setup, and attrs runs it weekly.
- **Docs sites.**
  The pytest, attrs and urllib3 docs use Sphinx with the Furo theme on Read the Docs, which builds a preview for each pull request and a version for each tag.
  FastAPI builds with Zensical and Pydantic with MkDocs Material, and both deploy to Cloudflare Pages with a preview for each pull request.
  Polars alone uses GitHub Pages, with Sphinx for the API reference and MkDocs Material for the user guide.
  GitHub Pages offers no public pull request previews.
- **Docs tools.**
  Material for MkDocs gets only critical fixes and security updates until May 5, 2027, and its team now builds Zensical.
  Zensical 0.0.65 is an alpha that reads `mkdocs.yml`, runs 19 rewritten plugins including mkdocstrings and markdown-exec, and ignores all others.
  The latest MkDocs 2.0 pre-release loads no plugins, and a former maintainer forks 1.x as ProperDocs.
  The great-docs 0.17.0 release builds on Quarto, with a Click reference, a changelog from GitHub Releases and versioned sites built in.
  Sphinx has an extension for each of Click, Typer, cyclopts and argparse.
  In griffe and in Sphinx's napoleon, a numpydoc `Returns` block that holds only a description becomes the return type.
- **A public repository on a personal account.**
  Rulesets, code scanning and GitHub Pages all work on a public repository on GitHub Free.
  Merge queues need a repository owned by an organization.
  A pull request's author cannot approve it, so a required approval blocks a sole maintainer unless a bypass applies.

## Pull request CI

### Triggers and path filters

Every library starts its test workflow on `pull_request` and on pushes to the default branch.
The urllib3 workflow also starts on pushes to every branch except Dependabot's ([`ci.yml`][u3-ci]).
The pytest workflow also starts on release tags and maintenance branches ([`test.yml`][pt-test-trigger]).
Polars runs its test job on pushes to `main` and `1.x`, but every test step requires a `pull_request` event, so a push only builds Polars and saves the Rust cache ([`test-python.yml`][pl-test-python-steps]).

Only FastAPI and Polars filter by path.
Polars sets `paths` on each workflow's trigger, and it requires no checks ([`test-python.yml`][pl-test-python]).
FastAPI's test and docs workflows start on every pull request.
A first job runs `dorny/paths-filter` and sets an output, and the test and docs jobs read it in their `if:` conditions ([`test.yml`][fa-test-filter]).
A last job runs `re-actors/alls-green` with `allowed-skips`, so it reports success when a filter skipped the jobs before it ([`test.yml`][fa-test-green], [`build-docs.yml`][fa-build-docs-green]).

GitHub's troubleshooting page gives the reason in a table ([troubleshooting required status checks][gh-checks-troubleshoot]):

- A workflow skipped by a path filter, a branch filter or a commit message leaves its checks Pending, and a pull request that requires them cannot merge.
- A job skipped by a conditional reports Success.
- A job that needs a failed job is skipped, so a required aggregate job needs `if: always()`.

The `alls-green` action covers that last case.
Its README says a plain aggregate job reports `skipped`, not `failed`, when a job it needs fails ([README][alls-green]).

pytest, attrs and Polars cancel superseded runs with `concurrency` and `cancel-in-progress: true`.
FastAPI, Pydantic and urllib3 do not set it on their test workflows.

### Python and OS matrix

The job counts come from the check runs on one merged pull request per library.

| Library | Test jobs on a pull request | Operating systems | Python versions | Other legs |
| --- | --- | --- | --- | --- |
| FastAPI | 15 ([#16289][fa-pr]) | Ubuntu, macOS, Windows | 3.10, 3.12, 3.13, 3.14, 3.14t | lowest direct versions on 3.10 and 3.12, Starlette from git, no httpx2 ([`test.yml`][fa-test-matrix]) |
| Pydantic | 26 ([#13866][pd-pr]) | Ubuntu, macOS, Windows, macOS on Intel | 3.10 to 3.15, 3.15t, PyPy 3.11 | 6 more jobs against typing-extensions from git, Pyodide ([`ci.yml`][pd-ci-test]) |
| pytest | 30 ([#15096][pt-pr]) | Ubuntu, macOS, Windows | 3.10 to 3.15, PyPy 3.11 | pluggy from git, Twisted, asynctest, doctests, plugins ([`test.yml`][pt-test-matrix]) |
| attrs | 7 ([#1617][at-pr]) | Ubuntu | 3.10 to 3.15, PyPy 3.11 | mypy on each version ([`ci.yml`][at-ci-matrix]) |
| urllib3 | 29 ([#5276][u3-pr]) | Ubuntu, macOS, Windows | 3.10 to 3.15, 3.14t, 3.12.2, PyPy 3.11 | Emscripten in Node, Firefox and Chrome, minimum pyOpenSSL, integration ([`ci.yml`][u3-ci-matrix]) |
| Polars | 9 ([#29539][pl-pr]) | Ubuntu, Windows | 3.10, 3.12, 3.13, 3.14, 3.14t | engine and morsel-size variants ([`test-python.yml`][pl-test-python]) |

attrs reads its Python versions from its own package.
The action `hynek/build-and-inspect-python-package` returns the trove classifiers as a JSON array, and the test matrix uses that array ([`ci.yml`][at-ci-matrix]).
The attrs tests run against the built wheel, and the pytest tests against the built sdist ([attrs][at-ci-matrix], [pytest][pt-test-matrix]).

Only Pydantic tests more for a release than for a pull request.
On `main`, on tags, or for a pull request labelled `full build`, it builds its Rust extension's wheels for every platform ([`ci.yml`][pd-ci-core-build]).
It then tests those wheels on Linux and Windows ARM runners and on emulated armv7, s390x, ppc64le and aarch64 ([`ci.yml`][pd-ci-builds-test]).
Its release jobs run in the tag's CI run and need the aggregate `check` job ([`ci.yml`][pd-ci-release]).
The release workflows of the other five build and publish, and none of them runs the test suite ([FastAPI][fa-publish], [pytest][pt-deploy], [attrs][at-pypi], [urllib3][u3-publish], [Polars][pl-release]).
Issue [#27](https://github.com/ozanozbeker/oxyscraper/issues/27) covers the release workflows.

### Lint

| Library | Runner | Where it runs | Type checkers |
| --- | --- | --- | --- |
| FastAPI | prek | `pre-commit.yml`, required through `pre-commit-alls-green` | mypy and ty, as hooks |
| Pydantic | pre-commit, through `pre-commit/action` | `lint` job on six Python versions, inside `check` | pyright, as a hook |
| pytest | pre-commit.ci | the `pre-commit.ci - pr` status, required | mypy and pyright, as hooks |
| attrs | prek, through tox | `lint` job, inside the required aggregate job | mypy on each version, then pyright, ty and pyrefly |
| urllib3 | pre-commit, through nox | `lint` job, required | mypy |
| Polars | none; `ruff-action`, `dprint/check` and `crate-ci/typos` | `lint-python.yml` and `lint-global.yml`, not required | mypy and pyrefly |

- FastAPI runs `uv run prek run --from-ref origin/${GITHUB_BASE_REF} --to-ref HEAD` after `uv sync --locked`.
  For a pull request from the same repository it commits the fixes and pushes them with a token from `tiangolo/pr-push`.
  For a fork it calls `pre-commit-ci/lite-action` instead ([`pre-commit.yml`][fa-pre-commit]).
- attrs runs `prek run --all-files` and ruff from tox environments ([`tox.ini`][at-tox]).
  Its hook config still has a `ci:` block for pre-commit.ci ([`.pre-commit-config.yaml`][at-hooks]).
  Its last pre-commit.ci pull request opened on 2026-07-06, and none of its last eight merged pull requests has a pre-commit.ci status ([pull requests][at-precommitci-prs]).
  FastAPI's last pre-commit.ci pull request opened on 2025-11-10 ([pull requests][fa-precommitci-prs]).
- urllib3's `nox -s lint` runs `pre-commit run --all-files` and then mypy ([`noxfile.py`][u3-nox-lint]).
- Polars runs `pyrefly check` and `pyrefly coverage check --public-only src` on Python 3.10 and 3.14 ([`lint-python.yml`][pl-lint-python]).

pre-commit.ci has three limits that matter for oxy's hooks:

- It reads its settings and the hooks from `.pre-commit-config.yaml` ([pre-commit.ci][precommit-ci]).
  The prek docs state that upstream pre-commit does not read `prek.toml` ([compatibility][prek-compat]).
- Its maintainer wrote in 2020 that the free tier allows no network access at runtime and no arbitrary installation, on an issue that is still open ([issue 13][precommit-ci-13]).
  The local hooks in oxy's `prek.toml` run their tools through `uv run`.
- By default it pushes fix commits to pull requests and opens an autoupdate pull request weekly ([pre-commit.ci][precommit-ci]).

The prek docs describe `j178/prek-action`, which installs prek and runs `prek run --all-files` ([CI docs][prek-ci]).

### Scheduled runs and newest dependencies

- **Pydantic.**
  The `dependencies-check.yml` workflow runs on Wednesdays and Saturdays, and tests the earliest and latest release of each dependency on Python 3.10 to 3.13 ([workflow][pd-deps-check], [`list-python-dependencies`][list-deps]).
  The `third-party.yml` workflow runs the test suites of 18 downstream projects daily, and on a pull request only when it has the `third-party-tests` label ([workflow][pd-third-party]).
  The `integration.yml` workflow tests pydantic-settings and pydantic-extra-types on weekdays ([workflow][pd-integration]).
  Every pull request also runs the tests against typing-extensions from its git `main` ([`ci.yml`][pd-ci-te]).
- **FastAPI.**
  The test workflow also runs every Monday at 00:00 UTC ([`test.yml`][fa-test-trigger]).
  Five legs replace Starlette with its git `main`, and two install the lowest direct versions of the dependencies ([`test.yml`][fa-test-matrix]).
- **pytest.**
  Every pull request runs two legs against pluggy's git `main`, and they may fail without failing the run ([`test.yml`][pt-test-matrix], [`tox.ini`][pt-tox]).
  Its scheduled workflows check links, update the plugin list and close stale issues, and none runs the tests.
- **urllib3.**
  Every pull request runs the test suites of requests and botocore against the change ([`downstream.yml`][u3-downstream]).
  Its scheduled workflows run CodeQL and OpenSSF Scorecard, and no tests.
- **attrs and Polars** schedule no test runs.
  The only scheduled workflow in attrs runs CodeQL.

## Protecting the default branch

### Rules on each library

| Library | Mechanism | Required checks | Approvals | Linear history | Merge methods | Squash commit title | Auto-merge |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FastAPI | ruleset | four `*-alls-green` jobs and `latest-changes/label` | 0 | required | squash | pull request title | allowed |
| Pydantic | ruleset | `check` | 0 | required | squash | pull request title | allowed |
| pytest | ruleset | `check`, `docs/readthedocs.org:pytest`, `Changelog entry`, `pre-commit.ci - pr` | 1 | not required | merge, squash | commit or pull request title | allowed |
| attrs | branch protection | `Ensure everything required is passing for branch protection` | hidden | hidden | squash | pull request title | allowed |
| urllib3 | branch protection | 30 job names | hidden | hidden | squash, rebase | commit or pull request title | allowed |
| Polars | branch protection | none | hidden | hidden | squash | pull request title | not allowed |

Sources: the rules endpoint for [FastAPI][fa-rules], [Pydantic][pd-rules] and [pytest][pt-rules]; the branch endpoint for [attrs][at-branch], [urllib3][u3-branch] and [Polars][pl-branch]; and GraphQL for merge methods, squash titles and auto-merge.

- Each ruleset also blocks force pushes and deletion.
  The pytest ruleset also covers the `N.N.x` maintenance branches ([ruleset][pt-rulesets]).
- Each required check in a ruleset names its source app, except Read the Docs.
  The sources are GitHub Actions, the Latest Changes app, the `psf-chronographer` app and pre-commit.ci.
- No ruleset requires a branch to be up to date before merging.
  The pytest ruleset sets "Do not require status checks on creation".
- urllib3's 30 names cover each operating system with Python 3.10 to 3.15, plus the package, lint, coverage, changelog, downstream, CodeQL and Read the Docs checks.
  Its 3.14t, PyPy, minimum pyOpenSSL and Emscripten jobs run but are not on the list ([branch][u3-branch]).
- attrs has a merge queue on `main`: GraphQL returns a `mergeQueue` object whose configuration is hidden.
  Its CI workflow runs on `merge_group` ([`ci.yml`][at-ci]).
- pytest and urllib3 also protect release tags with tag rulesets.
- pytest's contributing guide says no one merges their own pull request unless it is already approved ([guide][pt-contributing]).
  The attrs guide says nobody merges their own code ([guide][at-contributing]).
  The pytest guide also says when to merge and when to squash, and asks for squash on backports ([guide][pt-contributing]).

### What a non-admin can read

- `GET /repos/{owner}/{repo}/rules/branches/{branch}` returns every active rule, with the required checks and allowed merge methods.
  GitHub states that anyone with read access can view active rulesets ([about rulesets][gh-rules-about]).
- `GET /repos/{owner}/{repo}/rulesets/{id}` returns `bypass_actors: null` and `current_user_can_bypass: never`.
- For classic protection, `GET /repos/{owner}/{repo}/branches/{branch}` returns the required check names, and `.../protection` returns 404.
  Reviews, admin enforcement and linear history stay hidden.
- `GET /repos/{owner}/{repo}` omits the merge settings for a user without push access.
  The GraphQL `Repository` object returns them: `squashMergeAllowed`, `squashMergeCommitTitle`, `autoMergeAllowed`, `mergeQueue` and the rest ([GraphQL reference][gh-graphql-repo]).
- `GET /repos/{owner}/{repo}/environments` lists each environment's required reviewers and branch policies.
  The endpoints `.../code-scanning/default-setup` and `.../actions/permissions/workflow` return 403 to a non-admin.

Commit history shows direct pushes that the hidden settings allow:

- The Latest Changes app pushed 15 of FastAPI's last 30 commits on `master`, all after the ruleset's creation on 2026-08-06, with no pull request ([commits][fa-commits]).
  The app's description says to add it to the bypass list with "Always allow" when a ruleset blocks direct writes ([app][latest-changes]).
- attrs' maintainer pushed 21 of its last 30 commits on `main` directly, between 2026-08-01 and 2026-08-25 ([commits][at-commits]).
- pytest and Polars show no direct pushes in their last 30 commits.
  The urllib3 history shows two "Merge commit from fork" commits, and the Pydantic history one commit without a pull request.

### GitHub behaviour that shapes the choice

- Rulesets are available in public repositories on GitHub Free, including a personal account's ([about rulesets][gh-rules-about]).
  Rulesets and branch protection apply together, and the most restrictive version of each rule applies.
- The bypass list accepts the repository admin role, the maintain and write roles, teams, GitHub Apps and Dependabot ([creating rulesets][gh-rules-creating]).
  Each entry is "Always allow" or "For pull requests only".
  "For pull requests only" requires the actor to open a pull request, and then lets them bypass the rules when they merge it.
- "Require a pull request before merging" applies to every change, even with zero required approvals ([available rules][gh-rules-available]).
- Pull request authors cannot approve their own pull requests ([approving][gh-approve]).
- A ruleset can limit the allowed merge methods, and GitHub blocks a merge when the repository has disabled the method the ruleset requires ([available rules][gh-rules-available]).
- A required check can name the app that must report it, and a status from any other source then blocks the merge ([available rules][gh-rules-available]).
- With "Require branches to be up to date before merging" off, a check can fail after the merge if the base branch changed ([available rules][gh-rules-available]).
- Merge queues are available in public repositories owned by an organization, and each required workflow needs the `merge_group` trigger ([merge queue][gh-merge-queue]).
- By default, the squash commit takes the commit's title for a one-commit pull request and the pull request title otherwise.
  A repository setting makes it always use the pull request title ([commit squashing][gh-squash]).

## Pull request titles and changelog checks

- **Polars** runs `thehanimo/pr-title-checker@v1.4.2` from a `pull_request_target` workflow when a pull request opens or its title changes ([`pr-labeler.yml`][pl-pr-labeler]).
  The pattern requires a Conventional Commits type, an optional `python` or `rust` scope, an optional `!`, and a capitalised description without end punctuation ([config][pl-title-config]):

  ```text
  ^(build|chore|ci|depr|docs|feat|fix|perf|refactor|release|test)(\((python|rust)\!?(,(python|rust)\!?)?\))?\!?\: [A-Z].*[^\.\!\?,… ]$
  ```

  A failing title gets the label `title needs formatting`, and the label `skip changelog` exempts a pull request.
  The `release-drafter` action labels each pull request from its title and drafts the release notes ([`release-drafter.yml`][pl-release-drafter]).
  The contributing guide asks for the Angular convention's types ([contributing][pl-contributing]).
- **FastAPI** requires the `latest-changes/label` status from the Latest Changes app ([app][latest-changes]).
  The status succeeds only when a pull request has exactly one label from `breaking`, `security`, `feature`, `bug`, `refactor`, `upgrade`, `docs`, `lang-all`, `infra`, `internal` and `release`.
  The app adds the label itself when `.github/latest-changes.yml` maps every changed path to one ([config][fa-latest-changes]).
  On merge it writes the pull request into the release notes and pushes that commit to `master`.
- **pytest** requires the `Changelog entry` check from the `psf-chronographer` app, which looks for a towncrier fragment and accepts the `skip news` label ([`chronographer.yml`][pt-chronographer]).
- **urllib3** requires `changelog entry`, a job that runs `towncrier check` unless the pull request has the `Skip Changelog` label ([`changelog.yml`][u3-changelog]).
  Its Dependabot config adds that label to every update ([`dependabot.yml`][u3-dependabot]).
- **Pydantic** checks nothing.
  Its pull request template says the title goes into the changelog ([template][pd-pr-template]), and GitHub's generated release notes sort pull requests by label ([`release.yml`][pd-release-yml]).
- **attrs** checks nothing, and CI renders the draft changelog from towncrier fragments ([`ci.yml`][at-ci]).

## Dependency updates

| Library | Ecosystems | Interval | Cooldown | Groups | Commit prefix | Hook updates |
| --- | --- | --- | --- | --- | --- | --- |
| FastAPI | `github-actions`, `uv` | monthly | 7 days | all actions; all development dependencies | `⬆` | monthly `prek auto-update` workflow |
| Pydantic | `github-actions`, `cargo` | monthly | 7 days | Rust crates except pyo3 and strum | none | none found |
| pytest | `github-actions`, `pip` for plugin tests | weekly | 7 days | none | none | pre-commit.ci, weekly |
| attrs | `github-actions` | monthly | 7 days | all actions | none | pre-commit.ci, monthly; last pull request on 2026-07-06 |
| urllib3 | `github-actions`, `pre-commit` | monthly, and quarterly for hooks | 7 days | all actions; all hooks | none | Dependabot |
| Polars | `github-actions`, `cargo`, `pip` twice | monthly | not set | one group per ecosystem | `ci`, `build`, `chore(rust)`, `chore(python)` | no hooks |

Sources: [FastAPI][fa-dependabot], [Pydantic][pd-dependabot], [pytest][pt-dependabot], [attrs][at-dependabot], [urllib3][u3-dependabot] and [Polars][pl-dependabot].

- Polars ignores patch releases in every ecosystem, and labels every update `skip changelog`.
- FastAPI's hook workflow runs `uv run prek auto-update --freeze --cooldown-days 7`, then opens a pull request with a token from `tiangolo/pr-submit` ([workflow][fa-bump-hooks]).
  The prek changelog records that 0.4.8 renamed `auto-update` to `update`, and 0.5.0 removed `auto-update` and kept `autoupdate` as an alias ([changelog][prek-changelog]).
  FastAPI's lockfile pins prek 0.4.14, where the old name still works.
  The CLI reference documents `--freeze` and `--cooldown-days` for `prek update` ([CLI reference][prek-cli]).
- FastAPI, urllib3 and oxy pin hooks as `rev: <sha>  # frozen: <tag>` ([FastAPI][fa-hooks], [urllib3][u3-hooks]).

GitHub's Dependabot reference states ([options][gh-dependabot-options], [ecosystems][gh-dependabot-ecosystems]):

- Dependabot applies a 3-day cooldown to version updates when `cooldown` is unset, and no cooldown to security updates.
- `commit-message.prefix` sets the prefix of the commit message and of the pull request title.
  Dependabot adds a colon after a prefix that ends in a letter, a digit, `)` or `]`.
  The `prefix-development` option sets a separate prefix for development dependencies, for `pip` and `uv` among others.
- The `uv` ecosystem supports uv 0.11.
- The `pre-commit` ecosystem updates hook revisions in `.pre-commit-config.yaml` files.
  It resolves a `# frozen:` comment to the newest matching tag, and it updates `additional_dependencies`.
  The docs mention no other config file.
- The `github-actions` ecosystem updates SHA-pinned actions and the version comment on the same line.

## Workflow security

| Library | Actions pinned to a full SHA | Top-level `permissions` | `persist-credentials` set | zizmor | CodeQL |
| --- | --- | --- | --- | --- | --- |
| FastAPI | 95 of 95 | `{}` in 19 of 20 workflows | 25 of 25 checkouts | action on pull requests and `master`, and a hook | default setup |
| Pydantic | 179 of 179 | set in 9 of 10, and in every job of the tenth | 71 of 71 | hook, in `lint` | none |
| pytest | 24 of 24 | `{}` in 5 of 6, and in every job of the sixth | 8 of 8 | hook with `--fix`, on pre-commit.ci | none |
| attrs | 47 of 47 | `{}` in 6 of 6 | 10 of 10 | action with `persona: pedantic` | weekly, Python |
| urllib3 | 35 of 35 | `contents: read` in 7 of 7 | 9 of 9 | hook, in `lint` | every pull request, required |
| Polars | 0 of 108 | set in 4 of 19 | 0 of 30 | none | none |

The counts cover every `uses:` line and every `actions/checkout` step under `.github/`, with local actions left out.
The value of `persist-credentials` is `false` everywhere except in the jobs that push a commit.
"None" for CodeQL means no CodeQL workflow and no default-setup workflow in the Actions API.

- FastAPI's CodeQL default setup appears as the dynamic workflow `dynamic/github-code-scanning/codeql`, and its check runs cover Python, JavaScript and TypeScript, and Actions ([workflows][fa-workflows-api]).
- urllib3 runs CodeQL on pushes to `main`, on pull requests and weekly, for Python, JavaScript and TypeScript, and Actions ([`codeql.yml`][u3-codeql]).
  It also runs OpenSSF Scorecard weekly ([`scorecards.yml`][u3-scorecard]).
- attrs runs zizmor only through `zizmor-action`, in the Advanced Security mode ([`zizmor.yml`][at-zizmor]).
  In that mode the action uploads findings to code scanning and does not fail the job, so blocking a merge needs a code scanning rule in a ruleset ([README][zizmor-action]).
  FastAPI runs the same action, and its prek hook also runs zizmor inside the required lint job ([`.pre-commit-config.yaml`][fa-hooks]).
- Pydantic's `.github/zizmor.yml` turns off the `secrets-outside-env` and `superfluous-actions` audits ([config][pd-zizmor]).
- Polars pins by tag or branch, including `pierotofy/set-swap-space@master` and `pypa/gh-action-pypi-publish@release/v1`.

GitHub's security reference states ([secure use][gh-secure-use], [Actions settings][gh-actions-settings]):

- Pinning to a full commit SHA is the only way to use an action as an immutable release.
- A repository setting can require every action to be pinned to a full SHA.
- Dependabot creates no alerts for actions pinned to a SHA, only for actions pinned to a semantic version.
- The restricted setting gives `GITHUB_TOKEN` read access to `contents` and `packages` only.
- CodeQL analyses GitHub Actions workflows ([CodeQL][gh-codeql]).
  Default setup scans pushes to the default branch, pull requests against it except from forks, and a weekly schedule ([setup types][gh-codeql-setup]).
  Code scanning is available for every public repository ([CodeQL][gh-codeql]).

## Docs sites

| Library | Tool | Host | Deploys on | Pull request build | Versions |
| --- | --- | --- | --- | --- | --- |
| FastAPI | Zensical 0.0.57, reading `mkdocs.yml`, with mkdocstrings | Cloudflare Pages | push to `master` | preview deploy, URL posted as a comment | none |
| Pydantic | MkDocs with Material Insiders and mkdocstrings | Cloudflare Pages | push to `main`, and tags | Cloudflare Pages preview, plus `mkdocs build` in CI | `mike`, 16 versions |
| pytest | Sphinx 9 or later with Furo | Read the Docs | Read the Docs builds | Read the Docs preview, required | Read the Docs |
| attrs | Sphinx with Furo and MyST | Read the Docs | Read the Docs builds | Read the Docs preview; doctests in CI | Read the Docs |
| urllib3 | Sphinx with Furo and MyST | Read the Docs | Read the Docs builds | Read the Docs preview, required | Read the Docs |
| Polars | Sphinx 8.1.3 with numpydoc for the API; MkDocs Material 9.6.20 for the user guide | GitHub Pages | API: push to `main` and releases; user guide: releases | build only, when docs paths change | one folder per major version |

- **FastAPI** builds each language with `zensical build --config-file mkdocs.yml` ([`scripts/docs.py`][fa-docs-py]).
  Its docs dependency group lists `zensical` and `mkdocstrings[python]`, and no `mkdocs-material` ([`pyproject.toml`][fa-pyproject]).
  The config names the `material` theme with `variant: classic` ([`mkdocs.yml`][fa-mkdocs]).
  A `workflow_run` workflow deploys with `cloudflare/wrangler-action` ([`deploy-docs.yml`][fa-deploy-docs]).
  A build of `master` goes to the Cloudflare Pages branch `main`, and a pull request's build goes to a branch named after its commit SHA.
- **Pydantic** deploys `dev` from `main` and `<major>.<minor>` plus the `latest` alias from a tag, with `mike` on the `docs-site` branch ([`docs-update.yml`][pd-docs-update]).
  The publish job installs Material Insiders from a private index, and the CI build uses the public package ([`docs-update.yml`][pd-docs-update], [`ci.yml`][pd-ci-docs]).
  Cloudflare Pages serves the `docs-site` branch and builds pull request previews ([`build-docs.sh` on `docs-site`][pd-docs-site-script], [`build-docs.sh` on `main`][pd-build-docs]).
  On 2026-09-25 `https://docs.pydantic.dev/latest/` returned a 301 redirect to `https://pydantic.dev/docs/validation/latest/get-started/`.
  CI's `deploy-docs` job now also dispatches an event to the private `pydantic/unified-docs` repository ([`ci.yml`][pd-ci-deploy-docs]).
- **pytest** sets `fail_on_warning: true` for Read the Docs, and its Sphinx config loads `sphinxcontrib.towncrier` to render unreleased fragments ([`.readthedocs.yaml`][pt-rtd], [`conf.py`][pt-conf]).
- **attrs** and **urllib3** install uv on Read the Docs and run the build through tox or `uv run` ([attrs][at-rtd], [urllib3][u3-rtd]).
- **Polars** pushes both sites to the `gh-pages` branch with `JamesIves/github-pages-deploy-action`, and GitHub Pages builds from that branch through its `pages-build-deployment` workflow ([API docs][pl-docs-python], [user guide][pl-docs-global], [workflows][pl-workflows-api]).
  The user guide runs its code blocks at build time through `markdown-exec` ([`mkdocs.yml`][pl-mkdocs]).
  Its `github-pages` environment accepts deployments from `gh-pages` only ([branch policy][pl-pages-policy]).
  The authenticated Pages endpoint reports a legacy build from `gh-pages` with the domain `docs.pola.rs`.

The response headers on 2026-09-25 confirm each host.
The hosts `docs.pytest.org`, `www.attrs.org` and `urllib3.readthedocs.io` sent `x-rtd-project`, and `docs.pola.rs` sent `x-github-request-id`.
All six responses carried Cloudflare headers.

What each host offers, from its own docs:

- **Read the Docs** builds each pull request by default on new projects, reports the build as a check, and serves the preview from a separate domain ([pull request previews][rtd-pr]).
  It makes versions from Git tags and branches ([versions][rtd-versions]).
  It builds with Sphinx or MkDocs by default, and supports any tool that generates HTML through custom build jobs ([build customization][rtd-build]).
  It shows EthicalAds, and a project can opt out of paid ads ([EthicalAds][rtd-ads]).
- **GitHub Pages** deploys from a workflow with `actions/upload-pages-artifact` and `actions/deploy-pages`.
  The deploy job needs `pages: write` and `id-token: write` and the `github-pages` environment ([custom workflows][gh-pages-workflows]).
  The `actions/deploy-pages` action at v5.0.1 has a `preview` input for pull request previews, and its description says the feature "is only in alpha currently and is not available to the public" ([`action.yml`][deploy-pages]).

## Docs tools for a typed library with a CLI

This section compares great-docs, MkDocs Material, Zensical and Sphinx, and adds MkDocs because Material and mkdocstrings run on it.
It rests on each project's repository, docs and PyPI metadata as of 2026-09-25, at the commits listed under Sources.

### Maintenance status

| Tool | Latest release | Status in its own sources |
| --- | --- | --- |
| great-docs | 0.17.0, 2026-08-13 | Beta classifier; first release 0.1.0 on 2026-03-20; MIT, from Posit |
| MkDocs Material | 9.7.7, 2026-07-17 | maintenance mode since 9.7.0; critical fixes and security updates until 2027-05-05 |
| Zensical | 0.0.65, 2026-09-24 | "0.0.x versioning (alpha / development releases)"; MIT; from the Material team |
| Sphinx | 9.1.0, 2025-12-31 | 9.1.1 in development; no status notice |
| MkDocs | 1.6.1, 2024-08-30 | 2.0.dev0 to 2.0.dev6 on PyPI since 2026-08-28, built from a new repository |

- **MkDocs Material.**
  A post from 2025-11-11 announced maintenance mode: "no new features will be added to Material for MkDocs" ([post][mat-blog]).
  Issue 8523 and `SECURITY.md` extend critical fixes and security updates to May 5, 2027 ([issue][mat-eol], [`SECURITY.md`][mat-security]).
  Its PyPI metadata requires `mkdocs<2,>=1.6`.
- **Zensical.**
  Its docs call the 0.0.x versions alpha and name a beta as the next step ([versioning][zen-versioning]).
  Its roadmap page announces 0.1.0 for November 5 ([roadmap][zen-roadmap]).
  It reads `mkdocs.yml` and supports 19 plugins as rewrites, among them mkdocstrings since 0.0.11 and markdown-exec since 0.0.47 ([plugins][zen-plugins]).
  It "silently ignores the configuration for plugins that are not listed", and it does not run them.
  It provides no `gh-deploy` command ([migration][zen-migration]).
- **MkDocs.**
  The `mkdocs/mkdocs` repository has five commits after 1.6.1, the last two on 2025-10-20.
  PyPI serves the 2.0 pre-releases from `encode/mkdocs`, a repository created on 2025-10-15.
  The 2.0.dev6 source loads no plugins, fixes its Markdown extensions in code, and raises an error when it finds `mkdocs.yml` ([source][mkdocs2-src]).
  Its lead maintainer and original author wrote in 2024 of "a future iteration of MkDocs that *doesn't* require or support plugins in order to customise the page generation" ([discussion][mkdocs-plugins], [maintainership][mkdocs-lead]).
  Material, mike and the MkDocs extra of mkdocs-typer2 require MkDocs below 2.0.
  A former maintainer announced ProperDocs, a drop-in fork of 1.x, on 2026-03-15, and released 1.6.7 on 2026-03-20 ([README][properdocs], [announcement][properdocs-announce]).
- **Sphinx.**
  Its changelog opens with 9.1.1 as in development ([`CHANGES.rst`][sphinx-changes]).
- **great-docs.**
  It builds on Quarto, which its README says to install separately because it "isn't a Python package" ([README][gd-readme]).

### What each tool offers oxy

| Need | great-docs | MkDocs Material | Zensical | Sphinx |
| --- | --- | --- | --- | --- |
| API reference from numpydoc | built in, through griffe | mkdocstrings-python | mkdocstrings-python | autodoc with napoleon or numpydoc, or sphinx-autoapi |
| Types from annotations | yes | yes | yes | napoleon with `autodoc_typehints = "description"`; numpydoc no |
| Click reference | built in | mkdocs-click | not in its docs | sphinx-click |
| Typer reference | on `main`, not released | mkdocs-typer2 | mkdocs-typer2, per that project's README | sphinxcontrib-typer |
| cyclopts reference | none | cyclopts plugin, experimental | plugin ignored | `cyclopts.sphinx_ext` |
| argparse reference | none | mkdocs-rich-argparse, pre-alpha | plugin ignored | sphinx-argparse |
| Executed examples | Quarto `{python}` cells, in pages and docstrings | markdown-exec, mkdocs-jupyter | markdown-exec | MyST-NB, jupyter-sphinx |
| Changelog page | built in, from GitHub Releases | snippets include | snippets include | `include` directive |
| GitHub Pages deploy | `great-docs setup-github-pages` writes a `deploy-pages` workflow | guide runs `mkdocs gh-deploy --force` to `gh-pages` | `zensical new` writes a `deploy-pages` workflow | guide pushes to `gh-pages`; no generator |
| Versions | built in, `versions:` key | mike | fork of mike, "transitional" | Read the Docs, or sphinx-polyversion |

Sources for the rows: great-docs [CLI][gd-cli], [docstrings][gd-docstrings], [changelog][gd-changelog], [versions][gd-versions] and [workflow][gd-workflow]; Material [publishing][mat-publish] and [versioning][mat-versioning]; Zensical [compatibility][zen-compat], [plugins][zen-plugins], [mike][zen-mike] and [publishing][zen-publish]; Sphinx [autodoc][sphinx-autodoc] and [deploying][sphinx-deploy]; and the CLI projects listed under Sources.

- great-docs 0.17.0 documents Click, Go and Rust CLIs ([CLI docs][gd-cli]).
  Its `main` branch added Typer on 2026-09-02, after 0.17.0, by converting a Typer app to a Click command ([`_typer_cli.py`][gd-typer]).
- cyclopts' `App.generate_docs` writes Markdown, HTML or reST ([`core.py`][cyclopts-generate]).
  That route produces a CLI reference without any docs plugin.
- The cyclopts MkDocs plugin carries the warning "The MkDocs plugin is **experimental**" ([docs][cyclopts-mkdocs]).
- Zensical ignores MkDocs plugins it has not rewritten, which covers the cyclopts plugin and mkdocs-rich-argparse.
  Both mkdocs-click and mkdocs-typer2 are Markdown extensions, and mkdocs-typer2's README says it works with Zensical ([README][mkdocs-typer2]).
- numpydoc does not read type annotations: issue 196 has been open since 2019 ([issue][numpydoc-196]).
- great-docs builds the site on pull requests, but it hosts no preview.
  Its `great-docs preview` command downloads the CI artifact and serves it on the reviewer's machine ([`_pr_preview.py`][gd-preview]).
  The workflow it writes pins actions by tag, not by SHA ([template][gd-workflow]).

### Docstrings without types

These runs used griffe 2.1.0, the version great-docs pins, griffelib 2.3.0, which mkdocstrings-python installs, and Sphinx 9.1.0, in throwaway environments on 2026-09-25.

- griffe fills each parameter's type from the signature when the numpydoc entry names no type.
- A `Returns` block whose only line is a description is a different case.
  The griffe parser stores that line as the return annotation and leaves the description empty.
- A `:` line followed by the indented description gives the signature's return type and keeps the description, as griffe's docs describe ([griffe][griffe-docstrings]).
- Sphinx's napoleon turns the same description-only block into `:rtype: <description>`, with no `:returns:` field.
  With the `:` line, napoleon writes `:returns: <description>` instead.
- numpydoc's format guide says "The type of each return value is always required" ([format][numpydoc-format]).
- ruff 0.16.8 with oxy's `ruff.toml` reports no docstring error for either form.

## Open questions

- **Direct pushes to `main`.**
  A ruleset that requires pull requests blocks the maintainer's direct pushes unless the admin role has an "Always allow" bypass.
  Whether oxy's ruleset requires pull requests at all, and what bypasses it, is a choice for [#22](https://github.com/ozanozbeker/oxyscraper/issues/22).
- **The required check.**
  One `alls-green` job keeps the required list stable, and path filters then belong inside the workflow.
  Which jobs it covers, including any live smoke test, is a choice for #22 and [#23](https://github.com/ozanozbeker/oxyscraper/issues/23).
- **Hooks in CI and their updates.**
  The pre-commit.ci service does not read `prek.toml`, and Dependabot's `pre-commit` ecosystem names only `.pre-commit-config.yaml`.
  Running prek in Actions with a scheduled `prek update`, or keeping a YAML config for pre-commit.ci and Dependabot, is a choice for #22.
- **Docs host.**
  GitHub Pages has no public pull request previews, while Read the Docs and Cloudflare Pages build one per pull request.
  Whether oxy needs previews is a choice for #22.
- **CLI reference.**
  Which tool documents oxy's CLI depends on the framework that [#19](https://github.com/ozanozbeker/oxyscraper/issues/19) picks.
  Version 0.17.0 of great-docs documents only Click, and cyclopts can write a Markdown reference for any tool.
- **Return docstrings.**
  A `Returns` block that holds only a description becomes the return type in griffe and in napoleon, and a `:` line above the description keeps it a description in both.
  Keeping that form, adding a type, or writing the `:` line is a choice for #22.

## Sources

### Libraries

FastAPI at [`50113da`][fa-tree]:

- Workflows: [`test.yml`][fa-test], [`build-docs.yml`][fa-build-docs], [`deploy-docs.yml`][fa-deploy-docs], [`pre-commit.yml`][fa-pre-commit], [`bump-pre-commit-hooks.yml`][fa-bump-hooks], [`zizmor.yml`][fa-zizmor] and [`publish.yml`][fa-publish].
- Config: [`dependabot.yml`][fa-dependabot], [`.pre-commit-config.yaml`][fa-hooks], [`latest-changes.yml`][fa-latest-changes], [`mkdocs.yml`][fa-mkdocs], [`pyproject.toml`][fa-pyproject] and [`scripts/docs.py`][fa-docs-py].
- API: [branch rules][fa-rules], [ruleset][fa-ruleset], [workflows][fa-workflows-api] and [commits][fa-commits].

Pydantic at [`a9a0e1d`][pd-tree]:

- Workflows: [`ci.yml`][pd-ci], [`docs-update.yml`][pd-docs-update], [`dependencies-check.yml`][pd-deps-check], [`third-party.yml`][pd-third-party] and [`integration.yml`][pd-integration].
- Config: [`dependabot.yml`][pd-dependabot], [`.pre-commit-config.yaml`][pd-hooks], [`zizmor.yml`][pd-zizmor], [`build-docs.sh`][pd-build-docs], [`release.yml`][pd-release-yml] and [the pull request template][pd-pr-template].
- The `docs-site` branch at [`6897227`][pd-docs-site], with [`build-docs.sh`][pd-docs-site-script] and [`versions.json`][pd-versions].
- API: [branch rules][pd-rules] and [environments][pd-envs].

pytest at [`8721173`][pt-tree]:

- Workflows: [`test.yml`][pt-test] and [`deploy.yml`][pt-deploy].
- Config: [`dependabot.yml`][pt-dependabot], [`.pre-commit-config.yaml`][pt-hooks], [`chronographer.yml`][pt-chronographer], [`.readthedocs.yaml`][pt-rtd], [`tox.ini`][pt-tox], [`conf.py`][pt-conf] and [`CONTRIBUTING.rst`][pt-contributing].
- API: [branch rules][pt-rules] and [rulesets][pt-rulesets].

attrs at [`8f76777`][at-tree]:

- Workflows: [`ci.yml`][at-ci], [`zizmor.yml`][at-zizmor], [`codeql-analysis.yml`][at-codeql] and [`pypi-package.yml`][at-pypi].
- Config: [`dependabot.yml`][at-dependabot], [`.pre-commit-config.yaml`][at-hooks], [`tox.ini`][at-tox], [`.readthedocs.yaml`][at-rtd] and [`CONTRIBUTING.md`][at-contributing].
- API: [branch][at-branch] and [commits][at-commits].

urllib3 at [`ed0ed07`][u3-tree]:

- Workflows: [`ci.yml`][u3-ci], [`lint.yml`][u3-lint], [`changelog.yml`][u3-changelog], [`codeql.yml`][u3-codeql], [`downstream.yml`][u3-downstream], [`scorecards.yml`][u3-scorecard] and [`publish.yml`][u3-publish].
- Config: [`dependabot.yml`][u3-dependabot], [`.pre-commit-config.yaml`][u3-hooks], [`noxfile.py`][u3-nox-lint] and [`.readthedocs.yml`][u3-rtd].
- API: [branch][u3-branch].

Polars at [`efba0b7`][pl-tree]:

- Workflows: [`test-python.yml`][pl-test-python], [`lint-python.yml`][pl-lint-python], [`pr-labeler.yml`][pl-pr-labeler], [`docs-python.yml`][pl-docs-python], [`docs-global.yml`][pl-docs-global] and [`release-python.yml`][pl-release].
- Config: [`dependabot.yml`][pl-dependabot], [`pr-title-checker-config.json`][pl-title-config], [`release-drafter.yml`][pl-release-drafter], [`mkdocs.yml`][pl-mkdocs] and [the contributing guide][pl-contributing].
- API: [branch][pl-branch], [workflows][pl-workflows-api] and [`github-pages` branch policy][pl-pages-policy].

The pull requests behind the job counts are FastAPI [#16289][fa-pr], Pydantic [#13866][pd-pr], pytest [#15096][pt-pr], attrs [#1617][at-pr], urllib3 [#5276][u3-pr] and Polars [#29539][pl-pr].
GraphQL supplied the merge settings of all six, and `GET /repos/{owner}/{repo}/commits/{sha}/pulls` matched commits to pull requests.

### GitHub docs

- Rules: [about rulesets][gh-rules-about], [available rules][gh-rules-available], [creating rulesets][gh-rules-creating] and [troubleshooting required status checks][gh-checks-troubleshoot].
- Merging: [merge queue][gh-merge-queue], [commit squashing][gh-squash] and [approving a pull request][gh-approve].
- Dependabot: [options reference][gh-dependabot-options] and [supported ecosystems][gh-dependabot-ecosystems].
- Security: [secure use][gh-secure-use], [Actions settings][gh-actions-settings], [CodeQL][gh-codeql] and [code scanning setup types][gh-codeql-setup].
- [Custom workflows with GitHub Pages][gh-pages-workflows] and [the GraphQL `Repository` object][gh-graphql-repo].

### Tools and services

- [`re-actors/alls-green`][alls-green] v1.3.0 at `b5b5b37`.
- [`zizmorcore/zizmor-action`][zizmor-action] v0.6.4 at `8eacaa5`.
- [`actions/deploy-pages`][deploy-pages] v5.0.1 at `368f825`.
- prek v0.5.3 at `5ba6dc5`: [CI][prek-ci], [compatibility][prek-compat], [CLI reference][prek-cli] and [changelog][prek-changelog].
- [pre-commit.ci][precommit-ci] and its maintainer's comments on [issue 13][precommit-ci-13].
- [The Latest Changes app][latest-changes].
- Read the Docs: [pull request previews][rtd-pr], [versions][rtd-versions], [build customization][rtd-build] and [EthicalAds][rtd-ads].

### Docs tools

- great-docs 0.17.0 at `1ce8eb8` and `main` at `25dd6f1`: [README][gd-readme], [CLI docs][gd-cli], [Typer support][gd-typer], [docstrings guide][gd-docstrings], [changelog guide][gd-changelog], [versions guide][gd-versions], [workflow template][gd-workflow] and [`_pr_preview.py`][gd-preview].
- MkDocs Material at `1c73dca`: [maintenance post][mat-blog], [`SECURITY.md`][mat-security], [issue 8523][mat-eol], [publishing guide][mat-publish] and [versioning guide][mat-versioning].
- Zensical 0.0.65 at `27fa310`, with its docs at `72fdc06`: [versioning][zen-versioning], [MkDocs compatibility][zen-compat], [plugins][zen-plugins], [migration][zen-migration], [mike][zen-mike], [publishing][zen-publish] and [roadmap][zen-roadmap].
- Sphinx at `b04a210`: [autodoc][sphinx-autodoc], [deploying tutorial][sphinx-deploy] and [`CHANGES.rst`][sphinx-changes].
- MkDocs at `2862536`, 2.0.dev6 at `1110d2e` and ProperDocs at `fcb5316`: [PyPI][mkdocs-pypi], [2.0.dev6 source][mkdocs2-src], [plugins discussion][mkdocs-plugins], [maintainership discussion][mkdocs-lead], [ProperDocs README][properdocs] and [announcement][properdocs-announce].
- CLI projects: [sphinx-click][sphinx-click] 6.2.0, [sphinxcontrib-typer][sphinxcontrib-typer] 0.10.0, [sphinx-argparse][sphinx-argparse] 0.6.1, [mkdocs-click][mkdocs-click] 0.9.0, [mkdocs-typer2][mkdocs-typer2] 0.4.1, [mkdocs-rich-argparse][mkdocs-rich-argparse] 0.1.3, and cyclopts 5.0.0 with its [Sphinx extension][cyclopts-sphinx], [MkDocs plugin][cyclopts-mkdocs] and [`generate_docs`][cyclopts-generate].
- Docstring parsing: [griffe][griffe-docstrings] 2.3.0 docs, [mkdocstrings-python on NumPy style][mkdocstrings-numpy], [the numpydoc format guide][numpydoc-format] and [numpydoc issue 196][numpydoc-196].
- PyPI JSON supplied every version, date, classifier and MkDocs bound.

[fa-tree]: https://github.com/fastapi/fastapi/tree/50113da16fec53b66b80d75e80a89296de4fa5a5
[fa-test]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/test.yml
[fa-test-trigger]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/test.yml#L3-L12
[fa-test-filter]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/test.yml#L19-L50
[fa-test-matrix]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/test.yml#L52-L132
[fa-test-green]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/test.yml#L313-L332
[fa-build-docs]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/build-docs.yml
[fa-build-docs-green]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/build-docs.yml#L117-L129
[fa-deploy-docs]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/deploy-docs.yml#L1-L84
[fa-pre-commit]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/pre-commit.yml#L7-L91
[fa-bump-hooks]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/bump-pre-commit-hooks.yml
[fa-zizmor]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/zizmor.yml
[fa-publish]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/publish.yml
[fa-dependabot]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/dependabot.yml
[fa-hooks]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.pre-commit-config.yaml
[fa-latest-changes]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/latest-changes.yml
[fa-mkdocs]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/docs/en/mkdocs.yml#L3-L6
[fa-pyproject]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/pyproject.toml#L131-L146
[fa-docs-py]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/scripts/docs.py#L284-L290
[fa-rules]: https://api.github.com/repos/fastapi/fastapi/rules/branches/master
[fa-ruleset]: https://api.github.com/repos/fastapi/fastapi/rulesets/20498108
[fa-workflows-api]: https://api.github.com/repos/fastapi/fastapi/actions/workflows
[fa-commits]: https://github.com/fastapi/fastapi/commits/50113da16fec53b66b80d75e80a89296de4fa5a5
[fa-pr]: https://github.com/fastapi/fastapi/pull/16289/checks
[fa-precommitci-prs]: https://github.com/fastapi/fastapi/pulls?q=is%3Apr+author%3Aapp%2Fpre-commit-ci
[pd-tree]: https://github.com/pydantic/pydantic/tree/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74
[pd-ci]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml
[pd-ci-core-build]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml#L70-L73
[pd-ci-docs]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml#L669-L696
[pd-ci-test]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml#L717-L736
[pd-ci-te]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml#L931-L955
[pd-ci-deploy-docs]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml#L972-L992
[pd-ci-builds-test]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml#L330-L436
[pd-ci-release]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/ci.yml#L958-L997
[pd-docs-update]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/docs-update.yml#L66-L125
[pd-deps-check]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/dependencies-check.yml
[pd-third-party]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/third-party.yml#L15-L43
[pd-integration]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/workflows/integration.yml
[pd-dependabot]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/dependabot.yml
[pd-hooks]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.pre-commit-config.yaml
[pd-zizmor]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/zizmor.yml
[pd-build-docs]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/build-docs.sh#L3-L4
[pd-release-yml]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/release.yml
[pd-pr-template]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/.github/PULL_REQUEST_TEMPLATE.md?plain=1#L14
[pd-docs-site]: https://github.com/pydantic/pydantic/tree/6897227c3456bd0d897f4af6067555f1cf2591eb
[pd-docs-site-script]: https://github.com/pydantic/pydantic/blob/6897227c3456bd0d897f4af6067555f1cf2591eb/build-docs.sh
[pd-versions]: https://github.com/pydantic/pydantic/blob/6897227c3456bd0d897f4af6067555f1cf2591eb/versions.json
[pd-rules]: https://api.github.com/repos/pydantic/pydantic/rules/branches/main
[pd-envs]: https://api.github.com/repos/pydantic/pydantic/environments
[pd-pr]: https://github.com/pydantic/pydantic/pull/13866/checks
[pt-tree]: https://github.com/pytest-dev/pytest/tree/8721173580390a9d297e5af06cac3f0b6841f425
[pt-test]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/workflows/test.yml
[pt-test-trigger]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/workflows/test.yml#L3-L34
[pt-test-matrix]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/workflows/test.yml#L47-L270
[pt-deploy]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/workflows/deploy.yml
[pt-tox]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/tox.ini#L105
[pt-hooks]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.pre-commit-config.yaml
[pt-dependabot]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/dependabot.yml
[pt-chronographer]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/chronographer.yml
[pt-rtd]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.readthedocs.yaml
[pt-conf]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/doc/en/conf.py#L29-L41
[pt-contributing]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/CONTRIBUTING.rst?plain=1#L478-L533
[pt-rules]: https://api.github.com/repos/pytest-dev/pytest/rules/branches/main
[pt-rulesets]: https://api.github.com/repos/pytest-dev/pytest/rulesets/19676373
[pt-pr]: https://github.com/pytest-dev/pytest/pull/15096/checks
[at-tree]: https://github.com/python-attrs/attrs/tree/8f767776326faaed11e6c2974798787f6e19b343
[at-ci]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/workflows/ci.yml
[at-ci-matrix]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/workflows/ci.yml#L24-L81
[at-zizmor]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/workflows/zizmor.yml
[at-codeql]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/workflows/codeql-analysis.yml
[at-pypi]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/workflows/pypi-package.yml
[at-dependabot]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/dependabot.yml
[at-hooks]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.pre-commit-config.yaml
[at-tox]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/tox.ini#L108-L141
[at-rtd]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.readthedocs.yaml
[at-contributing]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/CONTRIBUTING.md?plain=1#L283
[at-branch]: https://api.github.com/repos/python-attrs/attrs/branches/main
[at-commits]: https://github.com/python-attrs/attrs/commits/8f767776326faaed11e6c2974798787f6e19b343
[at-precommitci-prs]: https://github.com/python-attrs/attrs/pulls?q=is%3Apr+author%3Aapp%2Fpre-commit-ci
[at-pr]: https://github.com/python-attrs/attrs/pull/1617/checks
[u3-tree]: https://github.com/urllib3/urllib3/tree/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5
[u3-ci]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/ci.yml#L3-L8
[u3-ci-matrix]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/ci.yml#L43-L101
[u3-lint]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/lint.yml
[u3-nox-lint]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/noxfile.py#L225-L229
[u3-changelog]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/changelog.yml
[u3-codeql]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/codeql.yml
[u3-downstream]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/downstream.yml
[u3-scorecard]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/scorecards.yml
[u3-publish]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/publish.yml
[u3-dependabot]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/dependabot.yml
[u3-hooks]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.pre-commit-config.yaml
[u3-rtd]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.readthedocs.yml
[u3-branch]: https://api.github.com/repos/urllib3/urllib3/branches/main
[u3-pr]: https://github.com/urllib3/urllib3/pull/5276/checks
[pl-tree]: https://github.com/pola-rs/polars/tree/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef
[pl-test-python]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/test-python.yml#L3-L66
[pl-test-python-steps]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/test-python.yml#L114-L164
[pl-lint-python]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/lint-python.yml
[pl-pr-labeler]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/pr-labeler.yml
[pl-title-config]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/pr-title-checker-config.json
[pl-release-drafter]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/release-drafter.yml
[pl-contributing]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/docs/source/development/contributing/index.md?plain=1#L284-L300
[pl-docs-python]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/docs-python.yml#L89-L111
[pl-docs-global]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/docs-global.yml#L109-L131
[pl-mkdocs]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/mkdocs.yml#L196-L199
[pl-release]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/release-python.yml
[pl-dependabot]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/dependabot.yml
[pl-branch]: https://api.github.com/repos/pola-rs/polars/branches/main
[pl-workflows-api]: https://api.github.com/repos/pola-rs/polars/actions/workflows
[pl-pages-policy]: https://api.github.com/repos/pola-rs/polars/environments/github-pages/deployment-branch-policies
[pl-pr]: https://github.com/pola-rs/polars/pull/29539/checks
[gh-rules-about]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
[gh-rules-available]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
[gh-rules-creating]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository#granting-bypass-permissions-for-your-branch-or-tag-ruleset
[gh-checks-troubleshoot]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks#handling-skipped-but-required-checks
[gh-merge-queue]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
[gh-squash]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/configuring-commit-squashing-for-pull-requests
[gh-approve]: https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews
[gh-dependabot-options]: https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference
[gh-dependabot-ecosystems]: https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories
[gh-secure-use]: https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions
[gh-actions-settings]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
[gh-codeql]: https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning
[gh-codeql-setup]: https://docs.github.com/en/code-security/concepts/code-scanning/setup-types
[gh-pages-workflows]: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
[gh-graphql-repo]: https://docs.github.com/en/graphql/reference/objects#repository
[alls-green]: https://github.com/re-actors/alls-green/blob/b5b5b37504aa4183270bd3d855c52a67f212be35/README.md#why
[zizmor-action]: https://github.com/zizmorcore/zizmor-action/blob/8eacaa5f3f72b6638f4f87c3f66113bbc0f363dd/README.md#usage-with-github-advanced-security-recommended
[deploy-pages]: https://github.com/actions/deploy-pages/blob/368f82528645a54fb793d4d04e342629a3f51346/action.yml#L28-L31
[prek-ci]: https://github.com/j178/prek/blob/5ba6dc58a6285c551620354f139bbd8b5fa60e23/docs/ci.md#github-actions
[prek-compat]: https://github.com/j178/prek/blob/5ba6dc58a6285c551620354f139bbd8b5fa60e23/docs/compatibility.md
[prek-changelog]: https://github.com/j178/prek/blob/5ba6dc58a6285c551620354f139bbd8b5fa60e23/CHANGELOG.md
[prek-cli]: https://github.com/j178/prek/blob/5ba6dc58a6285c551620354f139bbd8b5fa60e23/docs/reference/cli.md#prek-update
[precommit-ci]: https://pre-commit.ci/
[list-deps]: https://github.com/samuelcolvin/list-python-dependencies/blob/43f660fbd655f25c3e3ebd3165b09974bbf98e05/action.yml#L13-L17
[precommit-ci-13]: https://github.com/pre-commit-ci/issues/issues/13
[latest-changes]: https://github.com/apps/latest-changes
[rtd-pr]: https://docs.readthedocs.com/platform/stable/pull-requests.html
[rtd-versions]: https://docs.readthedocs.com/platform/stable/versions.html
[rtd-build]: https://docs.readthedocs.com/platform/stable/build-customization.html
[rtd-ads]: https://docs.readthedocs.com/platform/stable/advertising/ethical-advertising.html
[gd-readme]: https://github.com/posit-dev/great-docs/blob/25dd6f1a29dc6c18b295d6ad59d02fdaece0ba82/README.md?plain=1#L80-L87
[gd-cli]: https://github.com/posit-dev/great-docs/blob/1ce8eb88191df75405345b6ba2d35bea53a4f7f6/user_guide/07-cli-documentation.qmd#L10-L18
[gd-typer]: https://github.com/posit-dev/great-docs/blob/25dd6f1a29dc6c18b295d6ad59d02fdaece0ba82/great_docs/_typer_cli.py#L1-L11
[gd-docstrings]: https://github.com/posit-dev/great-docs/blob/25dd6f1a29dc6c18b295d6ad59d02fdaece0ba82/user_guide/04-writing-docstrings.qmd#L207-L246
[gd-changelog]: https://github.com/posit-dev/great-docs/blob/25dd6f1a29dc6c18b295d6ad59d02fdaece0ba82/user_guide/17-changelog.qmd#L12
[gd-versions]: https://github.com/posit-dev/great-docs/blob/25dd6f1a29dc6c18b295d6ad59d02fdaece0ba82/user_guide/30-multi-version-docs.qmd#L19-L37
[gd-workflow]: https://github.com/posit-dev/great-docs/blob/25dd6f1a29dc6c18b295d6ad59d02fdaece0ba82/great_docs/assets/github-workflow-template.yml
[gd-preview]: https://github.com/posit-dev/great-docs/blob/25dd6f1a29dc6c18b295d6ad59d02fdaece0ba82/great_docs/_pr_preview.py#L1-L8
[mat-blog]: https://github.com/squidfunk/mkdocs-material/blob/1c73dca3ff4909e4cddd0d3b6e272298e902dec7/docs/blog/posts/insiders-now-free-for-everyone.md?plain=1#L21
[mat-security]: https://github.com/squidfunk/mkdocs-material/blob/1c73dca3ff4909e4cddd0d3b6e272298e902dec7/SECURITY.md?plain=1#L25-L29
[mat-eol]: https://github.com/squidfunk/mkdocs-material/issues/8523
[mat-publish]: https://github.com/squidfunk/mkdocs-material/blob/1c73dca3ff4909e4cddd0d3b6e272298e902dec7/docs/publishing-your-site.md?plain=1#L15-L51
[mat-versioning]: https://github.com/squidfunk/mkdocs-material/blob/1c73dca3ff4909e4cddd0d3b6e272298e902dec7/docs/setup/setting-up-versioning.md
[zen-versioning]: https://github.com/zensical/docs/blob/72fdc0623f97b921215f9b95f084a840fbf4cbcf/docs/upgrade.md?plain=1#L48-L53
[zen-compat]: https://github.com/zensical/docs/blob/72fdc0623f97b921215f9b95f084a840fbf4cbcf/docs/compatibility/mkdocs/index.md?plain=1#L13-L23
[zen-plugins]: https://github.com/zensical/docs/blob/72fdc0623f97b921215f9b95f084a840fbf4cbcf/docs/compatibility/mkdocs/plugins.md?plain=1#L40-L44
[zen-migration]: https://github.com/zensical/docs/blob/72fdc0623f97b921215f9b95f084a840fbf4cbcf/docs/compatibility/mkdocs/migration.md?plain=1#L61-L86
[zen-mike]: https://github.com/zensical/docs/blob/72fdc0623f97b921215f9b95f084a840fbf4cbcf/docs/compatibility/mkdocs/mike.md?plain=1#L7-L30
[zen-publish]: https://github.com/zensical/docs/blob/72fdc0623f97b921215f9b95f084a840fbf4cbcf/docs/publish-your-site.md?plain=1#L14-L70
[zen-roadmap]: https://zensical.org/roadmap/
[sphinx-autodoc]: https://github.com/sphinx-doc/sphinx/blob/b04a2101295ac3fb725b16111eda0284b6da4cca/doc/usage/extensions/autodoc.rst?plain=1#L1192-L1245
[sphinx-deploy]: https://github.com/sphinx-doc/sphinx/blob/b04a2101295ac3fb725b16111eda0284b6da4cca/doc/tutorial/deploying.rst?plain=1#L165-L232
[sphinx-changes]: https://github.com/sphinx-doc/sphinx/blob/b04a2101295ac3fb725b16111eda0284b6da4cca/CHANGES.rst?plain=1#L1
[mkdocs-pypi]: https://pypi.org/pypi/mkdocs/json
[mkdocs2-src]: https://github.com/encode/mkdocs/blob/1110d2ea607561335b74eb11e61252379c6a1855/src/mkdocs/mkdocs.py#L220-L238
[mkdocs-plugins]: https://github.com/mkdocs/mkdocs/discussions/3815#discussioncomment-10398312
[mkdocs-lead]: https://github.com/mkdocs/mkdocs/discussions/3677
[properdocs]: https://github.com/ProperDocs/properdocs/blob/fcb5316303da1ad2c8fa1974dbfa18e056493239/README.md?plain=1#L8
[properdocs-announce]: https://github.com/orgs/ProperDocs/discussions/33
[sphinx-click]: https://github.com/click-contrib/sphinx-click
[sphinxcontrib-typer]: https://github.com/sphinx-contrib/typer
[sphinx-argparse]: https://github.com/sphinx-doc/sphinx-argparse
[mkdocs-click]: https://github.com/mkdocs/mkdocs-click
[mkdocs-typer2]: https://github.com/syn54x/mkdocs-typer2/blob/f2a5e1581121b5100619c961400134ed5d201f8a/README.md?plain=1#L15
[mkdocs-rich-argparse]: https://github.com/i-VRESSE/mkdocs_rich_argparse
[cyclopts-sphinx]: https://github.com/BrianPugh/cyclopts/blob/db5f7b60aaad670dbfce7be66c2c476a83ac866b/docs/source/sphinx_integration.rst
[cyclopts-mkdocs]: https://github.com/BrianPugh/cyclopts/blob/db5f7b60aaad670dbfce7be66c2c476a83ac866b/docs/source/mkdocs_integration.rst?plain=1#L6-L9
[cyclopts-generate]: https://github.com/BrianPugh/cyclopts/blob/db5f7b60aaad670dbfce7be66c2c476a83ac866b/cyclopts/core.py#L2550-L2575
[griffe-docstrings]: https://github.com/mkdocstrings/griffe/blob/7c898a9685c8ac29e1a4fd7767e85bf830b75a58/docs/reference/docstrings.md?plain=1#L1357-L1368
[mkdocstrings-numpy]: https://github.com/mkdocstrings/python/blob/c888dc294f4c8305479d358e976fd8cbb2e0c62c/docs/usage/docstrings/numpy.md?plain=1#L5-L7
[numpydoc-format]: https://github.com/numpy/numpydoc/blob/c6f5df5a77cc3022f688e3d92ebc0557dcabd484/doc/format.rst?plain=1#L245
[numpydoc-196]: https://github.com/numpy/numpydoc/issues/196

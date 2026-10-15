# CI/CD across Epistole, oxyscraper and dagster-dataframely

Written 2026-10-12.
On 2026-10-15 Epistole's pull requests from section 6 merged as #124 to #129 and #131, and the pull request that added this note made `CONTRIBUTING.md` the standard.
It covers `ozanozbeker/epistole` at `db84c98`, `ozanozbeker/oxyscraper` at `a486f1c`, and `ozanozbeker/dagster-dataframely` at `6688a5e`.
The local oxyscraper checkout is one commit behind, at `4f45e85`, and that commit touches no CI file.

Every claim comes from read-only `gh api` calls, the three checkouts, and throwaway clones.
Nothing in the repos, on GitHub or on PyPI was changed.
One side effect: a check ran `uv run --locked` in `~/Dev/epistole`, which re-synced the untracked `.venv` to the committed `uv.lock`.

oxyscraper is going away, so [section 8](#8-retiring-oxyscraper) and the appendices keep everything from it that no other repo holds. dd means dagster-dataframely.

## Contents

1. [Summary](#1-summary)
2. [How three standards came to exist](#2-how-three-standards-came-to-exist)
3. [Side by side](#3-side-by-side)
4. [Findings](#4-findings)
5. [The unified standard](#5-the-unified-standard)
6. [Plan for Epistole](#6-plan-for-epistole)
7. [Plan for dagster-dataframely](#7-plan-for-dagster-dataframely)
8. [Retiring oxyscraper](#8-retiring-oxyscraper)
9. [Open questions](#9-open-questions)
10. Appendices
    - [A. The decision record from oxyscraper](#appendix-a-the-decision-record-from-oxyscraper)
    - [B. oxyscraper#22, the resolution, verbatim](#appendix-b-oxyscraper22-the-resolution-verbatim)
    - [C. Repository settings and the ruleset JSON](#appendix-c-repository-settings-and-the-ruleset-json)
    - [D. Traps](#appendix-d-traps)
    - [E. oxyscraper files kept verbatim](#appendix-e-oxyscraper-files-kept-verbatim)
    - [F. Method](#appendix-f-method)

## 1. Summary

**Make Epistole's `CONTRIBUTING.md` the one standard, fix Epistole first, give dagster-dataframely the security settings now, and copy what only oxyscraper holds before deleting it.**

- Three standards exist because each repo copied another and then changed on its own.
  dagster-dataframely set up its standard first (2026-08-07), Epistole second (2026-09-07, with release-please and hooks but no CI workflow), and oxyscraper wrote the third and most complete one (2026-09-28).
- Epistole copied oxyscraper's standard on 2026-09-30 at 04:22 UTC.
  oxyscraper merged 9 more CI changes from 18:26 UTC that day on, and none reached Epistole.
- dagster-dataframely never adopted the standard.
  It has no protection on `main` and no approval step before PyPI.
- No repo holds the standard once oxyscraper is deleted.
  Epistole's `CONTRIBUTING.md:3-6` and `~/.claude/CLAUDE.md:64-66` both point at oxyscraper, and one of those links already names a missing anchor.
- On 2026-10-11 the maintainer decided to stop maintaining oxyscraper and to delete the repo and the PyPI project (oxyscraper memory `oxyscraper-sunset.md`).
  oxylake's research tickets still ran jobs through the package on 2026-10-07, so check oxylake before the PyPI project is deleted ([8.2](#82-steps-before-deletion)).

### 1.1 Broken or wrong today

| # | Repo | Problem | Fix |
| --- | --- | --- | --- |
| 1 | Epistole | A `deps:` PR title fails the required `title` check, so no floor can rise as `CONTRIBUTING.md:119` says it must. | oxyscraper's commit-type list ([6.3](#63-snippets)). |
| 2 | Epistole | No hook reads `user_guide/*.qmd`: prek tags `.qmd` as `quarto`, not `markdown`. | `"quarto"` in ruff-format's `types_or`; rumdl's `types` becomes `types_or = ["markdown", "quarto"]`; `extension = { qmd = "markdown" }` in `ruff.toml`. |
| 3 | Epistole, oxyscraper | `gitleaks` and `check-added-large-files` scan nothing in CI: both read staged changes only. | A manual-stage `gitleaks-ci` hook and `SKIP` for the two in CI. |
| 4 | Epistole, oxyscraper | zizmor skips 5 online audits in CI, because the `lint` job sets no token. | `GH_TOKEN: ${{ github.token }}` on the prek step. |
| 5 | Epistole, oxyscraper | CPython 3.15.0 went final on 2026-10-09, and the policy says it joins at its final release. | Add 3.15 to `test` and the classifiers. |
| 6 | Epistole | `CONTRIBUTING.md:6` links `#a-new-repo`, an anchor oxyscraper#95 renamed on 2026-10-01. Lines 3-6 name oxyscraper as the reference repo. | Rewrite the lines ([8.4](#84-replacement-text)). |
| 7 | Epistole, oxyscraper | The Pages sites serve plain HTTP with no redirect (`https_enforced: false`). | One `gh api -X PUT` each. |
| 8 | Epistole, oxyscraper | The Pages upload drops `.well-known/`, so the `npx skills add` URL the site advertises returns 404. | `include-hidden-files: true`. |
| 9 | dagster-dataframely | No ruleset, no `pypi` reviewer or tag policy, Actions can approve PRs, SHA pins not required, Dependabot alerts, security updates and CodeQL off, `uv.lock` outside Dependabot. | Tier 1 ([7.1](#71-tier-1-the-security-floor)). |
| 10 | dagster-dataframely | The weekly `latest` job will fail on its next run, due 2026-10-12 (measured in a sandbox): polars 2.0.0 removed `scan_parquet(rechunk=)`, and `dagster_polars` still passes it. | Drop `latest` in tier 1. |
| 11 | Epistole | `CONTRIBUTING.md:52` says Dependabot runs on Mondays; it runs on Wednesdays. | `day: monday`. |
| 12 | Epistole, oxyscraper | CI installed uv 0.13.0 two days after its release, which skips the 7-day cooldown every other update keeps. | `version: latest-known` on `setup-uv`. |

### 1.2 Before deleting oxyscraper

1. Check that nothing still installs `oxyscraper` from PyPI: oxylake's research tickets ran jobs through it on 2026-10-07.
2. Copy three research notes.
   The first two hold 325 external links that exist nowhere else.
   `httpx2.md` holds the evidence for the `httpx2>=2.12` floor that Epistole shares (D24) and for testing httpx2 without RESPX (D45).

   ```bash
   cp ~/Dev/oxyscraper/docs/research/{release-practices,ci-and-docs-practices,httpx2}.md ~/Dev/epistole/docs/research/
   ```

3. Merge the Epistole PR that rewrites `CONTRIBUTING.md:3-6` ([6.2](#62-pull-requests-in-order), PR 8).
4. Replace `~/.claude/CLAUDE.md:64-66` with the text in [8.4](#84-replacement-text).
5. Move `typing-everywhere.md` and `dev-floors-newest-past-cooldown.md` from oxyscraper's project memory into `~/.claude/CLAUDE.md` or Epistole's memory, because both state preferences for every package.
6. Uninstall the release App from oxyscraper, remove oxyscraper's trusted publisher on pypi.org, then delete the PyPI project and the repo ([8.2](#82-steps-before-deletion)).

## 2. How three standards came to exist

### 2.1 Timeline

| Date | Repo | What changed |
| --- | --- | --- |
| 2026-08-04 | dd | `prek.toml`, `ruff.toml`, `rumdl.toml` from a personal template (`bdd0a1d`) |
| 2026-08-07 | dd | **Standard 1.** `ci.yml` runs pytest only plus a weekly `latest` job; `release.yml` tests, builds and publishes; `dependabot.yml` covers actions only (`bdd31db`). Frozen hook revs, zizmor, typos, `[tool.uv] required-version` (`496d401`). |
| 2026-09-07 | Epistole | **Standard 2.** The same template, trimmed. release-please and publishing in one `release.yml` on push to `main`; no CI workflow (`a925a8a`, `8a123c4`). A pytest pre-commit hook followed on 2026-09-10 (`5ba17ec`). |
| 2026-09-10 | Epistole | The `uv.lock` JSONPath for release-please (`b63c8ef`). |
| 2026-09-11 | none | `~/Dev/github-publishing/` (not a git repo) compares dd and Epistole and drafts a standard. Not adopted as written. |
| 2026-09-13 | dd | CI `lint` job runs every prek hook (`ec425b0`); `py.typed` wheel check (`f0e5f4a`). |
| 2026-09-14 | dd | great-docs site; Quarto pinned to 1.10.18 (`865a58a`). |
| 2026-09-23 | oxyscraper | Copies Epistole's `prek.toml`, `ruff.toml`, `rumdl.toml`, `tombi.toml`, `pyrefly.toml` (`8717446`). |
| 2026-09-25 | oxyscraper | Surveys of six large libraries (#27, #28). |
| 2026-09-28 | oxyscraper | **Standard 3.** #22 written as the standard for every package; six workflows, `dependabot.yml`, release-please config, rulesets (`332c944`, #33). It reuses dd's hardening and Epistole's release-please findings. |
| 2026-09-29 to 30 | dd, Epistole, oxyscraper | Logo, favicon, social card, `title_template` workaround, `_brand.yml`. |
| 2026-09-30 04:22 | Epistole | Adopts standard 3 as of oxyscraper `d5ca42a` (#80, `357af09`). |
| 2026-09-30 to 10-05 | oxyscraper | Coverage job and `live` marker (#83), `pyrefly-typing` (#89), `deps` type (#91), "A new repo" renamed (#95), floor wording (#109, #110), monthly dev-floor raise (#111), `--extra cli` docs (#126), `live.yml` (#133). None reached Epistole. |

### 2.2 Who copied what

| Pattern | First in | Then |
| --- | --- | --- |
| `persist-credentials: false`, 7-day Dependabot cooldown, cron minute `17 6`, no cache on the release path | dd `bdd31db` | oxyscraper `332c944`, Epistole `357af09` |
| `py.typed` check on the built wheel | dd `f0e5f4a` | oxyscraper, Epistole |
| Quarto 1.10.18 pin, `cache-suffix: docs`, `timeout-minutes: 20` on the docs build | dd `865a58a` | oxyscraper, Epistole |
| release-please, the `uv.lock` `extra-files` JSONPath, the "never pass `release-type`" trap | Epistole `8a123c4`, `b63c8ef` | oxyscraper `332c944` |
| `prek.toml`, `ruff.toml`, `rumdl.toml`, `tombi.toml`, `pyrefly.toml` | Epistole `a925a8a` | oxyscraper `8717446` |
| Every workflow, `dependabot.yml`, `CONTRIBUTING.md` | oxyscraper `332c944`, `bbb6325` | Epistole `357af09` |
| great-docs logo, favicon, `include_in_header`, `social_cards`, `seo`, `assets/theme.css` | dd `b04e05b`, `195234b` | Epistole `d61a006`, `70ac733` |

Each repo copied the standard once and never again.
The rule in `~/.claude/CLAUDE.md` says to copy oxyscraper, and nothing says to copy again.
Every difference between Epistole and oxyscraper in [section 4](#4-findings) was found by hand with `diff -u`, 11 days after the copy.

## 3. Side by side

### 3.1 Workflows

| File | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| `ci.yml` | `test` (Ubuntu, 3.12, editable), `lint`, weekly `latest` (3.12 to 3.14, `uv sync --upgrade`) | `test` (3 OS by 3.13, 3.14, built wheel), `next-python`, `lowest`, `lint`, `docs`, `all-green` | Epistole's plus 3.11 and 3.12, `coverage`, `--all-extras` |
| `pr-title.yml` | none | runs the `commit-msg` hook on the title | byte-identical to Epistole's |
| `release-please.yml` | none | App token, config in a file | byte-identical to Epistole's |
| `release.yml` | tests 3.12 to 3.14, builds, `testpypi` on dispatch, `pypi` with no approval | builds, then `pypi` after approval | Epistole's |
| `docs.yml` | builds on PR, deploys on push to `main`, `include-hidden-files: true` | deploys on `release: published` | Epistole's plus `--extra cli` |
| `prek-update.yml` | none | monthly `prek update --freeze --cooldown-days 7` | Epistole's plus a script that raises `dev` floors |
| `live.yml` | none | none | weekly billed live suite in a `live` environment |
| `dependabot.yml` | actions only, Monday 06:00, prefix `chore` | `uv` and actions, weekly with no day, `chore` and `ci` | Epistole's |

All three pin every action to a full SHA with a version comment, set `persist-credentials: false` on every checkout, and use no `pull_request_target`.
Epistole and oxyscraper also start every workflow with `permissions: {}`; dd grants `contents: read` at the top of `ci.yml` and `docs.yml`.

### 3.2 CI jobs

| Concern | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| PR test matrix | Ubuntu, 3.12 only | 3 OS by 3.13, 3.14 | 3 OS by 3.11 to 3.14 |
| Install | editable | `--no-editable` (built wheel) | `--no-editable --all-extras` |
| Next CPython | none | `next-python` on 3.15, may fail | same |
| Floors | none; `pyproject.toml:33` sets each floor to the lock | `lowest`: `--resolution lowest-direct` on 3.13 | same on 3.11 |
| Newest dependencies | weekly `latest`; only deprecation warnings in Dagster's wording become errors | none | none |
| Warnings | not errors on PRs | `filterwarnings = ["error"]` | same |
| Coverage | none | none | 100% line gate, Codecov over OIDC |
| Lint | `prek run --all-files` | same | same |
| Docs build on PR | in `docs.yml`, runs every example | in `ci.yml`, runs no example (they send mail) | in `ci.yml`, runs every example |
| Required checks | none | `all-green`, `title` | same |
| Timeouts | docs jobs only (20 and 10 min) | docs jobs only (20 min) | docs and live only |
| uv version | `required-version = ">=0.12,<0.13"` | newest | newest |
| uv cache | on, `cache-dependency-glob: uv.lock` | `auto` (on for PR and push) | same |

### 3.3 Hooks

| Hook | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| `default_install_hook_types` | missing, so `prek install` skips `commit-msg` | `pre-commit`, `commit-msg` | same |
| `conventional-pre-commit` types | defaults | defaults, so `deps` fails | the defaults plus `deps` |
| gitleaks, zizmor, actionlint | yes | yes | yes |
| `pre-commit-hooks` | 7 hooks incl. `check-toml` | 6 hooks | 6 hooks |
| TOML | `check-toml` | `tombi-lint`, `tombi-format` | same as Epistole |
| Spelling | `typos` (excludes all `*.toml`) | none | none |
| ruff format and rumdl scope | `files = '\.(md\|qmd)$'` regexes | `types`, which skip `.qmd` | same as Epistole |
| `uv lock --check`, pyrefly | yes | yes | yes, plus `pyrefly-typing` |
| Repo-only | `sync-demo-snippets`, `no-describe`, `no-default-setter`, `no-figures-of-speech` | none | none |
| Syntax | `[[repos.hooks]]` tables | inline tables | inline tables |

Every remote hook is pinned to the same SHA in all three repos, except `typos`, which only dd uses.

### 3.4 Dependency updates

| Concern | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| Dependabot `uv` | none | weekly, grouped, `increase-if-necessary`, 7-day cooldown | same |
| Dependabot actions | weekly Monday, grouped, `chore` | weekly, grouped, `ci` | same |
| Security updates | off | on | on |
| Hook updates | by hand | monthly `prek-update.yml` | monthly, plus `dev` floor rewrite |
| Transitive packages | `uv lock --upgrade` by hand | moved only by a security update (#90, `pyjwt`); 10 packages behind today | not measured |
| Dependabot PRs merged | 2 | 3 | 0 (#129 open and passing since 2026-10-05) |

### 3.5 Release

| Concern | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| Version bump | hand commit `chore(release): X.Y.Z` on `main` | release-please PR | same |
| Changelog | hand-written `CHANGELOG.md` with migrations | release-please; migrations in `user_guide/upgrading.qmd` | same |
| Tag and GitHub release | by hand, lightweight tag | the App creates both | same |
| Tests before publish | yes, 3.12 to 3.14 | no; the release PR passed them | same |
| `pypi` environment | no reviewer, any ref, admin bypass | `v*` tags, owner approves, no admin bypass | same |
| Tag ruleset | none | App and admin only | same |
| TestPyPI | `workflow_dispatch` job, last used 2026-08-11 | none | none |
| Attestations | PEP 740 on PyPI | same | same |

### 3.6 Docs

| Concern | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| Deploy trigger | push to `main` | `release: published` | same as Epistole |
| Examples | every cell runs (pre-render script braces the fences) | none run in the build; `tests/test_examples.py` runs them against `MemoryBackend` | every cell runs against the fake |
| Hidden files in the upload | kept | dropped | dropped |
| HTTPS enforced | yes | no | no |
| Branding | logo, favicon, `theme.css` | same pattern | assets present, but great-docs reads none of them |

### 3.7 GitHub settings

| Setting | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| Merge methods | merge, squash, rebase; squash message `COMMIT_MESSAGES` | squash only, `PR_TITLE` and `PR_BODY` | same as Epistole |
| Auto-merge | off | on | on |
| Rulesets | none | `main`, `version tags` | same, by ID 24126503 and 24126504 |
| `sha_pinning_required` | false | true | true |
| Actions can approve PRs | **true** | false | false |
| CodeQL default setup | off | `actions`, `python`, weekly | same |
| Dependabot alerts and security updates | off | on | on |
| Secret scanning and push protection | on | on | on |
| Private vulnerability reporting | off | off | off |
| OIDC subject | legacy | immutable | immutable |
| Environments | `pypi`, `testpypi`, `github-pages` (branch `main`) | `release` (`main`), `pypi` (`v*`), `github-pages` (`v*`) | Epistole's plus `live` (`main`) |
| Repo-level secrets | none | none | none |

The release App is `ozanozbeker-release` (bot user 335071888), and Integration 5110076 in the tag rulesets is inferred to be it: its bot authored every release since v0.0.5, and creating the tag needs the bypass.
It is private, so `gh api apps/ozanozbeker-release` returns 404, and no file in any repo records the ID.

### 3.8 Measured runs

| Measure | dd | Epistole | oxyscraper |
| --- | --- | --- | --- |
| Successful `ci.yml` run, median / p90 | 1m00s / 1m07s | 1m24s / 1m54s | 1m44s / 2m44s |
| Jobs and summed job time, latest run | 2 jobs, 103 s (push run) | 11 jobs, 450 s | 18 jobs, 840 s |
| Slowest job | `lint` 56 s | Windows 3.13 `test` 64 s | `docs` 107 s |
| Actions cache | 0.62 GB | 5.36 GB (62% on PR refs) | 8.68 GB (62% on PR refs) |
| `release` environment deployment records | n/a | 25 | 57 |
| Failed runs on `main` | 1 (`769bd56`, a direct push that broke pyrefly) | 0 | 1 (go.dev download failed in `lint`) |

Durations are `updatedAt - createdAt` over the last 100 runs per workflow, so they include queue time.
On 2026-09-30 Epistole's macOS `test` jobs took 41 minutes, because `smtplib` called `socket.getfqdn()` 68 times; PR #82 fixed it.
CodeQL default setup starts about as many runs as CI in Epistole and oxyscraper.

## 4. Findings

Each finding names the evidence a reader can re-run.
"Confirmed" means a second agent tried to refute it in a throwaway clone and could not.

### 4.1 Broken

#### F1. Epistole cannot merge a `deps:` PR

Confirmed.
`prek.toml:13-15` passes only `--strict` to `conventional-pre-commit` v4.4.0, whose default types are `build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test` (`format.py:92-106` at `91ab4bf`).
`pr-title.yml` runs that hook, and the `main` ruleset requires `title`.
A sandbox run on `deps: raise the msal floor` exits 1. oxyscraper found and fixed it in #91 (`4a232ab`).
The full list is needed: `["--strict", "deps"]` alone keeps only `feat`, `fix` and `deps` (`format.py:113-117`), so release-please's own `chore(main): release 0.0.7` then fails.
With the full list, `feat!:`, `feat(x)!:` and a `BREAKING CHANGE:` footer after a blank line still pass, and `fixup!` still fails.

#### F2. dd's `latest` job will fail on its 2026-10-12 run

polars 2.0.0 (2026-10-06) removed `scan_parquet(rechunk=)`, and `dagster_polars/io_managers/parquet.py:185` still passes it.
In a sandbox, `uv sync --upgrade` then pytest gives 10 failures on 3.14, all through the `dagster-polars` IO manager. dd's own `src/` never calls `scan_parquet`.

### 4.2 Checks that check nothing

#### F3. No hook reads Epistole's `.qmd` pages

Confirmed.
`prek util identify user_guide/sending.qmd` prints `quarto, text` (prek `tags.rs:883-884`).
The rumdl hook selects `types = ["markdown"]`, and ruff-format `types_or` without `quarto`.
`rumdl check user_guide/` passes today, so no page breaks a rule yet.
Trap: adding `quarto` to ruff-format without `extension = { qmd = "markdown" }` in `ruff.toml` makes ruff parse the pages as Python, and all 5 fail with `invalid-syntax`. ruff 0.16.9 needs no `preview = true` for this.

#### F4. gitleaks and `check-added-large-files` pass in CI without reading anything

Confirmed. gitleaks' hook entry is `gitleaks git --pre-commit --redact --staged --verbose`, and CI stages nothing: it prints `0 commits scanned`. prek's large-files hook keeps only staged additions unless `--enforce-all` is set (`check_added_large_files.rs:35-48`).
A clone with a fake `ghp_` token and a 684 KB file committed passes both.
GitHub push protection covers provider token patterns only; non-provider patterns, such as a private key, need an organization on GitHub Team.
`ci.yml:68` says CI "runs every hook on every file", which is literally true and checks nothing for these two.

#### F5. zizmor runs offline in CI

Confirmed.
Without `GH_TOKEN`, `GITHUB_TOKEN` or `ZIZMOR_GITHUB_TOKEN`, zizmor 1.30.1 skips `impostor-commit`, `known-vulnerable-actions`, `ref-confusion`, `stale-action-refs` and `ref-version-mismatch`. zizmor's docs mark `ref-version-mismatch` as offline, but the source skips it (`ref_version_mismatch.rs:237-246`).
That audit compares each SHA with its `# vX.Y.Z` comment, and Dependabot's actions PRs change both.
Run by hand with a token, zizmor reports no findings.
Passing `${{ github.token }}` adds no capability on `pull_request`, because the PR already controls `ci.yml` and the token is `contents: read`.
The cost: a GitHub API outage now fails `lint`.

#### F6. `check-merge-conflict` passes in CI without checking

Without `--assume-in-merge`, it checks only while a merge or rebase is in progress (prek built-in hooks docs).

### 4.3 Out of date

#### F7. Python 3.15 has not joined

Confirmed.
The `v3.15.0` tag is dated 2026-10-09.
`CONTRIBUTING.md:136-137` says a version joins at its final release, and `ci.yml:21`, `pyproject.toml:17-18` stop at 3.14.
Epistole's suite passes on 3.15.0: 1447 passed, 13 skipped, no warnings, on macOS and Linux.
Every runtime and dev package has a 3.15 wheel on all three CI platforms.
Windows on 3.15 has not run anywhere yet.
`next-python` has nothing newer to run: 3.16.0a1 is due 2026-10-13 and 3.16.0b1 on 2027-05-04 (PEP 826), and uv cannot install 3.16 today.
None of FastAPI, Pydantic, pytest or attrs runs alphas; pytest and attrs add a version at beta 1.

#### F8. CI uses the newest uv, with no cooldown

No `setup-uv` step sets `version`, and Epistole has no `[tool.uv]`, so CI installed uv 0.13.0 on 2026-10-11, two days after its release.
The `uv_build>=0.12.10,<0.13.0` cap is not a breakage: uv 0.13.0 counts 0.12.24 as compatible and builds with its bundled backend, printing one warning (`metadata.rs:37-39`).
Dependabot's uv ecosystem widens `[build-system] requires`, so Epistole should get `<0.14.0` in its uv group PR after 2026-10-16.
Dependabot never bumps `[tool.uv] required-version` (dependabot-core #14376 open), and an exact `required-version` breaks Dependabot's own `uv lock` (#13199).
Once dd adds a Dependabot `uv` entry, its `>=0.12,<0.13` works only while Dependabot runs uv 0.12.x (0.12.19 today).

#### F9. Quarto is pinned by hand

Both workflows pin 1.10.18, and 1.10.19 came out 2026-10-06.
Dependabot reads `uses:` only, not `with:` inputs, so nothing bumps it.

#### F10. dd's `typos` pin is out of date

dd pins `typos` at v1.50.2, although v1.50.3 is past the 7-day cooldown, and dd has no hook-update workflow.
`prek update` would move it to `typos-dict-v0.14.2`, because the repo tags two series; `[update] exclude_tags = ["typos-dict-*"]` prevents that.

### 4.4 Docs that disagree with the files

#### F11. Dependabot runs on Wednesdays

`CONTRIBUTING.md:52` says Mondays.
GitHub's reference says `weekly` defaults to Monday.
Inference from three repos: with no `day`, the slot follows the weekday the config merged, and Epistole's merged on Wednesday 2026-09-30.

#### F12. `CONTRIBUTING.md:5` undercounts the departures

It says "Epistole departs from it in one place".
At the copy point it already ran no docs examples.
Against oxyscraper's head it also lacks the coverage job, the `deps` type, the dev-floor step, the `live` marker and `pyrefly-typing`.

#### F13. `CONTRIBUTING.md:118` overclaims what `lowest` proves

It says each floor in `pyproject.toml` is as low as the `lowest` job proves.
`lowest` installs the `dev` floors and runs only pytest, so it proves the runtime floors and the floors of packages the tests import (`pytest`, `css-inline`, `inscriptis`), but not the tool floors (`prek`, `pyrefly`, `ruff`, `rumdl`, `tombi`). oxyscraper's wording, "runtime floor", is correct.

#### F14. Epistole's `CLAUDE.md` Writing section contains dd's examples

They are `quarantine`, `dd.asset` and "a member is Dataframely's", at `:52`, `:61` and `:64`.

#### F15. `rumdl.toml:10` excludes a file that does not exist

The file is `LICENSE`, not `LICENSE.md`.

#### F16. dd's `typos.toml` excludes every `*.toml`

The commit that added it says it ignores only rule-code shapes.
With `--isolated`, typos finds two words: `CPY` and `als`.
`extend-words` for those two replaces the exclusion.

#### F17. dd's `ruff.toml` comment on `preview = true` is stale

ruff 0.16.8 formats `.qmd` chunks without it, so it now only restyles Python (153 lines, measured in `865a58a`).

### 4.5 Security and settings

#### F18. dd publishes to PyPI with no approval

The `pypi` environment has no reviewer, no branch or tag policy, and `can_admins_bypass: true`.
9 of its 10 release runs finished in under two minutes.
`testpypi` is the same.

#### F19. dd's `main` has no protection

No ruleset and no branch protection; 53 of 56 commits since 0.7.0 went to `main` without a PR.
One of them (`769bd56`, a tool bump) broke pyrefly on `main`.
Actions can approve PRs, and `sha_pinning_required` is false, although every dd workflow already pins.

#### F20. Dependabot alerts do not read dd's `uv.lock`

GitHub's dependency graph reads `uv.lock` only through a Dependabot `uv` entry: Epistole's SBOM lists 131 PyPI packages, and dd's SBOM endpoint returns 404.
Alerts and security updates are also off.

#### F21. HTTPS is not enforced on Epistole's and oxyscraper's Pages sites

`http://ozanozbeker.com/epistole/` returns 200; dd's returns 301.
The certificate is already approved, so the PUT needs no wait.

#### F22. `.well-known/` never reaches Epistole's site

great-docs 0.17.0 writes `.well-known/agent-skills/` by default (`skill.well_known: true`), and `actions/upload-pages-artifact` excludes dotfiles unless `include-hidden-files: true`.
Epistole's `skills.html` tells readers to run `npx skills add https://ozanozbeker.com/epistole/`, whose discovery file returns 404. great-docs' own workflow template sets the input.

#### F23. A rejected `pypi` approval still deploys the docs

`docs.yml` and `release.yml` both start on `release: published`, so the site can document a version that never reached PyPI.

#### F24. Nothing checks that a release tag is on `main`

The `version tags` ruleset lets the App tag any commit, and `github-pages` has no reviewer.
`git merge-base --is-ancestor "$GITHUB_SHA" origin/main` before the build closes this.
A release checkout with `fetch-depth: 0` fetches every branch, so `origin/main` exists (docs run 36751999699).

#### F25. `prek-update.yml` runs unpinned code in the job that holds the App key

The job mints the App token first, then runs `prek update`, `uv lock` (which can build an sdist and run its backend) and an inline script, then opens the PR.
The key mints tokens for every repo the App is installed on.
Reordering the steps does not help, because a process started by an earlier step can read a later step's memory on the same runner.

#### F26. oxyscraper's `coverage` job holds `id-token: write` while it runs PR code

A Dependabot PR gets a real OIDC token there (run 37258798705).
PyPI rejects it, because the trusted publisher names `release.yml` and `pypi`, so only Codecov accepts it.
The same run shows Codecov's wrapper printing "CLI integrity verified" after `Could not verify signature` and `Could not verify SHASUM`.

#### F27. Private vulnerability reporting is off in all three

It is free on public repos.
Non-provider secret patterns and validity checks need an organization on GitHub Team, so they are not options.

#### F28. `prevent_self_review: false` is right, for a different reason than recorded

GitHub records the App's bot as the initiator of a release run, so by the docs' wording self-review should not block the App path (untested).
It would block the recovery path: a release published by hand makes the maintainer the initiator, and nobody else can approve.

### 4.6 Cost and noise

#### F29. Each release-please run writes a deployment record

Epistole has 25 and oxyscraper 57, against 5 and 2 for `pypi`.
GitHub added `environment: {name: release, deployment: false}` on 2026-03-19; it keeps the secrets and the branch policy and creates no record. actionlint 1.7.12 and zizmor 1.30.1 accept it.

#### F30. The uv cache costs storage and saves no time

Every dependency is a pre-built wheel, so `uv cache prune --ci` leaves 28 KB of 145 MB.
A miss downloads all 35 test packages in 0.24 s.
An all-hit run and an all-miss run take the same time.
Release-please and Dependabot PRs change the lock, so they always miss and write about 10 entries of about 60 MB to their PR ref, which no other ref can restore.

#### F31. The `lint` job downloads Go on every run

prek builds gitleaks and actionlint from source and finds no Go on the runner, so it fetches about 70 MB from go.dev.
That download failed once and failed a push run on oxyscraper's `main` (run 37021169828).
Caching `~/.cache/prek/hooks` and `~/.cache/prek/repos` (62 MB) removes it; prek-action adds nothing over `actions/cache` and installs an unlocked prek.

#### F32. Most jobs have no timeout

They inherit 360 minutes, so a hung job holds auto-merge for 6 hours.
Since PR #82 the longest measured job takes 107 s; before it, macOS `test` jobs ran 41 minutes.

#### F33. Dependabot version updates move only declared dependencies

`uv lock --upgrade --exclude-newer '7 days'` moves 10 transitive packages in Epistole's lock, `pyjwt` 2.15.0 to 2.15.1 among them, which `msal` uses at runtime.
Users install the newest transitive releases; CI never tests them.

#### F34. oxyscraper's dev-floor script is wrong in three measured ways

`text.replace` rewrites every copy of a requirement string, so a `dev` entry that matches a runtime entry raises the runtime floor in a `chore:` PR.
A PEP 735 `{include-group = ...}` entry crashes it with `TypeError`, and a dynamic version crashes it with `KeyError`.
It has never run on a schedule: its only run predates it.

### 4.7 What already works

- Every action SHA matches its version comment in all three repos, and Epistole and oxyscraper enforce SHA pins with the repo setting.
- Epistole's and oxyscraper's workflows start with `permissions: {}`, and every checkout sets `persist-credentials: false`.
- `pr-title.yml` passes the title through `env`, so a title cannot inject shell.
- zizmor with a token reports nothing on Epistole.
- PyPI provenance for Epistole 0.0.6 names `release.yml` and environment `pypi`; all three packages carry PEP 740 attestations.
- The rulesets pin both required checks to integration 15368 (GitHub Actions), so another App cannot post a passing status.
- release-please's `uv.lock` JSONPath works, including on dd's workspace lock.
- The 40 most recent oxyscraper runs and the last 100 Epistole runs all succeeded.

### 4.8 Claims that verification refuted

- "uv 0.13 breaks the build because of the `uv_build` cap": refuted, it warns and builds the same wheel.
- "dd needs `bootstrap-sha` or `last-release-sha` for release-please": refuted. release-please finds `v0.9.0` through GitHub releases even with a lightweight tag, so the manifest `{".": "0.9.0"}` is enough.
- "dd's executing docs need push-to-main deploys": refuted.
  Every cell already runs on each PR.
- "`enable-cache: false` on the release jobs prevents cache poisoning": redundant. setup-uv v10's `auto` already turns caching off on `release` and tag pushes, and a tag run cannot restore a PR-ref cache.

## 5. The unified standard

Three independent designs (minimal, drift-proof, secure) were judged against the findings.
The rule for a tie: keep what Epistole has unless it is broken, checks nothing, or has a measured cost; add a piece only when someone measured what it catches.

IDs: `W` where the standard is kept, `P` pull requests and rulesets, `C` CI, `H` hooks, `U` updates, `R` release, `S` site and live tests, `G` GitHub settings.
`F` numbers are the findings in section 4, and `D` numbers are oxyscraper's decisions in [Appendix A](#appendix-a-the-decision-record-from-oxyscraper).

### 5.1 Where the standard is kept

| # | Decision | Why |
| --- | --- | --- |
| W1 | Epistole's `CONTRIBUTING.md` holds the standard. Its last section, "Epistole's departures", holds what only Epistole does. | `CLAUDE.md` already imports it into every session, and one copy of the prose cannot differ from itself. |
| W2 | `docs/adr/0021-epistole-holds-the-release-standard-for-every-package.md` records the decision. This report moves to `docs/research/` as its evidence, with the oxyscraper record in its appendices. | oxyscraper#22 is the record today, and deleting the repo deletes it. |
| W3 | oxyscraper's `release-practices.md`, `ci-and-docs-practices.md` and `httpx2.md` move to Epistole's `docs/research/` verbatim. | Both repos use the same `rumdl.toml`, so they pass unchanged. |
| W4 | Each package copies the files. No reusable workflow, template tool or composite action. | See 5.2. |
| W5 | A package's `CONTRIBUTING.md` records the Epistole commit it copied and lists its departures, nothing else. Its `CLAUDE.md` imports `@~/Dev/epistole/CONTRIBUTING.md`, then `@CONTRIBUTING.md`. | An agent in the package reads the one copy of the rules, and with the SHA, catching up takes one `git diff`. |
| W6 | Catching up is by hand: `git -C ~/Dev/epistole diff <sha> HEAD -- <standard files>`, port, update the SHA. No CI job yet. | With one follower that may stay in maintenance, a required check would fail every Dependabot and release PR there after each Epistole change. Add the check when a third package adopts. |
| W7 | A standard change merges in Epistole first, then as a same-titled PR in each full follower. | Epistole missed 9 CI commits because no order existed. |
| W8 | `CONTRIBUTING.md` lists each package as "full" or "maintenance". A maintenance repo keeps only the security floor and owes no port PRs. | It states which repos W7 covers. |

### 5.2 Ways to share the standard that were rejected

| Option | Why not |
| --- | --- |
| copier template with `copier update` | The template is a third copy to keep. `copier update` checks out the newest PEP 440 tag, and Epistole's tags are package releases, so every update needs `--vcs-ref=HEAD`. Dependabot reads only `*.yml` and `*.yaml` files in `.github/workflows`, so pins inside `ci.yml.jinja` never move. 16 `${{ }}` expressions need Jinja escaping. |
| Reusable workflows with `workflow_call` | PyPI rejects trusted publishing from a reusable workflow, so the publish job stays local. A called job's check is named `<caller> / <called>`, so every ruleset changes. Dependabot bumps the reference to Epistole's newest tag, which is a package release. Of the 7 oxyscraper commits to generic shared files that Epistole missed, a reusable workflow would have carried the workflow half of 4 and none of the `prek.toml` changes, including the `deps` fix. |
| Composite action | One more pin per job to save about 6 lines; it covers none of the missed changes. |
| A required `standard` CI job that diffs shared files against Epistole | It works: a 119-line stdlib prototype passed at Epistole's copy point and failed at oxyscraper#83 and #91, the first changes Epistole missed. It is the right tool for three or more full followers. With one, it costs more than it catches. |

### 5.3 Commits, pull requests and rulesets

| # | Decision | Source | Why |
| --- | --- | --- | --- |
| P1 | 12 types. `feat`, `fix`, `perf`, `docs`, `deps`, `revert` are visible and bump the patch below 1.0; the rest are hidden; `!` or a `BREAKING CHANGE:` footer bumps the minor. | all | release-please 17.6.0 measured these bumps (D1). |
| P2 | `conventional-pre-commit` args: `--strict`, the 11 defaults and `deps`. | oxyscraper | F1. |
| P3 | `pr-title.yml` stays its own workflow, on `opened`, `edited`, `reopened`, `synchronize`. No concurrency. | Epistole | In `ci.yml` it would rerun the matrix on every body edit release-please makes. The duplicate run costs 18 s. |
| P4 | Squash only, `PR_TITLE` and `PR_BODY`, auto-merge on, head branches deleted. | Epistole | dd's `COMMIT_MESSAGES` drops a `BREAKING CHANGE:` footer written in the body. |
| P5 | Turn on auto-merge only with `gh pr merge --auto --squash`. | new trap | The web form saves the commit title, and a later title fix never reaches it (plausible, not tested). |
| P6 | `main` ruleset: PR with 0 approvals, squash only, `all-green` and `title` from integration 15368, no up-to-date rule, no force push or deletion, admin bypass for PRs only. | Epistole | Strict mode stalls auto-merge; merge queues need an organization. |
| P7 | `version tags` ruleset: `v*` create, update and delete only by the admin and Integration 5110076. Write the ID into `CONTRIBUTING.md`. | Epistole | PyPI recommends tag protection for tag-triggered publishing (D37). |

### 5.4 CI

| # | Decision | Source | Why |
| --- | --- | --- | --- |
| C1 | `test`: Ubuntu, macOS, Windows on every supported CPython, `uv sync --locked --no-editable`, `fail-fast: false`. pytest keeps `filterwarnings = ["error"]`, `xfail_strict`, `--strict-config`, `--strict-markers`, `--import-mode=importlib`. Every extra is installed in `test`, `next-python` and `lowest`, through `--all-extras` or a self-reference in `dev` as Epistole's `pyproject.toml:39` does. | Epistole | Windows and macOS found three bugs the Linux runs missed (`epistole#75`). Installing every extra lets `lowest` test each extra's floors. |
| C2 | 3.15 joins `test` and the classifiers now. | new | F7. |
| C3 | `next-python` runs the newest CPython that has reached beta 1. At a final release, the version joins `test` and `next-python` stays on it until the next beta 1. | new | Nothing newer exists to run, and the major libraries add a version at beta 1. The duplicate job costs 29 s for 7 months. |
| C4 | Remove `continue-on-error` from `next-python`. | new | `allowed-failures: next-python` already keeps `all-green` passing, and the key only hides the failure on the run page. |
| C5 | `lowest`: `uv sync --resolution lowest-direct --no-editable --exclude-newer '7 days'`, Python from `.python-version`. | Epistole, plus flag | `lowest-direct` resolves transitive packages to their newest release, so this is the one job that runs unlocked upstream code; the flag applies the cooldown. 1447 passed with it. |
| C6 | 100% line coverage: `source_pkgs`, `exclude_also = ["if TYPE_CHECKING:"]`, `fail_under = 100`, `show_missing = true` in `pyproject.toml`. | oxyscraper tables | The threshold in config makes a local `coverage report` fail the same way as CI. Epistole is 6 lines short: 2 tests and 2 pragmas close it. |
| C7 | Coverage runs inside `lowest`: `coverage run -m pytest`, then `coverage report`. | new | `lowest` already runs the suite once on Ubuntu, and the floors reach 100% (1450 passed). Ceiling: code only a newer Python reaches needs a pragma. |
| C8 | No Codecov, and no `id-token: write` in `ci.yml`. | new | At 100% its comment always reads "covered". F26. |
| C9 | No branch coverage, no pyrefly at the floors. | new | Branch coverage found one gap and needs pragmas on exhaustive `match` statements pyrefly already proves; pyrefly at the floors found 0 errors. |
| C10 | `lint`: `prek run --all-files --show-diff-on-failure` with `GH_TOKEN: ${{ github.token }}` and `SKIP: gitleaks,check-added-large-files`. | Epistole, plus F5, F4 | The two skipped hooks read staged changes only. |
| C11 | A manual-stage `gitleaks-ci` hook (`gitleaks git --redact --verbose`, `--log-opts=HEAD^1..HEAD`), checkout `fetch-depth: 0`, and a CI step that runs `git rev-parse --verify --quiet HEAD^1` first. | new | It caught a token that a later commit in the same PR removed. On a shallow clone gitleaks exits 0 after `git log` fails, so the parent check comes first. |
| C12 | No prek cache for now. Add the `actions/cache` step in [6.3](#63-snippets) after a second go.dev failure. | new | One failure in about 200 runs, fixed by a rerun; `lint` takes 45 s against 64 s for Windows `test`. |
| C13 | `docs` job builds the site on every PR. | Epistole | A broken build fails the PR, not the release. |
| C14 | `all-green` via `re-actors/alls-green`, `if: always()`, every job in `needs`. `ci.yml` cancels superseded PR runs only. | Epistole | Adding a job never changes the ruleset. |
| C15 | `timeout-minutes: 15` on every job, 20 on the docs builds. | new | F32. |
| C16 | `enable-cache: false` on every `setup-uv` step; no `cache-suffix`. | new | F30. |
| C17 | `version: latest-known` on every `setup-uv` step; no `[tool.uv] required-version`. | new | It installs the newest uv whose checksum the pinned setup-uv bundles, so uv moves when Dependabot moves setup-uv, after the cooldown. Until setup-uv v10.3.0 merges, CI runs uv 0.12.17, which accepts Epistole's lock. |

### 5.5 Hooks

| # | Decision | Source | Why |
| --- | --- | --- | --- |
| H1 | `default_install_hook_types = ["pre-commit", "commit-msg"]`, `default_stages = ["pre-commit"]`, `default_language_version.python` at the floor. | Epistole | dd skips the `commit-msg` hook without the first. |
| H2 | `repo = "builtin"` replaces the `pre-commit-hooks` repo: `trailing-whitespace`, `end-of-file-fixer`, `check-merge-conflict` with `--assume-in-merge`, `check-yaml`, `check-case-conflict`, `check-added-large-files`, `detect-private-key`. | new | No clone and no pin. `detect-private-key` reads every tracked file, which covers the PEM shape push protection misses. Both trees pass it. |
| H3 | `check-added-large-files` keeps its default arguments and checks locally only. | new | `--enforce-all` fails dd's 656 KB `uv.lock`. |
| H4 | `"quarto"` in ruff-format's `types_or`; rumdl's `types` becomes `types_or = ["markdown", "quarto"]`; `extension = { qmd = "markdown" }` in `ruff.toml`; all in one PR. | new | F3. `types_or` is simpler than dd's regex and keeps shebang detection. With `flavor = "quarto"`, rumdl's MD078 then wants `#| label:` on every executable chunk. |
| H5 | Keep `tombi-lint` and `tombi-format`; no `check-toml`. | Epistole | tombi passes all 8 of dd's TOML files unchanged and adds formatting and schema checks. |
| H6 | zizmor and actionlint as remote hooks; local `ruff-check`, `ruff-format`, `rumdl`, `uv-lock`, `pyrefly`; no pytest hook. | all | Tests run in CI (D21). |
| H7 | `typos`, `no-figures-of-speech`, `sync-demo-snippets`, the two pygrep bans and `pyrefly-typing` stay in the repo that needs them. | dd, oxyscraper | typos finds 33 hits in Epistole, 1 real; dd's figures regex matches 457 Epistole domain words such as `refused` and `consent`. A repo with `typos` sets `[update] exclude_tags = ["typos-dict-*"]` in `prek.toml`, or `prek update` pins the dictionary tags. |
| H8 | Epistole's inline-table syntax; a follower appends its own hooks after the standard's. | Epistole | A port from Epistole then applies as a patch. |
| H9 | Delete ruff's `target-version`. | new | ruff 0.16.9 reads it from `requires-python` (measured), and the end-of-life checklist loses one edit. |

### 5.6 Dependency updates

| # | Decision | Source | Why |
| --- | --- | --- | --- |
| U1 | Dependabot: `uv` and `github-actions`, weekly, `day: monday`, 7-day cooldown, `increase-if-necessary` for uv, one group each, prefixes `chore` and `ci`. | Epistole, plus day | Hidden prefixes start no release (D26); F11. |
| U2 | Dependabot alerts and security updates on; the `uv` entry belongs to the security floor. | Epistole | F20. |
| U3 | Monthly `prek-update.yml`: `prek update --freeze --cooldown-days 7`, then `uv lock --upgrade --exclude-newer '7 days'` and a second `uv lock`. Title `chore: update prek hooks and uv.lock`. | new | F33. The first lock writes `exclude-newer-span = "P7D"` into `uv.lock`, and without the second lock `uv lock --check` fails. |
| U4 | `prek-update.yml` runs in two jobs: `update` holds no secret, runs prek and uv, and uploads `prek.toml` and `uv.lock`; `pr` runs in `release` with `deployment: false`, mints the token and opens the PR with pinned actions only. | new | F25. |
| U5 | Runtime floors as low as `lowest` proves, raised only in a `deps:` commit. `dev` floors are the newest release at least 7 days old, raised by hand in a `chore:` commit with `uv add --dev "<name>>=<locked>"` and `tombi format`. No floor-rewrite script. `CONTRIBUTING.md` says "runtime floor". | Epistole; maintainer preference of 2026-10-01 | F13, F34. Dev tools never reach users, so a current floor costs nothing. Dropping dev floors is wrong: an unbounded `pytest` under `lowest-direct` resolves to an ancient release. |
| U6 | Quarto stays pinned by hand. | Epistole | F9. `quarto-cli` on PyPI ships only an sdist that downloads the binary. |

### 5.7 Release

| # | Decision | Source | Why |
| --- | --- | --- | --- |
| R1 | release-please: `release-type: python` in the config file only, `include-component-in-tag: false`, both pre-major options, the `uv.lock` extra file with `@.name.value`, 12 sections. `bootstrap-sha` only for a repo with no release. | Epistole | D1 to D7, D33, D34. |
| R2 | `environment: {name: release, deployment: false}` in `release-please.yml` and the `pr` job of `prek-update.yml`. | new | F29. |
| R3 | One App with Contents, Issues and Pull requests read and write and Metadata read, nothing else. Each repo gets its own key at setup; no `.pem` stays on disk. | new | A key reaches every installation, so the App must hold no Workflows or Administration permission. Separate keys let one repo's key be revoked alone. |
| R4 | `release.yml`: `build` (`contents: read`, `uv build`, `py.typed` check) and `pypi` (`id-token: write` only). No tests. PEP 740 attestations from the PyPA action. | Epistole | D35. |
| R5 | `build` checks out with `fetch-depth: 0` and runs `git merge-base --is-ancestor "$GITHUB_SHA" origin/main` first. | new | F24. Not yet run in Actions. |
| R6 | `skip-existing: true` on `pypa/gh-action-pypi-publish`. | new | A rerun after a partial upload otherwise fails on the first file. Not measured. |
| R7 | `pypi`: `v*` tags, owner approves, self-review allowed, admin bypass off. `release`: `main`. `github-pages`: `v*`. | Epistole | F28. |
| R8 | No TestPyPI, no draft releases. | oxyscraper | D38, D39. |
| R9 | Before approving `pypi`, read `git log <previous tag>..<new tag>`. | new | The ruleset needs no review, so the approval is the last human check. |

### 5.8 Docs and live tests

| # | Decision | Source | Why |
| --- | --- | --- | --- |
| S1 | great-docs on GitHub Pages at `https://ozanozbeker.com/<repo>/`. | all | |
| S2 | `release.yml` gains `site` (`needs: pypi`) and `pages` (`needs: site`, environment `github-pages`); delete `docs.yml`. | new | F23. `site` waits for `pypi` because `upload-pages-artifact` keeps its artifact for 1 day, so an approval given after a day would leave `pages` nothing to deploy. |
| S3 | `include-hidden-files: true` on the Pages upload. | dd | F22. |
| S4 | HTTPS enforced on every project site. | dd | F21. |
| S5 | Every example runs at build time unless it has side effects; then a test runs it against a fake. Migrations go in `user_guide/upgrading.qmd` under the next minor. | dd, oxyscraper, Epistole | Epistole's examples send mail. oxyscraper's pages used a hidden setup cell that enters the fake with `ExitStack().enter_context(...)`, so the build still ran every page (oxy#56). |
| S6 | The live-test module stays out of `CONTRIBUTING.md`. [Appendix E](#appendix-e-oxyscraper-files-kept-verbatim) keeps `live.yml`, and D48 keeps the reasons. | new | No repo uses it once oxyscraper is deleted. Epistole's Gmail consent expires every 7 days, and each secret grants a whole mailbox. |

A package adopts the live module when it has a credential that does not expire on a schedule and an upstream that changes often.
Then it adopts four parts together: a `live` marker, `-m "not live"` in `addopts`, a `live` environment limited to `main`, and `live.yml` with `deployment: false`, a `concurrency` group and `--tb=short`.
`--tb=short` matters because GitHub's log redaction misses derived values, such as the Base64 form of an SMTP password.
The live test module overrides the autouse fake fixture with a no-op, so its sessions reach the real service, and fails, not skips, when a credential is missing.
Locally it runs with `uv run --env-file .env pytest -m live`.
An optional folder outside the repo, such as oxyscraper's `OXY_CAPTURES`, can keep every exchange; it stays out of the repo and CI because the captures hold account details.

### 5.9 GitHub settings

| # | Decision | Why |
| --- | --- | --- |
| G1 | `CONTRIBUTING.md` gains "Repository settings" ([Appendix C](#appendix-c-repository-settings-and-the-ruleset-json)). | The only written list is in oxyscraper. |
| G2 | `sha_pinning_required`, read-only default token, Actions cannot approve PRs. | dd allows approval today. |
| G3 | Dependabot alerts and security updates, CodeQL default setup for `actions` and `python`, private vulnerability reporting, secret scanning with push protection. | Each is one call. |
| G4 | Leave fork PR approval at `first_time_contributors`, and dd's OIDC subject as it is. | Changing the subject changes the claim PyPI reads. |

### 5.10 Where the designs disagreed

The judge's pick is in the tables above; the other choice is here so it can be revisited.

- **Drift check (W6).**
  The drift-proof design wanted the required `standard` job now.
  Picked: by hand until a third package adopts.
- **Tag ruleset (P7).**
  The minimal design dropped it.
  Kept: it costs nothing to keep.
- **Coverage placement (C7).**
  Two designs wanted a separate job.
  Picked: inside `lowest`, to run the suite once fewer.
- **prek cache (C12).**
  Two designs added `actions/cache`.
  Picked: none until a second failure.
- **gitleaks in CI (C11).**
  The minimal design skipped it.
  Kept: apart from `detect-private-key` for PEM keys, it is the only CI check on a non-provider secret, and the only one that finds a secret a later commit in the PR removed.
- **`--enforce-all` (H3).**
  Two designs added it.
  Dropped: it fails dd's lock.
- **TOML (H5).**
  The minimal design used the builtin `check-toml`.
  Kept tombi.
- **`prek-update.yml` split (U4).**
  The minimal design only reordered steps.
  Picked: two jobs.
- **Docs deploy (S2).**
  Two designs kept `docs.yml`.
  Picked: inside `release.yml` after `pypi`.
- **`continue-on-error` (C4).**
  Two designs kept it.
  Picked: remove.

## 6. Plan for Epistole

Every PR except 8 touches a workflow, `pyproject.toml` or a linter config, so each needs the maintainer's confirmation before it opens.

### 6.1 Settings, no PR

1. `gh api -X PUT repos/ozanozbeker/epistole/pages -F https_enforced=true`
2. `gh api -X PUT repos/ozanozbeker/epistole/private-vulnerability-reporting`
3. On pypi.org, confirm Epistole's trusted publisher names environment `pypi`.
   PR 4 adds a second `id-token: write` job (`pages`) to `release.yml`, and only the environment keeps that job from publishing.
4. On the App's settings page, confirm the permissions in R3 and note the App ID.

### 6.2 Pull requests, in order

| # | Title | Files | Notes |
| --- | --- | --- | --- |
| 1 | `ci: accept deps in commit titles` | `prek.toml` (P2) | First, because no floor can rise until it merges. The PR passes its own `title` check, because `pr-title.yml` reads the PR's `prek.toml`. |
| 2 | `ci: make every hook check what CI runs it on` | `prek.toml` (H2, C11, H4); `ruff.toml` (H4, H9); `rumdl.toml` (F15); `ci.yml` `lint` (C10, C11, `fetch-depth: 0`); `CONTRIBUTING.md:139` (drop ruff's `target-version`) | The builtin set and the `gitleaks-ci` diff each passed alone, not together; run every hook once on the combined change. |
| 3 | `feat: support Python 3.15` | `ci.yml` matrix; `pyproject.toml` classifier; `CONTRIBUTING.md` `next-python` rule (C3) | The first Windows run on 3.15. |
| 4 | `ci: deploy the site after the PyPI upload` | `release.yml` (R5, R6, S2, S3, C15 to C17); delete `docs.yml`; `CONTRIBUTING.md` Releasing, When something fails, Traps | Step 6.1.3 first. `.well-known/` reaches the site at the next release. |
| 5 | `ci: pin uv, drop the uv cache and bound every job` | `ci.yml` (C4, C5, C15 to C17, both `cache-suffix` lines); `pr-title.yml`; `release-please.yml` (R2, C15); `dependabot.yml` (U1 day); `CONTRIBUTING.md:139` (drop the `lowest` job's Python) | Old caches expire after 7 days unused. |
| 6 | `ci: keep the App key out of the update job and refresh uv.lock` | `prek-update.yml` (U3, U4, R2, C15, C17); `CONTRIBUTING.md:53`, `:122` (new title, monthly lock refresh) | After merging, run `gh workflow run prek-update.yml` and check that `gh api "repos/ozanozbeker/epistole/deployments?environment=release"` stops growing. |
| 7 | `test: require 100% line coverage` | `pyproject.toml` (`coverage` in `dev`, C6 tables); `uv.lock`; two tests (`<img =SRC\r="/src=data:...">` and `a<br><br>b`); pragmas at `src/epistole/_message.py:637` and `_tokens.py:152`; `ci.yml` `lowest` (C7) | |
| 8 | `docs: make CONTRIBUTING.md the release standard` | `CONTRIBUTING.md` (lines 3-6, "Adopting the standard", "Repository settings" with App ID 5110076, the package list, the P5 and R9 traps, "runtime floor", "Epistole's departures"); `CLAUDE.md` (F14); ADR 0021; this report into `docs/research/`; the two oxyscraper research notes | Prose only. |

Nothing else needs a hand edit: Dependabot widens `uv_build` to `<0.14.0` in an ordinary uv group PR after 2026-10-16.

### 6.3 Snippets

`prek.toml`, the commit types (P2):

```toml
hooks = [
  {
    id = "conventional-pre-commit",
    stages = ["commit-msg"],
    # Listing types replaces the hook's defaults, so the list repeats them and adds `deps`, which CONTRIBUTING.md uses for a floor.
    args = ["--strict", "build", "chore", "ci", "deps", "docs", "feat", "fix", "perf", "refactor", "revert", "style", "test"],
  },
]
```

`prek.toml`, gitleaks for CI (C11):

```toml
hooks = [
  { id = "gitleaks" },
  # `gitleaks` scans staged changes and CI stages nothing, so CI runs this copy on the commits HEAD adds to its first parent.
  { id = "gitleaks", alias = "gitleaks-ci", stages = ["manual"], entry = "gitleaks git --redact --verbose", args = ["--log-opts=HEAD^1..HEAD"] },
]
```

`prek.toml`, the built-in hooks (H2):

```toml
[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  # Without the flag, the hook checks only while a merge is in progress, so CI checked nothing.
  { id = "check-merge-conflict", args = ["--assume-in-merge"] },
  { id = "check-yaml" },
  { id = "check-case-conflict" },
  { id = "check-added-large-files" },
  { id = "detect-private-key" },
]
```

`prek.toml` and `ruff.toml`, the `.qmd` pages (H4):

```toml
# prek.toml, ruff-format: replaces its types_or line
types_or = ["python", "pyi", "jupyter", "markdown", "quarto"],
# prek.toml, rumdl: replaces `types = ["markdown"],`, because `types` requires every tag and a .qmd page has no `markdown` tag
types_or = ["markdown", "quarto"],
```

```toml
# ruff.toml, top level. Without it, ruff parses a .qmd page as Python.
extension = { qmd = "markdown" }
```

`ci.yml`, the `lint` job (C10, C11):

```yaml
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          # `gitleaks-ci` reads every commit the pull request adds.
          fetch-depth: 0
          persist-credentials: false
      # ...
      - run: uv run --no-sync prek run --all-files --show-diff-on-failure
        env:
          # zizmor skips its online audits without a token.
          GH_TOKEN: ${{ github.token }}
          # Both read staged changes only, and CI stages nothing.
          SKIP: gitleaks,check-added-large-files
      # gitleaks exits 0 when `git log` fails on a shallow clone, so check the parent exists first.
      - run: |
          git rev-parse --verify --quiet HEAD^1
          uv run --no-sync prek run --all-files --hook-stage manual gitleaks-ci
```

Every `setup-uv` step (C16, C17):

```yaml
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          # uv follows setup-uv, which Dependabot bumps after the cooldown.
          version: latest-known
          # Every dependency is a pre-built wheel, so a cache hit saves nothing.
          enable-cache: false
```

`release-please.yml` and the `pr` job of `prek-update.yml` (R2):

```yaml
    environment:
      name: release
      deployment: false
```

The Pages upload (S3):

```yaml
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0
        with:
          path: great-docs/_site
          # great-docs writes `.well-known/agent-skills/`, which `npx skills add` reads.
          include-hidden-files: true
```

The release build (R5):

```yaml
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          # The ancestor check reads `origin/main`.
          fetch-depth: 0
          persist-credentials: false
      - run: git merge-base --is-ancestor "$GITHUB_SHA" origin/main
```

`prek-update.yml`, the lock refresh (U3):

```yaml
      - run: |
          uv run --locked --only-dev prek update --freeze --cooldown-days 7
          uv lock --upgrade --exclude-newer '7 days'
          # The first lock writes `exclude-newer` into `uv.lock`, and `uv lock --check` fails until this one removes it.
          uv lock
```

`pyproject.toml`, coverage (C6):

```toml
[tool.coverage.run]
source_pkgs = ["epistole"]

[tool.coverage.report]
# Every other exclusion is a `# pragma: no cover` that a reviewer sees.
exclude_also = ["if TYPE_CHECKING:"]
fail_under = 100
show_missing = true
```

`dependabot.yml` (U1), on both entries:

```yaml
    schedule:
      interval: weekly
      day: monday
```

The prek cache, held back until a second go.dev failure (C12):

```yaml
      # prek builds gitleaks and actionlint with a Go toolchain it downloads from go.dev, and a cache hit skips both.
      - uses: actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        with:
          path: |
            ~/.cache/prek/hooks
            ~/.cache/prek/repos
          key: prek-${{ runner.os }}-${{ hashFiles('prek.toml') }}
```

## 7. Plan for dagster-dataframely

**Do tier 1 now, list dd as "maintenance", and do tier 2 at the next dd release with user-facing changes.** release-please, the changelog and the approved publish are useful only at a release.
With no users, a port PR for every standard change costs time and adds nothing until then.

### 7.1 Tier 1, the security floor

Settings, about 10 `gh api` calls (exact bodies in [Appendix C](#appendix-c-repository-settings-and-the-ruleset-json), including dd's two rulesets):

1. Require SHA pins; stop Actions approving PRs.
   No workflow changes, because every dd action already pins.
2. `pypi`: the owner as reviewer, `v*` tags, admin bypass off.
   Then `GET` the environment and check `can_admins_bypass: false`, because the REST docs omit that field.
3. Dependabot alerts and security updates, CodeQL default setup, private vulnerability reporting.
4. Squash only with `PR_TITLE` and `PR_BODY`, auto-merge on.
5. Rulesets: `main` requiring `test`, `lint` and `build` (the names dd's PRs report today); `version tags` with the admin as the only bypass.
6. On pypi.org, confirm the trusted publisher names environment `pypi` (dd 0.9.0's provenance does).

One PR, `ci: add uv to Dependabot and drop the TestPyPI and latest jobs`:

- `dependabot.yml`: Epistole's `uv` entry with `day: monday`; actions prefix `ci`; ignore `polars` major updates until `dagster-polars` stops passing `scan_parquet(rechunk=)`.
- `pyproject.toml`: delete `[tool.uv] required-version`, which breaks Dependabot once Dependabot runs uv 0.13.
- Every `setup-uv` step: `version: latest-known`.
  The `lint` prek step: `GH_TOKEN`.
- `release.yml`: delete the `testpypi` job and `workflow_dispatch`.
  After merging, delete the `testpypi` environment, then the TestPyPI publisher.
  A run that names a missing environment creates it with no rules, so delete the job first.
- `ci.yml`: delete `latest` and its schedule.
  F2 makes it fail from its next run, and the Dependabot uv PR shows the same break on a PR that names the cause.

Cost: about an hour of maintainer time, and from then on every change, a release commit included, needs a PR.

### 7.2 Tier 2, full adoption

| # | Title | Content |
| --- | --- | --- |
| 1 | `ci: adopt the standard's hooks and title check` | `prek.toml` as Epistole's plus dd's hooks; tombi in place of `check-toml`; `pr-title.yml`; `ruff.toml` without `preview = true` (153 restyled lines); `CHANGELOG.md` excluded in `rumdl.toml` and `typos.toml`, because a generated entry fails MD012 and MD004 and typos reads short SHAs as words; `[update] exclude_tags = ["typos-dict-*"]` in `prek.toml`; `extend-words` for `cpy` and `als` in place of the `*.toml` exclusion (F16). |
| 2 | `deps: raise the universal-pathlib floor to <bisected version>` | `lowest` fails at `universal-pathlib==0.2.0` with `No module named 's3fs'`. Needs tier 2 PR 1's type list. |
| 3 | `ci: adopt the standard's CI jobs` | `ci.yml` with C1 to C5 and C8 to C17 and dd's departures: 3.12 to 3.14; `uv run --locked --directory demo pytest` (20 tests CI never ran); `--all-packages` on the docs sync. `filterwarnings = ["error"]` with three ignores, `xfail_strict`. Switch the ruleset to `all-green` and `title` after both run on this PR, before it merges. |
| 4 | `ci: release with release-please` | `release-please.yml`, `prek-update.yml`, config, manifest `{".": "0.9.0"}` (no `bootstrap-sha`); `release.yml` as Epistole's; delete `docs.yml`; `CHANGELOG.md` preamble rewritten and no `## Unreleased` again; `user_guide/upgrading.qmd` with the 80 lines of 0.7 to 0.9 migrations; `CONTRIBUTING.md` with the SHA and departures; `CLAUDE.md` imports. Before: install the App, create `release` with a dd key, add the App to the tag bypass. After: `github-pages` to `v*`. |
| 5 | `test: require 100% line coverage` | Measure first; if short, add tests or record the number as a departure. |

The `filterwarnings` ignores, measured on 3.12 (they make 420 tests pass):

```text
error
ignore::dagster.BetaWarning
ignore::DeprecationWarning:dagster\._core
ignore::DeprecationWarning:dagster_polars
```

Write the module filter as `dagster\._core`: the filter matches a prefix of the module name, so `dagster` would also match `dagster_dataframely`.

dd's departures: the 3.12 floor (end of life October 2028); no 3.15 until Dagster drops `Requires-Python <3.15`, so `next-python` stays on 3.15 as the signal; every example runs in the build; the demo workspace; the dd-only hooks; the warning ignores.

Effort: 5 PRs touching about 21 files, plus 6 settings steps.
Known work: a floor bisect, 5 warnings, a 153-line restyle, an 80-line migration move.
Not measured: dd's coverage, its suite on Linux and Windows, and Dependabot's uv updater on a workspace.
Expect one to two days of agent work over about a week of reviews.

### 7.3 Python 3.15 and dd

Dagster 1.13.26 declares `Requires-Python <3.15,>=3.10`, and Dagster's `master` still does.
`pip install dagster-dataframely` on 3.15 ends in `ResolutionImpossible`. uv ignores upper bounds, so a uv install succeeds, and then 10 tests fail inside polars 1.44.2. dd's own code is not implicated.
Dagster took 93 days to allow 3.14, so expect 3.15 in early 2027.

## 8. Retiring oxyscraper

### 8.1 The decision

On 2026-10-11 the maintainer decided to delete the repo and the PyPI project, because the new Oxylabs Web API makes a wrapper over the Classic API not worth maintaining (oxyscraper memory `oxyscraper-sunset.md`).
This report and the copied research notes keep the CI/CD record.
`gh repo archive` would keep the issue threads and every link instead, if that is ever wanted.

### 8.2 Steps before deletion

1. Check oxylake: its research tickets ran jobs through `oxyscraper` and the `oxy` CLI on 2026-10-07, and both stop installing once the PyPI project is deleted.
2. Copy the three research notes ([1.2](#12-before-deleting-oxyscraper)).
3. Move `web-api-guide.md`, untracked in the checkout, somewhere the checkout's deletion does not remove: it holds the lessons kept for the new Web API.
4. Merge Epistole PR 8, which moves this report and its appendices to `docs/research/`.
5. Replace `~/.claude/CLAUDE.md:64-66` ([8.4](#84-replacement-text)).
6. Move `typing-everywhere.md` and `dev-floors-newest-past-cooldown.md` out of oxyscraper's project memory, because both state preferences for every package.
7. Uninstall the release App from oxyscraper, so its key reaches one repo fewer.
8. Remove oxyscraper's trusted publisher on pypi.org, delete the PyPI project, then delete the repo.

Not covered by this report: oxyscraper's other 10 research notes (`live-api.md`, `obstore-vs-fsspec.md` and others) and the rest of its project memory under `~/.claude/projects/-Users-ozanozbeker-Dev-oxyscraper/memory/`.
Deleting the repo deletes the notes.

### 8.3 References that break

| Location | Points at |
| --- | --- |
| `~/Dev/epistole/CONTRIBUTING.md:3` | "oxyscraper is its reference repo" |
| `~/Dev/epistole/CONTRIBUTING.md:4` | oxyscraper#22 |
| `~/Dev/epistole/CONTRIBUTING.md:6` | `oxyscraper/blob/main/CONTRIBUTING.md#a-new-repo`, an anchor that no longer exists |
| `~/.claude/CLAUDE.md:64-66` | `~/Dev/oxyscraper`, its file list, its "Repository settings" section |
| `~/.claude/projects/-Users-ozanozbeker-Dev-epistole/memory/auto-merge-prs.md:11,13` | context only; the rule still holds |
| `epistole#23`, `#73` (open), `#74`, `#75`, `#76`, `#77`, PR `#80`, PR `#83` | oxyscraper issues, files at `d5ca42a`, and ruleset IDs 24126503 and 24126504 (Appendix C keeps both) |
| `oxyscraper` 0.0.1 and 0.1.0 on PyPI | deleted with the project |
| `~/Dev/oxylake/.scratch/` notes, oxylake memory `every-oxylabs-job-in-lake.md`, `~/Dev/oxyscraper-captures/` | the package and the `oxy` CLI, which stop installing once the PyPI project is deleted |

No workflow or config in Epistole or dd fetches from oxyscraper at run time, and Epistole's `release` environment holds its own App credentials, so no CI job breaks. dagster-dataframely has no reference to oxyscraper.

### 8.4 Replacement text

Epistole `CONTRIBUTING.md:3-6`:

```markdown
This file holds the release standard for the maintainer's Python packages, and Epistole is its reference repo.
[ADR 0021](docs/adr/0021-epistole-holds-the-release-standard-for-every-package.md) records the decision, and [the research note](docs/research/ci-cd-standard.md) holds the evidence.
A package that adopts the standard follows [Adopting the standard](#adopting-the-standard), and [Epistole's departures](#epistoles-departures) lists where Epistole itself differs.
```

`~/.claude/CLAUDE.md:64-66`:

```markdown
### New packages follow Epistole's release standard

`~/Dev/epistole` is the reference repo for my packages, and its `CONTRIBUTING.md` holds the standard. A new package copies the files that its "Adopting the standard" section lists, replaces `epistole` in each, and applies its "Repository settings" with my release App as the GitHub App and me as the `pypi` reviewer. The package's `CLAUDE.md` imports `@~/Dev/epistole/CONTRIBUTING.md`, and its own `CONTRIBUTING.md` records the Epistole commit it copied and lists where it departs. A change to a standard file merges in Epistole first, then in each package that follows it.
```

"Adopting the standard", for Epistole's `CONTRIBUTING.md`:

1. Copy `.github/dependabot.yml`, `.github/workflows/{ci,pr-title,release-please,release,prek-update}.yml`, `release-please-config.json`, `prek.toml`, `ruff.toml`, `rumdl.toml`, `tombi.toml`, `pyrefly.toml`, `great-docs.yml`, `user_guide/upgrading.qmd`, `.python-version`, the `[build-system]`, `[tool.pytest.ini_options]` and `[tool.coverage.*]` tables, and the `dev` and `docs` dependency groups.
   Replace `epistole` in each.
2. Write `.release-please-manifest.json`.
   A repo with no release sets `bootstrap-sha` and gives its first PR a `Release-As: 0.0.1` footer.
3. In the new repo's `CONTRIBUTING.md`, write `Copied from Epistole at <sha>` and a departures table.
   In its `CLAUDE.md`, import `@~/Dev/epistole/CONTRIBUTING.md`, then `@CONTRIBUTING.md`.
4. To catch up: `git -C ~/Dev/epistole diff <sha> HEAD -- .github release-please-config.json prek.toml ruff.toml rumdl.toml tombi.toml pyrefly.toml great-docs.yml user_guide/upgrading.qmd pyproject.toml CONTRIBUTING.md`, port the diff, update the SHA.

"Epistole's departures": the 3.13 floor and its three reasons; the docs build runs no examples; the Prose naming rule.

## 9. Open questions

Each has a default, so none blocks the work.

1. **Does anything still install `oxyscraper` from PyPI?**
   Default: check oxylake, then delete as decided on 2026-10-11.
2. **dd tier 2 now or at its next release?**
   Default: tier 1 now, tier 2 with the next release that has user-facing changes.
3. **What does the release App hold, and where do copies of its key live?**
   Only the maintainer can read the App's page.
   Default: Contents, Issues and Pull requests read and write plus Metadata read; delete any saved `.pem`; a fresh key per repo.
4. **Drop `preview = true` from dd's `ruff.toml`?**
   Default: yes.
   Its reason is gone with ruff 0.16.8, and preview styles can change on any ruff bump, for a one-time cost of 153 restyled lines.
5. **Ignore polars majors in dd's Dependabot, or cap `polars<2` for users?**
   Default: ignore in Dependabot only.
   Every measured failure is inside `dagster_polars`, a dev dependency.
6. **Keep this report?**
   Default: PR 8 moves it to `docs/research/ci-cd-standard.md`, so Epistole keeps the oxyscraper record.

## Appendix A. The decision record from oxyscraper

oxyscraper's issues and research notes recorded 50 decisions, D1 to D50.
The entries below are copied from the preservation pass of 2026-10-11, so they stay readable after the repo is deleted.
Paths such as `oxyscraper/CONTRIBUTING.md:63-76` refer to oxyscraper at `4f45e85`, and they stop resolving once the repo is deleted.
[Appendix E](#appendix-e-oxyscraper-files-kept-verbatim) keeps the files still worth copying.
`oxy#N` is `https://github.com/ozanozbeker/oxyscraper/issues/N`. "release-practices.md" and "ci-and-docs-practices.md" are two of the research notes that [1.2](#12-before-deleting-oxyscraper) copies into Epistole's `docs/research/`. "memory" names a file in oxyscraper's project memory, `~/.claude/projects/-Users-ozanozbeker-Dev-oxyscraper/memory/`.

### A.0 Status under the unified standard

| Decision | Status | Change |
| --- | --- | --- |
| D1 to D16 | kept | D4: Epistole adopts the type list (P2). D11: add trap P5. D7: only a repo with no release sets `bootstrap-sha`. |
| D17 | changed | `next-python` runs the newest CPython at beta 1 and stays on it after final (C3); no `continue-on-error` (C4). |
| D18 | changed | `--exclude-newer '7 days'`, Python from `.python-version`, coverage runs here (C5, C7). |
| D19 | kept | |
| D20 | changed | No Codecov, no `id-token: write`; `fail_under = 100` in config (C6, C8). |
| D21 | changed | `GH_TOKEN` for zizmor, `SKIP` for the staged-only hooks, a `gitleaks-ci` hook (C10, C11). |
| D22 | changed | Examples run at build time unless they have side effects (S5). |
| D23, D24 | kept | D24's httpx2 exception was oxyscraper's only. |
| D25 | changed | `dev` floors stay at the newest release past the cooldown, raised by hand with no script; a monthly `uv lock --upgrade` moves the lock (U3, U5, F34). |
| D26 | changed | `day: monday` (U1). |
| D27 | changed | The monthly job also refreshes `uv.lock` and runs in two jobs (U3, U4). |
| D28, D29 | kept | |
| D30 | changed | zizmor gets a token in CI (C10). |
| D31 | kept | Redundant at setup-uv v10, and the uv cache is off everywhere anyway (C16). |
| D32 | changed | Minimal App permissions, a key per repo, `deployment: false` (R2, R3). |
| D33, D34 | kept | |
| D35 | changed | Ancestor check, `skip-existing`, and the site deploys from `release.yml` after `pypi` (R5, R6, S2). |
| D36 | kept | The reason for allowing self-review changes (F28). |
| D37 to D39 | kept | |
| D40 | changed | Deploys after the approved upload, HTTPS enforced, hidden files kept (S2 to S4). |
| D41 | changed | No "Built with Claude Code" badge, because the maintainer's global rule bans crediting AI tools. The wording is oxyscraper's. |
| D42 | kept | |
| D43, D46, D49 | oxyscraper only | |
| D44 | changed | great-docs reads no `_brand.yml`; colours live in `assets/theme.css`. |
| D45 | pattern kept | A public fake at the transport seam, where a package has an HTTP seam. |
| D47 | repo only | `pyrefly-typing` stays where `tests/typing/` exists (H7). |
| D48 | optional | The live module stays out of `CONTRIBUTING.md` (S6). |
| D50 | changed | The `next-python` wording (C3). The end-of-life list loses ruff's `target-version` (H9) and the `lowest` job's Python (C5). |

Each entry gives the decision, the alternatives considered, the evidence, and where oxyscraper implemented it.
Unless marked, the decision is from oxy#22 ([Appendix B](#appendix-b-oxyscraper22-the-resolution-verbatim)) and the evidence from oxy#27 and oxy#28, whose detail is in the two research notes.

### A.1 Versioning and changelog

#### D1. SemVer, with both pre-major options, so a new minor below 1.0 always means a breaking change

- Decision: `bump-minor-pre-major: true` and `bump-patch-for-minor-pre-major: true`.
  A user can pin `oxyscraper~=0.3.0` and get every feature and fix.
- Alternatives: neither option (a `feat!:` on `0.x` becomes `1.0.0`); `bump-minor-pre-major` alone (FastAPI's policy, where features and breaks both bump the minor); CalVer (attrs).
- Evidence: release-please 17.6.0 measured from `0.2.0`: neither gives `feat!:` 1.0.0, `feat:` 0.3.0, `docs:` 0.2.1; `bump-minor-pre-major` gives 0.3.0, 0.3.0, 0.2.1; both give 0.3.0, 0.2.1, 0.2.1 (release-practices.md "Bumps below 1.0.0").
  Polars' pre-1.0 policy matches both options: <https://github.com/pola-rs/polars/blob/ea086d6af4fad255fece8a5f06410a3aade89633/docs/development/versioning.md#L5-L7>.
  FastAPI's matches `bump-minor-pre-major` alone: <https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/docs/en/docs/deployment/versions.md#L7-L57>.
  SemVer: <https://semver.org/spec/v2.0.0.html>.
  All four surveyed libraries past 1.0 shipped a breaking change in a minor (pytest 8.4.0, Pydantic 2.8.0, urllib3 2.6.0, Polars 1.31.0).
- Implemented: `oxyscraper/release-please-config.json:8-9`; `oxyscraper/CONTRIBUTING.md:63-76` (the table of types and bumps).

#### D2. Leaving 0.x takes a `Release-As: 1.0.0` footer, and the policy after 1.0 is set then

- Evidence: with `bump-minor-pre-major`, no commit type reaches `1.0.0` (release-practices.md).
- Implemented: `oxyscraper/CONTRIBUTING.md:75-76`.

#### D3. Below 1.0, a break needs no deprecation period

- Alternatives: pytest's two-minor deprecation then major removal; Pydantic keeps deprecations until V3; Polars removes two breaking releases later.
- Implemented: `oxyscraper/CONTRIBUTING.md:82`.

#### D4. Visible and hidden commit types, with `deps` added as a visible type

- Decision: `feat`, `fix`, `perf`, `docs`, `deps`, `revert` are visible and bump the patch below 1.0; `refactor`, `test`, `build`, `ci`, `style`, `chore` are hidden and bump nothing on their own.
- Evidence: under `release-type: python`, a `docs:` commit alone opens a release PR (<https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/python.ts#L31-L44>).
  PR oxy#91 found that `conventional-pre-commit`'s default types lack `deps`, so a `deps:` title failed the `title` check.
  Passing any type replaces the defaults, so the list repeats them.
  Verified on 2026-10-11 in the hook source at rev `91ab4bf` (`~/.cache/prek/repos/dec2c893d6378faa/conventional_pre_commit/format.py:93-106`): defaults are `feat`, `fix`, `build`, `chore`, `ci`, `docs`, `perf`, `refactor`, `revert`, `style`, `test`.
- Implemented: `oxyscraper/release-please-config.json:17-30`; `oxyscraper/prek.toml:9-29`.

#### D5. release-please writes `CHANGELOG.md` and the GitHub release from Conventional Commits; migration notes go in a docs page written by hand

- Decision: a breaking PR ends its description with a one-line `BREAKING CHANGE:` footer that links to its section of `user_guide/upgrading.qmd`, and writes the migration under the next minor's heading, such as `## 0.4`.
- Alternatives: towncrier fragments (pytest, attrs, urllib3); Latest Changes app (FastAPI); release-drafter (Polars); hand edits to the release PR body.
- Evidence: all six surveyed libraries write migration notes by hand. release-please keeps only commit subjects and the first paragraph of a `BREAKING CHANGE:` footer (<https://github.com/googleapis/release-please/blob/v17.6.0/src/commit.ts#L316-L369>, measured).
  The GitHub release body comes from the merged release PR body, and an edit there is lost when `main` moves before the merge (<https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L1089-L1102>).
  An edit never reaches `CHANGELOG.md`.
  Polars ships an upgrade guide with every breaking release: <https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/docs/source/releases/upgrade/index.md#L3-L7>.
- Implemented: `oxyscraper/user_guide/upgrading.qmd:1-6`; `oxyscraper/CONTRIBUTING.md:44`, `:78-82`, `:171-172`.

#### D6. `BEGIN_COMMIT_OVERRIDE` in the merged PR's description corrects a changelog entry

- Evidence: release-please finds a commit's PR through `associatedPullRequests`, so a commit pushed straight to `main` cannot be corrected (<https://github.com/googleapis/release-please/blob/v17.6.0/README.md#L118-L138>, <https://github.com/googleapis/release-please/blob/v17.6.0/src/github.ts#L357-L386>).
  This is one reason every change goes through a PR.
- Implemented: `oxyscraper/CONTRIBUTING.md:45-46`, `:160-161`.

#### D7. `bootstrap-sha` names the commit before release-please, so the research commits stay out of the first changelog

- Evidence: without it, the first release notes list every `docs:` commit in up to 500 commits of history (<https://github.com/googleapis/release-please/blob/v17.6.0/docs/manifest-releaser.md#L74-L103>).
- Implemented: `oxyscraper/release-please-config.json:3` is `"bootstrap-sha": "ca2a7768395722bd8e7871708ff40a0e775cc11d"`, the commit of PR oxy#32. release-please ignores it after the first release PR merges.

#### D8. The first upload is an empty `0.0.1` that registers the name; `0.1.0` is the first real release

- Decision: PR oxy#33 carries `Release-As: 0.0.1` with classifier `Development Status :: 1 - Planning`.
  PR oxy#137 carries `Release-As: 0.1.0` and moves to `Development Status :: 3 - Alpha`.
- Evidence: PyPI registers a name only at the first upload, and a pending trusted publisher does not reserve it (<https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>, quoted in oxy#8).
  `release-type: python` always proposes `0.1.0` for the first release and never reads `initial-version` (<https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/python.ts#L200-L202>).
  PyPI normalises names: it strips `-`, `_`, `.`, maps `l` and `i` to `1` and `o` to `0`, so `oxyscraper` blocks `oxy-scraper` and `oxy_scraper` (oxy#8).
- Implemented: oxy#29 comment; `oxyscraper/pyproject.toml:13`.

### A.2 Changes to `main`

#### D9. Every change reaches `main` through a PR, the maintainer's included

- Alternatives: allow direct pushes with an admin "Always allow" bypass (FastAPI's Latest Changes app pushed 15 of its last 30 commits, attrs' maintainer 21 of 30).
- Evidence: a required check gates only PRs, so a PR is the one route where CI runs before a change lands.
  `BEGIN_COMMIT_OVERRIDE` also needs the PR (D6).
  "Require a pull request before merging" applies even with zero approvals (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets>).
  A PR author cannot approve their own PR, so a required approval blocks a sole maintainer (<https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews>).
- Implemented: `main` ruleset (Appendix C); `oxyscraper/CLAUDE.md:28-30`; `oxyscraper/CONTRIBUTING.md:18-37`.

#### D10. Squash merges only, and the squash commit takes the PR title and description

- Evidence: FastAPI, Pydantic, attrs and Polars allow only squash and title the commit with the PR title.
  GitHub's default uses the commit title for a one-commit PR, and a setting makes it always use the PR title (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/configuring-commit-squashing-for-pull-requests>).
- Implemented: API `repos/ozanozbeker/oxyscraper` returns `allow_squash_merge: true`, `allow_merge_commit: false`, `allow_rebase_merge: false`, `squash_merge_commit_title: PR_TITLE`, `squash_merge_commit_message: PR_BODY`; the ruleset's `allowed_merge_methods: ["squash"]`.

#### D11. A `title` check runs the `commit-msg` hook from `prek.toml` against the PR title

- Alternatives: `thehanimo/pr-title-checker` from `pull_request_target` (Polars, not required); a required label (FastAPI); a towncrier fragment check (pytest, urllib3).
- Evidence: without it, a PR titled `Update stuff` merges, and release-please skips it without a warning (oxy#22).
  Only Polars of the six checks titles (ci-and-docs-practices.md).
- Implemented: `oxyscraper/.github/workflows/pr-title.yml:1-25`.
  The title goes through an `env:` variable, not inline `${{ }}`, so a title cannot inject shell (`pr-title.yml:21-25`).

#### D12. Auto-merge, head branch deletion, and `gh pr merge --auto --squash` after each PR

- Implemented: API returns `allow_auto_merge: true`, `delete_branch_on_merge: true`; `oxyscraper/CONTRIBUTING.md:23-37`.
- Lesson: with deletion on, a commit pushed after auto-merge fires recreates the deleted branch and needs a second PR (memory `auto-merge-before-last-push.md`, Appendix D).

#### D13. One aggregate `all-green` job is the only required CI check, beside `title`

- Alternatives: list every job name (urllib3 requires 30); path filters on the workflow trigger.
- Evidence: FastAPI, Pydantic, pytest and attrs require one `re-actors/alls-green` job.
  GitHub keeps a required check Pending when a path filter skips the workflow, counts a job skipped by `if:` as success, and skips a job that needs a failed job, so the aggregate needs `if: always()` (<https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks#handling-skipped-but-required-checks>, <https://github.com/re-actors/alls-green/blob/b5b5b37504aa4183270bd3d855c52a67f212be35/README.md#why>).
- Implemented: `oxyscraper/.github/workflows/ci.yml:131-141`, with `allowed-failures: next-python`.
  The ruleset pins both required checks to `integration_id: 15368` (GitHub Actions), so a status from any other app cannot satisfy them.

#### D14. No merge queue and no "require branches to be up to date"

- Evidence: merge queues need an organization-owned repo (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue>).
  No surveyed ruleset requires up-to-date branches.
- Implemented: ruleset `strict_required_status_checks_policy: false`.

### A.3 CI on each PR

#### D15. `ci.yml` runs on every PR and every push to `main`, and cancels superseded PR runs only

- Implemented: `oxyscraper/.github/workflows/ci.yml:3-12`.

#### D16. `test` runs Ubuntu, macOS and Windows on every supported Python, against the built wheel

- Alternatives: Ubuntu only (attrs); Ubuntu and Windows (Polars); a smaller matrix on PRs and a fuller one on release (Pydantic only).
- Evidence: FastAPI, Pydantic, pytest and urllib3 test all three OSes in 15 to 30 jobs.
  Actions minutes are free on a public repo, and oxy writes local files and ships a CLI, so Windows is a real target (oxy#22). attrs tests the built wheel and pytest the built sdist (ci-and-docs-practices.md "Python and OS matrix").
- Implemented: `oxyscraper/.github/workflows/ci.yml:15-34`, matrix `os: [ubuntu-latest, macos-latest, windows-latest]`, `python: ["3.11", "3.12", "3.13", "3.14"]`, step `uv sync --locked --no-editable --all-extras`.
  The comment at `ci.yml:20` ties the matrix to the classifiers at `pyproject.toml:11-20`.
- Measured: 12 test jobs took 32 s to 58 s each on PR oxy#155 (`gh pr checks 155`).

#### D17. `next-python` runs the next CPython from its first beta, and may fail

- Implemented: `oxyscraper/.github/workflows/ci.yml:36-50`, `python-version: "3.15"`, `continue-on-error: true`, and `allowed-failures: next-python` in `all-green`.

#### D18. `lowest` runs the floor Python with `uv sync --resolution lowest-direct`

- Alternatives: a scheduled job against the newest versions (Pydantic tests earliest and latest twice a week); none.
- Evidence: FastAPI runs two lowest-direct legs.
  A floor that tracks the lock forces every user onto the maintainer's versions (oxy#22).
- Implemented: `oxyscraper/.github/workflows/ci.yml:52-66`, `python-version: "3.11"`, `cache-suffix: lowest`.
  No `--locked`, because the resolution differs from the lock.
- Gap: the job runs pytest but not pyrefly, so CI never type-checks at the floors (oxy#106 comment).

#### D19. pytest sets `filterwarnings = ["error"]`

- Evidence: a new upstream deprecation then fails the Dependabot PR that brings it in, before the removal breaks the package.
- Implemented: `oxyscraper/pyproject.toml:72-78` (`addopts` with `--strict-config`, `--strict-markers`, `--import-mode=importlib`, `-m "not live"`; `xfail_strict = true`).

#### D20. `coverage` fails under 100% line coverage and uploads to Codecov with OIDC (oxy#23, oxy#60, PR oxy#83)

- Decision: one job on Ubuntu and the newest Python, inside `all-green`.
  The config excludes only `if TYPE_CHECKING:`, so every other exclusion is a visible `# pragma: no cover`.
- Alternatives considered: none recorded beyond httpx2's own `--fail-under=100` as precedent.
- Evidence and measurements:
  - `coverage xml` exits 2 on a package with no statements whenever a fail-under is set, so CI passes `--fail-under=100` to `coverage report` instead of the config (PR oxy#83).
  - In codecov-action v7.1.1, `fail_ci_if_error` does not cover the OIDC token step, so the upload step uses `continue-on-error: true` (PR oxy#83).
  - The OIDC upload works without a Codecov sign-in; the sign-in only installs the Codecov GitHub App for PR comments and `codecov/*` statuses (oxy#58, oxy#60).
  - Codecov's free Developer plan has no limit for public repos; its 250-upload and 1-user caps apply to private repos (oxy#23).
  - The upload runs before `coverage report`, so Codecov's PR comment shows missed lines of a PR that fails the gate (`ci.yml:89`).
  - The job installs editable, so the report names files under `src/` where Codecov finds them (`ci.yml:80`).
- Implemented: `oxyscraper/.github/workflows/ci.yml:68-90` (`id-token: write`, `codecov/codecov-action@303a32d7a59b442fa8d48b6a1cc6825c09c847a5 # v7.1.1`, `use_oidc: true`); `oxyscraper/pyproject.toml:64-70`.

#### D21. `lint` runs every prek hook on every file in Actions; no test runs in a commit hook

- Alternatives: pre-commit.ci (pytest); `pre-commit/action` (Pydantic, urllib3); each tool called directly (Polars).
- Evidence: pre-commit.ci reads only `.pre-commit-config.yaml`, and prek's docs say upstream pre-commit does not read `prek.toml` (<https://github.com/j178/prek/blob/5ba6dc58a6285c551620354f139bbd8b5fa60e23/docs/compatibility.md>).
  Its free tier has no network access at hook runtime (<https://github.com/pre-commit-ci/issues/issues/13>), and the local hooks run through `uv run`.
  FastAPI and attrs run prek in Actions.
  Local hooks miss a `--no-verify` commit and a fork's commits (`ci.yml:92`).
- Implemented: `oxyscraper/.github/workflows/ci.yml:92-104` (`prek run --all-files --show-diff-on-failure`); `oxyscraper/prek.toml` (hooks: conventional-pre-commit v4.4.0, gitleaks v8.30.1, zizmor v1.30.1, actionlint v1.7.12, pre-commit-hooks v6.0.0, and local ruff check, ruff format, rumdl, tombi lint, tombi format, `uv lock --check`, pyrefly, pyrefly typing tests).

#### D22. `docs` builds the site on every PR and runs every example

- Evidence: great-docs runs Quarto `{python}` cells at build time.
  A fork's PR gets no secrets, so every example runs against the fake (D45).
- Implemented: `oxyscraper/.github/workflows/ci.yml:106-129`: `timeout-minutes: 20` because Quarto sets no cell timeout; `fetch-depth: 0` because great-docs reads git history for page dates; Quarto pinned to `1.10.18`; `GITHUB_TOKEN` passed because great-docs reads GitHub Releases for the changelog page and an anonymous runner gets 60 requests an hour.

### A.4 Dependencies and updates

#### D23. Runtime floors are the oldest version the `lowest` job proves; no upper bounds; a floor rises only in a `deps:` commit (oxy#21)

- Alternatives: caps such as `obstore>=0.11,<0.12`; a daily newest-versions job.
- Evidence (oxy#21, measured 2026-09-29):
  - A cap that a later release adds makes a resolver that needs the newer version pick an older release with no cap, so the rule holds from the first release.
  - Under `increase-if-necessary`, Dependabot's uv updater rewrites `obstore>=0.11,<0.12` to `<0.13` inside the grouped `chore:` PR, so a cap lifts silently (dependabot-core `requirements_updater.rb`).
  - Dependabot alone catches an upstream break: its weekly PR, after the 7-day cooldown, fails CI 7 to 14 days after the release.
    A daily newest-versions job was rejected because it skips the cooldown and changes the standard for every repo.
  - Bounds in peers on 2026-09-29: pydantic-ai-slim 2.51.0 `anyio>=4.7.0`, `httpx2>=2.7`, `pydantic>=2.12`; FastAPI 0.141.1 `pydantic>=2.9.0`; OpenAI 3.20.0 `anyio>=4.10.0,<5`, `httpx2>=2.12.0,<3`; Anthropic 1.9.0 `httpx2>=2.0.0,<3`.
- Implemented: `oxyscraper/pyproject.toml:24-30`; `oxyscraper/CONTRIBUTING.md:120-130`.

#### D24. A floor may sit above what `lowest` proves when a security audit flags lower versions (PR oxy#102, oxy#106)

- Decision: the `httpx2` floor is 2.12.0 while `lowest` proves 2.10.0, and `CONTRIBUTING.md` names the exception.
- Evidence: GHSA-7mj9-2mp8-4m2p (httpcore2 below 2.10.0, <https://github.com/advisories/GHSA-7mj9-2mp8-4m2p>), GHSA-h4x7-gw46-3wm6 (httpx2 below 2.11.0, <https://github.com/advisories/GHSA-h4x7-gw46-3wm6>), GHSA-8xx6-hgc6-gc2m (httpx2 below 2.12.0, <https://github.com/advisories/GHSA-8xx6-hgc6-gc2m>).
  None reaches oxy, but a user's audit still flags them (`oxyscraper/docs/research/httpx2.md:332-335`).
- Implemented: `oxyscraper/CONTRIBUTING.md:122-124`; `oxyscraper/.github/workflows/ci.yml:52`.

#### D25. `dev` floors equal the newest release at least 7 days old, and a monthly job raises them to the lock (PRs oxy#110, oxy#111)

- Decision: the maintainer said on 2026-10-01 "these are my dev tools and I like them updated" (memory `dev-floors-newest-past-cooldown.md`).
  Users never install the group, so a `chore:` commit raises them.
- Evidence: `uv add` keeps an existing specifier, even with `--upgrade-package` or `--bounds` (`prek-update.yml:32`).
  Dependabot's security updates skip the cooldown, so a floor can be younger than 7 days (PR oxy#111). coverage dropped from 7.16.2 to 7.16.1 because 7.16.2 was 4 days old (PR oxy#110).
- Implemented: `oxyscraper/pyproject.toml:45-56`; `oxyscraper/.github/workflows/prek-update.yml:32-51`.
- Status: the floor step has never run on a schedule.
  The only scheduled run, on 2026-10-01, predates PR oxy#111 (merged 2026-10-02) and opened no PR because nothing changed (run 36868061474 log: "Branch 'prek-update' is not ahead of base 'main' and will not be created").

#### D26. Dependabot updates `uv.lock` and actions weekly, grouped, after a 7-day cooldown, with `chore` and `ci` prefixes

- Alternatives: Renovate (none of the six use it); Dependabot's `pre-commit` ecosystem (reads only `.pre-commit-config.yaml`).
- Evidence: all six use Dependabot, five with a 7-day cooldown; Dependabot applies 3 days when `cooldown` is unset and none to security updates.
  `commit-message.prefix` also sets the PR title (<https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference>).
  The `github-actions` ecosystem updates SHA pins and their version comments (<https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories>).
  `increase-if-necessary` leaves each `>=` floor alone and moves only `uv.lock`, so a floor rises only in a deliberate `deps:` commit.
- Implemented: `oxyscraper/.github/dependabot.yml:1-29`.

#### D27. A monthly `prek-update.yml` runs `prek update --freeze --cooldown-days 7` and opens a PR with the App token

- Evidence: FastAPI runs a monthly `prek auto-update --freeze --cooldown-days 7` workflow (<https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/bump-pre-commit-hooks.yml>). prek 0.4.8 renamed `auto-update` to `update`, and 0.5.0 removed `auto-update` (<https://github.com/j178/prek/blob/5ba6dc58a6285c551620354f139bbd8b5fa60e23/CHANGELOG.md>).
  A PR opened with `GITHUB_TOKEN` starts no CI (D31), so the job uses the App token.
- Implemented: `oxyscraper/.github/workflows/prek-update.yml:1-60`: cron `17 6 1 * *`, `environment: release`, App token narrowed to `contents` and `pull-requests` write, `peter-evans/create-pull-request@5f6978faf089d4d20b00c7766989d076bb2fc7f1 # v8.1.1` with `sign-commits: true`, branch `prek-update`.
  Hooks are pinned as `rev = "<sha>"  # frozen: <tag>` (`oxyscraper/prek.toml:8,35,41,48,54`).

### A.5 Workflow security

#### D28. Every action is pinned to a full SHA with a version comment, and a repo setting requires it

- Evidence: five of six surveyed libraries pin all 380 action references; Polars pins none of 108.
  Pinning to a full SHA is the only immutable reference (<https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions>).
  Dependabot raises no alerts for SHA-pinned actions, only for version-pinned ones.
- Implemented: every `uses:` in `oxyscraper/.github/workflows/*.yml` matches `@<40 hex> # v` (checked with `grep -n 'uses:' .github/workflows/*.yml | grep -v -E '@[0-9a-f]{40} # v'`, which printed nothing).
  API `actions/permissions` returns `"sha_pinning_required": true`.
  Pins on 2026-10-11: `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`, `actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0`, `actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346 # v5.0.1`, `actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1`, `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1`, `actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0`, `astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0`, `codecov/codecov-action@303a32d7a59b442fa8d48b6a1cc6825c09c847a5 # v7.1.1`, `googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7 # v5.0.0`, `peter-evans/create-pull-request@5f6978faf089d4d20b00c7766989d076bb2fc7f1 # v8.1.1`, `pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2`, `quarto-dev/quarto-actions/setup@8a96df13519ee81fd526f2dfca5962811136661b # v2.2.0`, `re-actors/alls-green@b5b5b37504aa4183270bd3d855c52a67f212be35 # v1.3.0`.

#### D29. Each workflow starts with `permissions: {}`, each job asks for what it needs, and each checkout sets `persist-credentials: false`

- Evidence: the same five libraries set `permissions` in every workflow and `persist-credentials` on every checkout.
  The repo default `GITHUB_TOKEN` is read-only (API `actions/permissions/workflow` returns `"default_workflow_permissions": "read"`, `"can_approve_pull_request_reviews": false`).
- Implemented: `permissions: {}` at `ci.yml:8`, `pr-title.yml:8`, `release-please.yml:7`, `release.yml:8`, `docs.yml:8`, `live.yml:9`, `prek-update.yml:9`.

#### D30. zizmor and actionlint run as prek hooks; gitleaks runs as a hook; CodeQL default setup scans Python and Actions

- Alternatives: `zizmor-action` in Advanced Security mode (attrs, FastAPI), which uploads to code scanning and does not fail the job unless a ruleset blocks on code scanning (<https://github.com/zizmorcore/zizmor-action/blob/8eacaa5f3f72b6638f4f87c3f66113bbc0f363dd/README.md#usage-with-github-advanced-security-recommended>); a CodeQL workflow on every PR (urllib3).
- Evidence: CodeQL analyses Actions workflows (<https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning>).
  Default setup scans pushes, non-fork PRs and a weekly schedule (<https://docs.github.com/en/code-security/concepts/code-scanning/setup-types>).
- Implemented: `oxyscraper/prek.toml:32-49`; API `code-scanning/default-setup` returns `"state":"configured","languages":["actions","python"],"query_suite":"default","schedule":"weekly"`.
  Secret scanning and push protection are on, and Dependabot security updates are on (API `repos/ozanozbeker/oxyscraper` `security_and_analysis`); vulnerability alerts return 204 (enabled).

#### D31. Release workflows never restore a cache

- Evidence: a release must not restore a cache that a PR run could have written (`release.yml:21`, `docs.yml:27`).
- Implemented: `enable-cache: false` at `oxyscraper/.github/workflows/release.yml:22`, `docs.yml:28`, `prek-update.yml:29`.

### A.6 Release

#### D32. One GitHub App serves all the maintainer's package repos, and its token drives release-please and the hook updates

- Alternatives: `GITHUB_TOKEN` (all six surveyed libraries); a PAT (FastAPI until 0.141.1); `tiangolo/pr-submit` (FastAPI since 2026-08-08, no release yet).
- Evidence (release-practices.md "`GITHUB_TOKEN` against a GitHub App token"):
  - A PR opened by `GITHUB_TOKEN` starts `pull_request` runs in an approval-required state; pytest 9.1.1's release PR shows `action_required` (<https://github.com/pytest-dev/pytest/actions/runs/27818252525>).
    An event caused by `GITHUB_TOKEN` starts no other workflow, so pytest's tags 9.1.0 and 9.1.1 started no runs (<https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow>).
  - `permissions:` limits only `GITHUB_TOKEN`; the App token carries the installation's permissions, narrowed by `permission-*` inputs (<https://github.com/actions/create-github-app-token/blob/v3.2.0/README.md#L400-L402>).
  - The token works in one job, expires after an hour, and is revoked when the job ends (<https://github.com/actions/create-github-app-token/blob/v3.2.0/README.md#L15-L16>).
  - `create-github-app-token` v3 takes `client-id`; `app-id` is deprecated (<https://github.com/actions/create-github-app-token/blob/v3.2.0/README.md#L351-L356>).
  - The approval on `pypi` stops a leaked App key from publishing on its own (oxy#22).
- Implemented: `oxyscraper/.github/workflows/release-please.yml:14-31` (`environment: release`, `client-id: ${{ vars.APP_CLIENT_ID }}`, `private-key: ${{ secrets.APP_PRIVATE_KEY }}`, `permission-contents: write`, `permission-issues: write`, `permission-pull-requests: write`).
  The App's bot is `ozanozbeker-release[bot]` (user id 335071888, `gh api 'users/ozanozbeker-release%5Bbot%5D'`), and its integration id in the tag ruleset is 5110076.
  `gh api /apps/ozanozbeker-release` returns 404, so the App is private and its slug is unconfirmed.

#### D33. `release-please.yml` runs on each push to `main`; all settings live in `release-please-config.json`

- Trap: a `release-type` input makes the action ignore the config file, with no warning (`release-please.yml:28`, `CONTRIBUTING.md:167-168`).
- Implemented: `oxyscraper/.github/workflows/release-please.yml:1-31` (`concurrency: group: ${{ github.workflow }}`, `cancel-in-progress: false`); `oxyscraper/release-please-config.json:1-33`; `oxyscraper/.release-please-manifest.json:2` is `"0.1.0"`.
  `release-please-action` v5.0.0 bundles release-please 17.6.0 (<https://github.com/googleapis/release-please-action/blob/v5.0.0/package-lock.json#L5130-L5132>).

#### D34. `extra-files` keeps `uv.lock` in step with the release version

- Evidence: release-please never updates `uv.lock` (<https://github.com/googleapis/release-please/issues/2561>), so a release PR fails `uv lock --check` (measured).
  The TOML updater parses each value into an object, so the filter needs `.value` (<https://github.com/googleapis/release-please/blob/v17.6.0/src/util/toml-edit.ts#L21-L35>); `@.name=='oxyscraper'` logs "No entries modified" (measured). lazycogs and descope use the same entry; descope added it after a release PR failed CI (<https://github.com/descope/python-sdk/pull/1518>). open-feature's release PR left `uv.lock` stale because its CI runs `uv sync --frozen` (<https://github.com/open-feature/python-sdk/pull/602>). workos-python runs `uv lock` in a second job instead (<https://github.com/workos/workos-python/blob/83af6f53ba6456a7c03c0cef1b3fcc80b3da91c4/.github/workflows/release-please.yml#L51-L83>).
- Implemented: `oxyscraper/release-please-config.json:10-16`: `"jsonpath": "$.package[?(@.name.value=='oxyscraper')].version"`.

#### D35. `release.yml` runs on `release: published`, builds in one job and publishes in another, and runs no tests

- Alternatives: publish jobs inside the release-please workflow keyed on `release_created` (descope, openai-python); `uv publish` (FastAPI, pydantic-core, lazycogs, descope); a reusable publish workflow shared across repos.
- Evidence:
  - The release PR already passed the full matrix, and the ruleset blocks its merge until it passes.
    Five of six surveyed release workflows run no tests.
  - PyPI, the PyPA action and uv's guide recommend a build job without `id-token: write` and a publish job that only downloads and uploads (<https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/security-model.md#L149-L159>).
  - PyPI does not support trusted publishing from a reusable workflow, because it matches the file in `job_workflow_ref` (<https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/troubleshooting.md#L7-L11>, <https://github.com/pypi/warehouse/issues/11096>).
    The publish job stays in each repo's own workflow.
  - `pypa/gh-action-pypi-publish` makes PEP 740 attestations by default (<https://github.com/pypa/gh-action-pypi-publish/blob/v1.14.2/action.yml#L83-L88>).
    `uv publish` uploads attestations but does not create them (<https://github.com/astral-sh/uv/blob/0.12.19/docs/guides/package.md#L177-L203>); `astral-sh/attest-action` is v0.0.6 and early-stage (<https://github.com/astral-sh/attest-action/blob/v0.0.6/README.md#L20-L29>).
  - A `release: published` workflow runs because an App token created the release, as in lazycogs (<https://github.com/developmentseed/lazycogs/blob/ca203a9326f58b4b73457be1ed456d8f8c3ed1f1/.github/workflows/publish-pypi.yml#L3-L33>).
    A release published by hand starts the same workflows, which is the recovery path.
- Implemented: `oxyscraper/.github/workflows/release.yml:1-46`.
  Build job: `contents: read`, `enable-cache: false`, `uv build`, then `unzip -l dist/*.whl | grep -q 'oxyscraper/py.typed'` because no test reads `py.typed`.
  Publish job: `environment: pypi`, `url: https://pypi.org/p/oxyscraper`, `id-token: write` only.
- Result: PyPI lists 0.0.1 and 0.1.0, each wheel and sdist with one attestation from `release.yml` in the `pypi` environment (oxy#29, oxy#81).

#### D36. The `pypi` environment accepts `v*` tags only and waits for the maintainer's approval, with self-review allowed and no admin bypass

- Evidence: PyPI calls an environment optional but strongly recommended and suggests required reviewers (<https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/security-model.md#L128-L140>). pytest, Pydantic, urllib3 and Polars require an approval, and all four allow self-review.
  "Prevent self-review" under an App-started run was unmeasured, so it stays off.
- Implemented: API `environments` returns `pypi` with `required_reviewers` = `ozanozbeker`, `prevent_self_review: false`, `can_admins_bypass: false`, and branch policy `v*` (type `tag`).

#### D37. A tag ruleset lets only the App and the admin create, update or delete `v*` tags

- Evidence: PyPI suggests tag protection for tag-triggered publishing (<https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/security-model.md#L142-L147>). pytest and urllib3 protect tags with rulesets.
- Implemented: ruleset `version tags` (id 24126504), Appendix C.

#### D38. No TestPyPI upload

- Evidence: only attrs and urllib3 use TestPyPI, for a dev build of every push to `main`.
  The empty `0.0.1` tested the pipeline instead (D8).

#### D39. No `draft` releases

- Evidence: GitHub creates no tag for a draft, so release-please's next release PR starts from the wrong place; `release_created` is `true` for a draft too (release-practices.md "`draft` and `force-tag-creation`").
  `draft` with `force-tag-creation` was left untested.

### A.7 Docs

#### D40. great-docs builds the site; GitHub Pages serves it at `https://ozanozbeker.com/oxyscraper/`; it deploys on `release: published`

- Alternatives: Sphinx with Furo on Read the Docs (pytest, attrs, urllib3); Zensical or MkDocs Material on Cloudflare Pages (FastAPI, Pydantic); MkDocs Material and Sphinx on GitHub Pages (Polars).
- Evidence: Material for MkDocs is in maintenance mode, with critical fixes until 2027-05-05 (<https://github.com/squidfunk/mkdocs-material/issues/8523>).
  Zensical 0.0.65 is an alpha (<https://github.com/zensical/docs/blob/72fdc0623f97b921215f9b95f084a840fbf4cbcf/docs/upgrade.md?plain=1#L48-L53>).
  MkDocs 2.0.dev6 loads no plugins (<https://github.com/encode/mkdocs/blob/1110d2ea607561335b74eb11e61252379c6a1855/src/mkdocs/mkdocs.py#L220-L238>). great-docs 0.17.0 runs examples at build time, builds a changelog from GitHub Releases, and supports versioned sites.
  GitHub Pages has no public PR previews: `actions/deploy-pages` v5.0.1 calls its `preview` input alpha and not public (<https://github.com/actions/deploy-pages/blob/368f82528645a54fb793d4d04e342629a3f51346/action.yml#L28-L31>).
  The site documents the version on PyPI, so it deploys on release, not on push.
- Implemented: `oxyscraper/.github/workflows/docs.yml:1-52` (`concurrency: group: pages`; `deploy` job with `pages: write`, `id-token: write`, `environment: github-pages`); `oxyscraper/great-docs.yml:1-28` (`parser: numpy`, `dynamic: true`, `site_url`, `include-after-body: assets/footer.html` because great-docs 0.17 has no footer setting).
  API `pages` returns `build_type: workflow`; `github-pages` environment branch policy `v*` (tag).
- Result: the site went live on 2026-09-28 (oxy#29).

#### D41. The README is the landing page, the PyPI description and the site home page; it carries the summary line, uv install commands, badges and a trademark footer

- Implemented: `oxyscraper/README.md:1-30`; `oxyscraper/pyproject.toml:4-5`; `oxyscraper/assets/footer.html:1`.
- Badges (oxy#23, oxy#80): CI, Codecov, PyPI version, Python versions, typed, license, Ruff, uv, prek, pyrefly (text only, because shields.io has no pyrefly logo), Built with Claude Code.
  All 11 badge URLs returned 200 on 2026-10-05, and Codecov read 100% (oxy#80).

#### D42. A numpydoc `Returns` block starts with a `:` line, then the indented description

- Evidence: griffe 2.1.0 (pinned by great-docs) and Sphinx napoleon read a description-only `Returns` block as the return type (measured 2026-09-25).
  The `:` line keeps it a description (<https://github.com/mkdocstrings/griffe/blob/7c898a9685c8ac29e1a4fd7767e85bf830b75a58/docs/reference/docstrings.md?plain=1#L1357-L1368>). numpydoc says "The type of each return value is always required" (<https://github.com/numpy/numpydoc/blob/c6f5df5a77cc3022f688e3d92ebc0557dcabd484/doc/format.rst?plain=1#L245>), and numpydoc does not read annotations (<https://github.com/numpy/numpydoc/issues/196>). ruff 0.16.8 reports neither form.
- Implemented: `oxyscraper/CONTRIBUTING.md:176-177`; also in `~/.claude/CLAUDE.md` "Docstrings follow numpydoc".

#### D43. The CLI reference waits for a great-docs release that documents Typer apps

- Evidence: great-docs 0.17.0 documents Click only; Typer support merged on `main` on 2026-09-02 (<https://github.com/posit-dev/great-docs/pull/337>), unreleased as of oxy#57's close on 2026-10-05.
- Implemented: not built; recorded in oxy#56 "Docs" and oxy#57.

#### D44. Brand assets come from `_brand.yml` and `assets/` (PR oxy#53)

- Implemented: `oxyscraper/_brand.yml:1-26` (palette `midnight #0B0922`, `navy #130F35`, `purple #7E0EA7`, `pine #0B7064`, and nine more); `oxyscraper/assets/` holds favicons at 32, 180 and 512 px, a hex logo at 433, 866 and 1732 px, an SVG of each, and a social card.
  Epistole uses `assets/theme.css` instead (epistole memory `site-palette-via-theme-css.md`).

### A.8 Testing (oxy#23, oxy#56 "Testing Decisions")

#### D45. One seam: the HTTP transport, filled by a public fake; an autouse fixture guards every test

- Alternatives: RESPX or pytest-httpx (they do not intercept httpx2 requests, measured in `oxyscraper/docs/research/httpx2.md:165-167`); recorded cassettes (vcrpy).
- Evidence: pydantic-ai ships `TestModel` and `FunctionModel` and `Agent.override` for the same reason; the OpenAI and Anthropic SDKs ship no fake (oxy#23).
- Implemented: `oxyscraper/tests/conftest.py:9-13`; `oxyscraper.testing.FakeOxylabs`.

#### D46. Async tests run on asyncio and trio through anyio's pytest plugin, with trio's `MockClock(autojump_threshold=0)`

- Evidence (measured 2026-09-29, anyio 4.15.1): `await anyio.sleep(600)` returns at once and `anyio.current_time()` moves 600 s.
  A 0.5 s `to_thread.run_sync` inside `fail_after(600)` moves the clock 600 s, so a test that writes through worker threads runs on real time. anyio ships its own plugin, so no pytest-asyncio.
- Implemented: `oxyscraper/tests/conftest.py:16-21`.

#### D47. `tests/typing/` holds caller code with `assert_type` and `# E:` lines; a prek hook runs `pyrefly check --expectations` on it, and the normal check excludes it

- Evidence (measured 2026-09-29, pyrefly 1.3.1): with `# E: not assignable` on a failing line, `--expectations` exits 0; when the marked line has no error it exits 1.
- Implemented: `oxyscraper/prek.toml:122-130`; `oxyscraper/pyrefly.toml:1-3`.

#### D48. A weekly live suite runs outside `all-green`, in a `live` environment limited to `main`; missing credentials fail it (oxy#23, oxy#58, oxy#78)

- Alternatives: live tests under the required check (rejected: a fork's PR gets no secrets, so it would block every outside contribution, and a provider outage would block merges); skip on missing credentials (rejected: a silent skip hides a broken secret).
- Evidence: each run bills 11 results, about 50 a month; fault jobs, a rendered batch of 14 that returns 429, and a rejected payload bill nothing (oxy#78).
  The first run found that the API renamed its rate-limit headers between 2026-09-30 and 2026-10-01 (PR oxy#133). pytest printed a credentials fixture in a failed local test, so credentials and jobs got reprs that show nothing (oxy#78).
- Implemented: `oxyscraper/.github/workflows/live.yml:1-28` (cron `17 6 * * 3`, Wednesdays 06:17 UTC, plus `workflow_dispatch`; `environment: live`; `timeout-minutes: 30`); `oxyscraper/pyproject.toml:73,76` (`-m "not live"` and the `live` marker); `oxyscraper/tests/test_live.py:68-72` (`pytest.fail(f"the live suite needs ...")`); `oxyscraper/CONTRIBUTING.md:101-118`.
- Environment: `live` allows `main` only, no reviewers, no wait timer, secrets `OXY_WSA_USERNAME`, `OXY_WSA_PASSWORD`, `OXYLAKE_URI`; no repo-level secret (oxy#58, API `environments/live/secrets`).
  The values held no `$`, `\`, `#` or quote, so `gh secret set -f` copied each unchanged (oxy#58).
- Scope cut: oxy#131 dropped the drift checks of oxy#128 (value-set diffs, 15 billed `context` jobs, a `live-drift` issue step with `issues: write`) because Oxylabs' docs stopped listing sources.

#### D49. CLI tests run in-process through Typer's `CliRunner`

- Lesson: `typer.rich_utils` sets `FORCE_TERMINAL` at import when `GITHUB_ACTIONS`, `FORCE_COLOR` or `PY_COLORS` is set, so CLI asserts passed locally and failed on every CI job (PR oxy#124).
  Strip ANSI before asserting, and reproduce with `GITHUB_ACTIONS=true uv run pytest` (memory `typer-forces-color-in-ci.md`).
- Implemented: `oxyscraper/tests/test_cli.py` (`plain()` helper); `oxyscraper/tests/test_import.py:12-20` checks that `import oxyscraper` loads neither typer nor rich.

### A.9 Python versions

#### D50. Support every CPython that has not reached end of life; a version joins at its final release and leaves in the first release after end of life, in a `feat!:` commit

- Evidence: only pytest and Pydantic write a policy. pytest supports every version "actively maintained at the time of the release" (<https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/doc/en/backwards-compatibility.rst#L79-L96>).
  Pydantic drops a version at end of life with under 5% of downloads (<https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/docs/version-policy.md#L87-L92>).
  FastAPI, Pydantic, urllib3 and Polars each dropped their most recent version in a minor.
- Implemented: `oxyscraper/CONTRIBUTING.md:132-140`, listing the five places to raise: `requires-python`, `.python-version`, ruff `target-version`, `default_language_version` in `prek.toml`, and the `lowest` job's Python.
  Python 3.11 stays oxy's floor until its end of life in October 2027 (oxy#21).
- Free-threaded 3.14t was out of scope; pydantic-core 2.46.5 and obstore 0.11.1 publish `cp314t` wheels (oxy#21).

## Appendix B. oxyscraper#22, the resolution, verbatim

The maintainer's resolution comment of 2026-09-28 on [oxyscraper#22](https://github.com/ozanozbeker/oxyscraper/issues/22), the record that Epistole's `CONTRIBUTING.md:4` links.
Parts of it changed since; [Appendix A.0](#a0-status-under-the-unified-standard) lists what.

````markdown
## Resolution

This answer is the release standard for all of the maintainer's Python packages.
oxy is the reference repo, and its `CONTRIBUTING.md` writes the standard down.

**Versioning**

- Versions follow SemVer.
  Below 1.0, release-please sets `bump-minor-pre-major` and `bump-patch-for-minor-pre-major`, so a new minor always means a breaking change.
  A user can pin `oxyscraper~=0.3.0` and still get every feature and fix.
- Leaving `0.x` takes a `Release-As: 1.0.0` footer.
  The policy for after 1.0 is set at 1.0.
- Below 1.0, a break needs no deprecation period.
- oxy supports every CPython that has not reached its end of life.
  A version joins at its final release, and it leaves in the first release after its end of life, as a `feat!:` commit.
  The next CPython runs in CI from its first beta, in a job that may fail.
- Each dependency floor is as low as CI proves.
  A floor rises only in a `deps:` commit.

**Changelog and migration notes**

- release-please writes `CHANGELOG.md` and the GitHub release from conventional commits.
  `feat`, `fix`, `perf`, `docs`, `deps` and `revert` are visible, and `refactor`, `test`, `build`, `ci`, `style` and `chore` are hidden.
- A breaking PR carries a one-line `BREAKING CHANGE:` footer in its description, with a link to the upgrade page.
  The same PR writes the migration into that page, under the next minor's heading, such as `## 0.4`.

**Changes to `main`**

- Every change goes through a PR, the maintainer's included.
  `CLAUDE.md` tells agents the same.
- PRs merge by squash only, and the squash commit takes the PR's title and description.
- A ruleset on `main` requires a PR with no approvals, the `alls-green` check and the title check.
  It blocks force pushes and deletion, and the admin bypass applies to PRs only.
- The title check runs the `commit-msg` hook from `prek.toml` against the PR title.

**CI**

- Each PR runs the tests on Ubuntu, macOS and Windows, on every supported Python, against a non-editable install.
- Another job runs the floor Python with `uv sync --resolution lowest-direct`.
- pytest sets `filterwarnings = ["error"]`.
- A lint job runs `prek run --all-files`, and the pytest hook leaves `prek.toml`.
- The docs build runs on each PR and runs every example.
- One `re-actors/alls-green` job gathers the jobs, and it is the only required CI check.
- Dependabot updates `uv.lock` and the actions weekly, in groups, after a 7-day cooldown.
  The `uv` entry uses `increase-if-necessary` and the prefix `chore`, and the actions entry uses `ci`, so neither opens a release PR.
- A monthly workflow runs `prek update --freeze --cooldown-days 7` and opens a PR.
- Every action is pinned to a full SHA, and a repo setting requires it.
  Each workflow starts with `permissions: {}`, and each checkout sets `persist-credentials: false`.
- CodeQL default setup scans Python and Actions.

**Release**

- One GitHub App serves all the maintainer's package repos.
  `actions/create-github-app-token` v3 mints its token with `client-id`, narrowed to contents, pull requests and issues.
  Its private key is a secret in a `release` environment.
- `release-please.yml` runs on each push to `main` with the App token.
  It opens the release PR, and after the merge it creates the tag and the GitHub release.
- `release.yml` runs on `release: published`.
  It builds without a cache or OIDC, and checks that `py.typed` is in the wheel.
  It then publishes with `pypa/gh-action-pypi-publish`, which makes PEP 740 attestations.
  It runs no tests.
- The `pypi` environment accepts `v*` tags only and waits for the maintainer's approval, with self-review allowed.
- A tag ruleset lets only the App and the admin create `v*` tags.
- `extra-files` updates `uv.lock` through `$.package[?(@.name.value=='oxyscraper')].version`.
- There is no TestPyPI upload.

**Docs**

- great-docs builds the site, and GitHub Pages serves it at `ozanozbeker.com/oxyscraper`.
  It deploys on `release: published`, without a cache.
- Install commands use uv: `uv add oxyscraper`, and `uv tool install oxyscraper` for the CLI.
- The README is the landing page, the PyPI description and the site's home page.
- The PyPI summary, the GitHub description and the README's first line read `Unofficial Python library and CLI for the Oxylabs Web Scraper API.`
- The README and the site footer read `oxyscraper is not affiliated with or endorsed by Oxylabs. Oxylabs and Oxy are trademarks of Oxylabs.`
- A numpydoc `Returns` block is a `:` line, then the indented description.

**First upload**

- The pipeline is built next, in its own issue outside the map.
  Its first run publishes an empty `0.0.1`, marked `Development Status :: 1 - Planning`, to register `oxyscraper`.
- `bootstrap-sha` names the commit that adds release-please, so the research commits stay out of the changelog.
- `0.1.0` is the first real release.

## Why

- Only an App token lets a release PR run CI and lets a release start a workflow.
  The approval on `pypi` stops a leaked App key from publishing on its own.
- A required check gates only PRs, so a PR is the one route where CI runs before a change reaches `main`.
  `BEGIN_COMMIT_OVERRIDE` also works only through the PR that merged a commit.
- Without the title check, a PR titled `Update stuff` merges, and release-please skips it without a warning.
- The release PR runs the full matrix, and the ruleset blocks its merge until the matrix passes, so tests in `release.yml` would repeat it.
  Five of the six surveyed release workflows run no tests.
- Actions minutes are free on a public repo, and oxy writes local files and ships a CLI, so Windows is a real target.
- All six surveyed libraries write migration notes by hand.
  release-please keeps only a commit subject and one footer paragraph, and an edit to the release PR body is lost when `main` moves.
- A floor that tracks the lock forces every user onto the maintainer's versions.
- great-docs runs examples at build time and builds its changelog page from GitHub Releases.
  Material for MkDocs is in maintenance mode, and Zensical is an alpha.
- griffe 2.1.0, the version great-docs pins, reads a description-only `Returns` block as the return type (measured).
  The `:` line keeps the text a description.
- PyPI registers a name at the first upload only.
  An empty `0.0.1` registers it now and tests the pipeline on a version nobody installs.

The evidence is in [How do large Python libraries release to PyPI?](https://github.com/ozanozbeker/oxyscraper/issues/27) and [How do large Python libraries run CI, protect main and publish docs?](https://github.com/ozanozbeker/oxyscraper/issues/28).

## Facts for later tickets

- [Prototype: the CLI](https://github.com/ozanozbeker/oxyscraper/issues/19): great-docs 0.17 documents Click CLIs only, and its Typer support is on `main`, not released.
  Another framework needs a generated Markdown page for its reference.
- [What does oxy depend on, and what goes in extras?](https://github.com/ozanozbeker/oxyscraper/issues/21): each floor is as low as the lowest-direct job proves, and Python 3.11 stays the floor until its end of life in October 2027.
- [How is oxy tested, with and without spending credits?](https://github.com/ozanozbeker/oxyscraper/issues/23): CI runs the full matrix under one required `alls-green` check.
  Whether a live test sits under that check is open, and a fork's PR gets no secrets.
  No test runs in a commit hook.
````

## Appendix C. Repository settings and the ruleset JSON

oxyscraper's `CONTRIBUTING.md` held this list as "A new repo" until oxy#95 renamed it "Repository settings".
The steps below merge both versions with what `epistole#74`, `epistole#76` and this review found, in the order that works.
`R=ozanozbeker/<repo>`.

1. **Install the release App** on the repo.
   Its permissions: Contents, Issues and Pull requests read and write, Metadata read, nothing else.
   Generate a private key for this repo on the App's page, and keep no `.pem` on disk afterwards.
   A user token cannot read an App installation, so the first `release-please.yml` run is the check.
2. **`release` environment**: branch policy `main`, variable `APP_CLIENT_ID`, secret `APP_PRIVATE_KEY`.
   Only jobs in this environment read the key.
3. **`pypi` environment**: tag policy `v*`, the owner as required reviewer, self-review allowed, admin bypass off.

   ```bash
   gh api -X PUT repos/$R/environments/pypi --input - <<'EOF'
   {"wait_timer": 0, "prevent_self_review": false,
    "reviewers": [{"type": "User", "id": 139365132}],
    "can_admins_bypass": false,
    "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
   EOF
   gh api -X POST repos/$R/environments/pypi/deployment-branch-policies -f name='v*' -f type=tag
   gh api repos/$R/environments/pypi --jq '{can_admins_bypass, deployment_branch_policy}'
   ```

   The REST docs omit `can_admins_bypass`, but the API accepts it.
   If the `GET` still shows `true`, untick "Allow administrators to bypass configured protection rules" on the environment page.
4. **pypi.org trusted publisher** (a pending one for a new project): owner `ozanozbeker`, the repo, workflow `release.yml`, environment `pypi`.
   Check that the environment field is filled in: the reviewer only binds if PyPI requires the environment.
   A pending publisher does not reserve the name; only the first upload does.
5. **Pages**: source GitHub Actions; `github-pages` limited to tags `v*`; HTTPS enforced; the repo website set to the `https://` URL.

   ```bash
   gh api -X PUT repos/$R/pages -F https_enforced=true
   ```

   Set the repo description to the README's first line, which is also the PyPI summary.
6. **Merge settings**:

   ```bash
   gh api -X PATCH repos/$R -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
     -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY \
     -F allow_auto_merge=true -F delete_branch_on_merge=true
   ```

7. **Actions**:

   ```bash
   gh api -X PUT repos/$R/actions/permissions -F enabled=true -f allowed_actions=all -F sha_pinning_required=true
   gh api -X PUT repos/$R/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
   ```

8. **Security**:

   ```bash
   gh api -X PUT repos/$R/vulnerability-alerts
   gh api -X PUT repos/$R/automated-security-fixes
   gh api -X PUT repos/$R/private-vulnerability-reporting
   gh api -X PATCH repos/$R/code-scanning/default-setup -f state=configured -f query_suite=default \
     -f 'languages[]=actions' -f 'languages[]=python'
   ```

   Check that secret scanning and push protection read `enabled` under `security_and_analysis` in `gh api repos/$R`; all three repos have both on.
9. **Rulesets**, after `all-green` and `title` have run once on a PR, because a ruleset can require only a check that has already run.
   Copy them from Epistole:

   ```bash
   for id in 24262487 24262488; do
     gh api repos/ozanozbeker/epistole/rulesets/$id --jq '{name,target,enforcement,conditions,bypass_actors,rules}' \
       | gh api -X POST repos/$R/rulesets --input -
   done
   ```

10. **First release**: a PR whose description ends with `Release-As: 0.0.1`, then the release PR, then approve `pypi` on the `release.yml` run (Review deployments, tick `pypi`, Approve and deploy).
    Check one PEP 740 attestation per file on PyPI and the site over HTTPS.
11. **Optional live module**: a `live` environment limited to `main`, no reviewer, holding the live secrets.
    Keep no secret at repo level.

The two rulesets, as oxyscraper and Epistole hold them (field for field identical; Epistole's IDs are 24262487 and 24262488).
`actor_id: 5` with `RepositoryRole` is the admin role, `integration_id: 15368` is GitHub Actions, and `actor_id: 5110076` is the release App.

```json
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}},
  "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false, "required_reviewers": [], "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": false, "require_extra_approval_for_unattributed_changes": true, "allowed_merge_methods": ["squash"]}},
    {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false, "do_not_enforce_on_create": false, "required_status_checks": [{"context": "all-green", "integration_id": 15368}, {"context": "title", "integration_id": 15368}]}}
  ]
}
```

```json
{
  "name": "version tags",
  "target": "tag",
  "enforcement": "active",
  "conditions": {"ref_name": {"exclude": [], "include": ["refs/tags/v*"]}},
  "bypass_actors": [
    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"},
    {"actor_id": 5110076, "actor_type": "Integration", "bypass_mode": "always"}
  ],
  "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}]
}
```

dd's tier 1 rulesets, until tier 2 renames the checks and installs the App:

```bash
gh api -X POST repos/ozanozbeker/dagster-dataframely/rulesets --input - <<'EOF'
{"name": "main", "target": "branch", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
 "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
 "rules": [
  {"type": "deletion"}, {"type": "non_fast_forward"},
  {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false,
   "required_reviewers": [], "require_code_owner_review": false, "require_last_push_approval": false,
   "required_review_thread_resolution": false, "allowed_merge_methods": ["squash"]}},
  {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false, "do_not_enforce_on_create": false,
   "required_status_checks": [{"context": "test", "integration_id": 15368}, {"context": "lint", "integration_id": 15368},
                              {"context": "build", "integration_id": 15368}]}}]}
EOF
gh api -X POST repos/ozanozbeker/dagster-dataframely/rulesets --input - <<'EOF'
{"name": "version tags", "target": "tag", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
 "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
 "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}]}
EOF
```

A matrix job reports as `test (ubuntu-latest, 3.12)`, so tier 2 PR 3 switches the required checks to `all-green` and `title` after they run on that PR and before it merges.
Tier 2 PR 4 adds the App to the tag bypass with `{"actor_id": 5110076, "actor_type": "Integration", "bypass_mode": "always"}`.

## Appendix D. Traps

From oxyscraper's `CONTRIBUTING.md` "Traps":

- Never pass `release-type` to `release-please-action`; the action then ignores `release-please-config.json` with no warning.
- The `uv.lock` JSONPath reads `@.name.value`, not `@.name`: release-please parses each TOML value into an object.
- An edit to the release PR's body is lost when `main` moves before the merge, and never reaches `CHANGELOG.md`.
- `GITHUB_TOKEN` cannot run CI on a PR it opens, and a release it creates starts no workflow.
- The `pypi` and `github-pages` environments accept `v*` tags only, and both release workflows run on the release's tag.
- A numpydoc `Returns` block starts with a `:` line; griffe reads a bare description line as the type.

From oxyscraper's issues and project memory:

- `prek install` writes the absolute path of the `prek` that ran it into `.git/hooks`, which every worktree shares.
  Removing the worktree that ran it makes every commit fail with `prek: not found`.
  Run `prek install` from the main checkout only (oxy#60).
- A worktree under `.claude/worktrees/` is inside paths `.git/info/exclude` ignores, so the `pyrefly` hook matched no files and failed every commit.
- `prek run --all-files` checks only tracked files, so a new file skips ruff and pyrefly until `git add`.
- `uv sync --resolution lowest-direct` keeps a version from a lock it already resolved with `lowest-direct`, so a local floor bisect must restore the committed `uv.lock` before each run and print the installed version.
- Auto-merge merged a PR about 8 minutes after it opened, and a commit pushed a minute later missed it.
- rumdl's sentence-per-line reflow joins a sentence that starts with a lowercase word or a backtick onto the line before.
- great-docs copies only pages that `great-docs.yml` lists and folders whose name starts with `_`, so shared setup cells go in `user_guide/_includes/` (oxy#79).
- `typer.rich_utils` sets `FORCE_TERMINAL` at import when `GITHUB_ACTIONS` is set, so CLI asserts pass locally and fail in CI.
  Strip ANSI before asserting, and reproduce with `GITHUB_ACTIONS=true uv run pytest`.

Found in this review:

- gitleaks 8.30.1 exits 0 when `git log` fails on a shallow clone, so a CI scan must check that `HEAD^1` exists first.
- Adding `quarto` to the ruff-format hook without `extension = { qmd = "markdown" }` makes ruff parse every `.qmd` page as Python.
- `["--strict", "deps"]` as the commit-type list keeps only `feat`, `fix` and `deps`, so release-please's `chore(main): ...` title fails.
- `uv lock --upgrade --exclude-newer '7 days'` writes `exclude-newer-span` into `uv.lock`; a second plain `uv lock` removes it, or `uv lock --check` fails.
- An exact `[tool.uv] required-version` makes every Dependabot uv update fail once it differs from Dependabot's own uv (dependabot-core #13199).
- Without `day`, Dependabot's weekly slot appears to follow the weekday the config merged, not Monday.
- `actions/upload-pages-artifact` keeps its artifact for 1 day, so a deploy job that waits on an approval must build the site after the approval.
- A workflow run that names a missing environment creates it with no rules, so delete a job before its environment.
- The web form for auto-merge appears to save the squash title (plausible, not tested); `gh pr merge --auto --squash` without `--subject` sends none.
- release-please splits a squash body at a blank line followed by `fix:` or another type, and a `BREAKING CHANGE:` line anywhere in the body bumps the minor.
- release-please never writes a `## Unreleased` section and keeps one it finds above every new entry.
- The `typos` hook repo tags two series, so `prek update` pins `typos-dict-*` unless `[update] exclude_tags = ["typos-dict-*"]` is set.
- prek's `--enforce-all` large-files check fails a `uv.lock` above 500 KB on every commit that touches it.
- With rumdl's `flavor = "quarto"`, MD078 wants `#| label:` on every executable chunk, so sending `.qmd` pages to rumdl fails a package whose pages hold unlabelled `{python}` chunks (oxy#79).
- In `tests/typing/`, keep each `# E:` line short enough that `ruff format` does not split it, because a split moves the comment off the line that holds the error.
- `uvx <dist>` runs only a command named after the distribution, so a package whose command differs needs an alias entry point named after the distribution (oxyscraper shipped `oxy` and `oxyscraper`).

## Appendix E. oxyscraper files kept verbatim

### E.1 `live.yml`

The optional live module's workflow, as oxyscraper ran it.
A new copy adds `deployment: false` to the environment, a `concurrency` group and `--tb=short` (S6).

```yaml
name: Live

# The suite bills about 11 results, so it runs weekly instead of on each pull request (CONTRIBUTING.md).
on:
  schedule:
    - cron: "17 6 * * 3"
  workflow_dispatch:

permissions: {}

jobs:
  live:
    runs-on: ubuntu-latest
    environment: live
    timeout-minutes: 30
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
      - run: uv sync --locked --all-extras
      - run: uv run --no-sync pytest -m live
        env:
          OXY_WSA_USERNAME: ${{ secrets.OXY_WSA_USERNAME }}
          OXY_WSA_PASSWORD: ${{ secrets.OXY_WSA_PASSWORD }}
          OXYLAKE_URI: ${{ secrets.OXYLAKE_URI }}
```

The pytest side, from oxyscraper's `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = ["-ra", "--strict-config", "--strict-markers", "--import-mode=importlib", "-m", "not live"]
# A new upstream deprecation fails the Dependabot PR that brings it in, before the removal breaks oxy.
filterwarnings = ["error"]
markers = ["live: calls the Oxylabs API and bills the account, so only `-m live` selects it"]
testpaths = ["tests"]
xfail_strict = true
```

The CLI `-m live` comes after `addopts`' `-m "not live"`, and pytest keeps the last `-m`.
`tests/test_live.py` calls `pytest.fail` when a credential is missing, so a broken secret fails the run instead of skipping it, and its credential classes hide every field from `repr`.

### E.2 The `coverage` job

Replaced by C6 to C8; kept as the record of D20.

```yaml
  coverage:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          python-version: "3.14"
      # Editable, so the report names the files under `src/`, where Codecov finds them.
      - run: uv sync --locked --all-extras
      - run: uv run --no-sync coverage run -m pytest
      - run: uv run --no-sync coverage xml
      # Codecov only draws the badge and comments on pull requests, so a failed upload fails no check.
      - uses: codecov/codecov-action@303a32d7a59b442fa8d48b6a1cc6825c09c847a5 # v7.1.1
        continue-on-error: true
        with:
          use_oidc: true
      # After the upload, so Codecov's comment shows the missed lines of a pull request that fails here.
      - run: uv run --no-sync coverage report --fail-under=100
```

### E.3 The `dev` floor step

Dropped by U5; kept as the record of D25 and of F34's failure modes.

```yaml
      # `uv add` keeps an existing specifier, even with `--upgrade-package` or `--bounds`.
      - run: |
          python3 - <<'EOF'
          import re, tomllib
          from pathlib import Path

          pyproject = Path("pyproject.toml")
          locked = {}
          # uv.lock lists a name's versions in ascending order, so a lock split by Python keeps the lowest.
          for package in tomllib.loads(Path("uv.lock").read_text())["package"]:
              locked.setdefault(package["name"], package["version"])
          text = pyproject.read_text()
          for req in tomllib.loads(text)["dependency-groups"]["dev"]:
              # Only a plain floor changes, so extras, markers and upper bounds stay as written.
              if match := re.fullmatch(r"([\w.-]+)>=[\w.]+", req):
                  floor = locked[re.sub(r"[-_.]+", "-", match[1]).lower()]
                  text = text.replace(f'"{req}"', f'"{match[1]}>={floor}"')
          pyproject.write_text(text)
          EOF
          uv lock
```

### E.4 The typing tests

D47's hook and its `pyrefly.toml`, for a package with a `tests/typing/` folder.

```toml
  # Each line marked `# E:` must fail to type-check and every other line must pass, so the types a caller sees stay public API.
  {
    id = "pyrefly-typing",
    name = "pyrefly typing tests",
    entry = "uv run pyrefly check --expectations tests/typing/",
    language = "system",
    types = ["python"],
    pass_filenames = false,
  },
```

```toml
preset = "strict"
# `tests/typing/` holds lines that must fail, so only the `pyrefly-typing` hook checks it, with `--expectations`.
project-excludes = ["tests/typing"]
```

## Appendix F. Method

Three rounds of agents did the work on 2026-10-11 and 2026-10-12.

1. **Inventory**: one agent per repo read every CI file, config and GitHub setting; one copied oxyscraper's issues and research; one recorded GitHub settings and 100 runs per workflow; one rebuilt the history and diffed every shared file.
2. **Verification**: six agents tried to refute the claims this report rests on, each in a `git clone --local` copy, with sources at the pinned SHAs: hooks, uv and setup-uv, GitHub behaviour, Python versions, tests and coverage, and dagster-dataframely.
3. **Design**: three agents designed the standard from different priorities (fewest parts, no silent differences between copies, security), and a judge merged them into section 5.

Sources the report cites by name: prek v0.5.4, zizmor v1.30.1, conventional-pre-commit v4.4.0 (`91ab4bf`), gitleaks v8.30.1 (`83d9cd6`), setup-uv v10.2.0 (`c18668a`), uv 0.13.0, release-please v17.6.0, dependabot-core at `4725d25`, github/docs at `be38ec5` and `ec8a02f`, PEP 790, PEP 826 and the PEPs repo's `python-releases.toml`.
The scratch files behind this report, including full verbatim copies of oxy#22, #23, #27 and #28, were temporary and are not kept.

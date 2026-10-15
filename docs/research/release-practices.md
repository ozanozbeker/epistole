# How large Python libraries release to PyPI

This note records how six large Python libraries version, release and publish to PyPI, and how release-please behaves where oxy's release process depends on it.
It answers [#27](https://github.com/ozanozbeker/oxyscraper/issues/27) for [#22](https://github.com/ozanozbeker/oxyscraper/issues/22).
It covers FastAPI `0.141.1`, Pydantic `v2.13.5`, pytest `9.1.1`, attrs `26.1.0`, urllib3 `2.8.0` and Polars `py-1.44.2`.
It also covers three libraries that run release-please: lazycogs, descope's Python SDK and openai-python.
Each repo was read at its default branch on 2026-09-25, and [Sources](#sources) lists the commits.
The release-please source is read at `v17.6.0`, the version that `release-please-action` `v5.0.0` bundles, and the cited code is the same in the latest release, `v17.11.2`.
The measurements ran that day with release-please 17.6.0 from npm and uv 0.12.18, in throwaway folders outside the repo.

## Answer

- **Version schemes.**
  Four libraries are past 1.0 with major.minor.patch versions: pytest, Pydantic, urllib3 and Polars.
  FastAPI is still at `0.x`, and attrs uses CalVer.
  All four libraries past 1.0 have shipped a breaking change in a minor release.
- **The 0.x bump policy.**
  FastAPI puts breaking changes and features in the minor and fixes in the patch, which is release-please's `bump-minor-pre-major`.
  Polars before 1.0 put only breaking changes in the minor, which is `bump-minor-pre-major` plus `bump-patch-for-minor-pre-major`.
  With neither option, release-please turns a breaking change on `0.x` into `1.0.0`.
  Under `release-type: python`, a `docs:` commit on its own makes a patch release.
- **The first release.**
  `release-type: python` proposes `0.1.0` for a package with no release, and it never reads `initial-version`.
  Without `bootstrap-sha`, the first release notes list every `feat`, `fix`, `perf`, `deps`, `revert` and `docs` commit in the history.
- **Release notes.**
  The GitHub release body is the merged release PR's body, not `CHANGELOG.md`.
  An edit to that body reaches the release if no push to `main` comes between the edit and the merge, and it never reaches `CHANGELOG.md`.
  In lazycogs `0.7.0`, a maintainer's edit to `CHANGELOG.md` is missing from the GitHub release.
- **Correcting a commit message.**
  `BEGIN_COMMIT_OVERRIDE` goes in the body of the pull request that merged the commit.
  A commit pushed straight to `main` has no such pull request, so only a hand edit of the release PR can correct its entry.
- **Migration notes.**
  All six libraries write migration notes by hand, in a changelog section for breaking changes, a deprecations page or a migration guide.
  Polars publishes an upgrade guide with every breaking release.
  The changelog that release-please writes keeps each commit's subject and the first paragraph of a `BREAKING CHANGE:` footer, and it drops the commit body.
- **Tokens.**
  None of the six libraries has cut a release with a GitHub App token.
  With `GITHUB_TOKEN`, the first CI run on pytest's `9.1.1` release PR ended as `action_required`, and pytest's tag pushes started no workflows.
  An App token lets CI run on the release PR at once and lets the release start a publish workflow.
- **`uv.lock`.**
  The Python strategy never updates `uv.lock`, which records oxy's own version, so a release PR fails `uv lock --check` (measured).
  An `extra-files` entry of type `toml` with the JSONPath `$.package[?(@.name.value=='oxyscraper')].version` updates that line (measured).
  Both lazycogs and descope use the same entry, and descope added it after a release PR failed CI.
- **The publish job.**
  `pypa/gh-action-pypi-publish` makes PEP 740 attestations by default.
  `uv publish` uploads attestations but does not create them.
  FastAPI since `0.128.1`, pydantic-core, lazycogs and descope run `uv publish` with no attestation step, and PyPI has no provenance for their files.
  PyPI does not support trusted publishing from a reusable workflow.
  PyPI, the PyPA action and uv's guide all build in a separate job that has no `id-token: write`.
- **The `pypi` environment.**
  PyPI calls a GitHub environment optional but strongly recommended.
  Four libraries require a maintainer's approval: pytest, Pydantic, urllib3 and Polars.
  All four let the person who started the run approve it.
  FastAPI, attrs and descope set no rules, and openai-python and lazycogs only limit which branches and tags can deploy.
- **TestPyPI.**
  Both attrs and urllib3 upload a dev build to TestPyPI on every push to `main`.
  No other library surveyed uses TestPyPI.
- **Supported Python.**
  Only pytest and Pydantic write down a policy.
  In pytest, each release supports every Python version still maintained at the time.
  Pydantic drops a version once it has reached its end of life and has under 5% of downloads.
  FastAPI, Pydantic, urllib3 and Polars each dropped their most recent Python version in a minor release.

## Versioning and the 0.x policy

| Library | Scheme | Stated policy |
| --- | --- | --- |
| FastAPI | `0.x` | Breaking changes and features in the minor, fixes in the patch |
| Pydantic | major.minor.patch | No intentional breaking change in a V2 minor |
| pytest | SemVer | Breaking changes only in a major, after a deprecation |
| attrs | CalVer, `YY.N.0` | A year of `DeprecationWarning` before a break, "if possible" |
| urllib3 | major.minor.patch | None written |
| Polars | SemVer since 1.0 | Breaking changes only in a major |

- SemVer calls `0.y.z` initial development, where "Anything MAY change at any time", and suggests bumping the minor for each release ([SemVer][semver]).
- FastAPI's docs put breaking changes and new features in minor versions, and bug fixes and non-breaking changes in patch versions ([`versions.md`][fa-versions]).
  They tell users to pin a minor, such as `>=0.112.0,<0.113.0`.
- Polars' policy before 1.0 read: "breaking releases lead to a minor version increase (e.g. from `0.18.15` to `0.19.0`), while all other releases increment the patch version" ([`versioning.md` before 1.0][pl-versioning-pre1]).
  Since 1.0, breaking changes lead to a major, and features and performance work to a minor ([`versioning.md`][pl-versioning]).
- attrs numbers releases by year and release count, and the third number exists only for emergency branches ([`CHANGELOG.md`][at-calver]).
- Each library past 1.0 has shipped a breaking change in a minor release:
  - pytest `8.4.0` dropped Python 3.8 under "Removals and backward incompatible breaking changes" ([changelog][pt-cl-38]).
  - Pydantic `2.8.0` marks two entries `**Breaking Change:**` ([`HISTORY.md`][pd-history-28]).
  - urllib3 `2.6.0` removed `getheaders()`, and `2.6.1` restored it ([`CHANGES.rst`][u3-changes-26]).
  - Polars `1.31.0` has a "Breaking changes" section that removes the old streaming engine ([release][pl-131]).

## Deprecation and supported Python versions

- **pytest** removes deprecated features only in a major, after at least two minor releases of warnings ([policy][pt-bc-deprecation]).
  A true breakage must add porting examples to `doc/en/deprecations.rst` ([policy][pt-bc-breakage]).
  Each release supports every Python version that is "actively maintained at the time of the release" ([policy][pt-bc-python]).
  It dropped 3.8 in `8.4.0` and 3.9 in `9.0.0`, both filed as breaking changes ([`8.4.0`][pt-cl-38], [`9.0.0`][pt-cl-39]).
- **Pydantic** keeps deprecated features until V3 ([version policy][pd-policy]).
  It drops a Python version once the version has reached its end of life and under 5% of downloads of the latest minor use it ([version policy][pd-policy-python]).
  It dropped 3.9 in `2.14.0a1`, a minor ([`HISTORY.md`][pd-history-39]).
- **Polars** removes a deprecated feature two breaking releases after the deprecation ([`versioning.md`][pl-deprecation]).
  It has no written Python policy, and it dropped 3.9 in `1.37.0` under "Enhancements" ([release][pl-137]).
- **attrs** supports only its latest release ([`SECURITY.md`][at-security]).
  It has no written Python policy.
  Its changelog lists the 3.7 drop as a backwards-incompatible change and has no entry for the 3.8 drop ([`CHANGELOG.md`][at-cl-37]).
- **urllib3** has no written versioning or Python policy.
  `2.7.0` dropped Python 3.9 and moved every scheduled removal to 3.0 ([`CHANGES.rst`][u3-changes-27]).
- **FastAPI** has no written deprecation or Python policy.
  It dropped 3.9 in `0.129.0` under "Breaking Changes" ([release notes][fa-notes-39]).

## Changelogs and migration notes

| Library | Changelog tool | File | Migration notes |
| --- | --- | --- | --- |
| FastAPI | The `latest-changes` App adds each merged PR's title | `docs/en/docs/release-notes.md` | A "Breaking Changes" section per release, and how-to pages |
| Pydantic | GitHub's generated notes by PR label, edited by hand | `HISTORY.md` | A `**Breaking Change:**` prefix, and `docs/migration.md` |
| pytest | towncrier | `doc/en/changelog.rst` | `breaking` and `deprecation` sections, and `deprecations.rst` |
| attrs | towncrier | `CHANGELOG.md` | A "Backwards-incompatible Changes" section |
| urllib3 | towncrier, edited by hand | `CHANGES.rst` | Removal sections and `caution` blocks, and `v2-migration-guide.rst` |
| Polars | release-drafter, from PR titles and labels | None | An upgrade guide per breaking release |

- A person writes every migration note in all six libraries.
  FastAPI's maintainers move bot-written entries under a "Breaking Changes" heading by hand ([commit][fa-breaking-edit]).
  Pydantic's release steps ask the maintainer to mark breaking changes in `HISTORY.md` ([`release/README.md`][pd-release-readme]).
- Polars states: "Polars releases an upgrade guide alongside each breaking release" ([upgrade guides][pl-upgrade]).
  The guide for 2.0 already exists for its release candidate.
- FastAPI, Pydantic, pytest and urllib3 copy the changelog section into the GitHub release body.
  In attrs, a maintainer writes the release body by hand, with the section inside it.
  Polars keeps no changelog file, so its GitHub releases are the changelog.
- Both pytest and attrs configure towncrier fragment types for breaking changes and deprecations ([pytest][pt-towncrier], [attrs][at-towncrier]).

## Cutting a release

| Library | Version source | Tag | GitHub release | Token |
| --- | --- | --- | --- | --- |
| FastAPI | A workflow edits `__init__.py` in a PR | Created when a maintainer publishes the draft | A workflow drafts it from the release notes | A PAT for the PR, `GITHUB_TOKEN` for the draft |
| Pydantic | A local script edits `version.py` | A local script pushes it | The script drafts it, and a maintainer publishes it | The maintainer's own `gh` login |
| pytest | setuptools-scm, from a `workflow_dispatch` input | The workflow pushes it after the upload | The workflow creates it from the changelog | `GITHUB_TOKEN` |
| attrs | hatch-vcs, from the tag | A maintainer pushes a signed tag | A maintainer writes it | `GITHUB_TOKEN` |
| urllib3 | hatch-vcs, from the tag | A maintainer pushes a signed tag | The workflow drafts it empty, and a maintainer fills it | `GITHUB_TOKEN` |
| Polars | Hand edits to eight files | Created when the workflow publishes the draft | release-drafter drafts it from PR titles | `GITHUB_TOKEN` |

- In FastAPI and attrs, a person publishes the GitHub release, and that event starts the PyPI upload.
  A release that a person publishes starts workflows like any other event.
  FastAPI depends on that: `create-draft-release.yml` drafts with `GITHUB_TOKEN`, and `publish.yml` runs on `release: published` ([draft][fa-draft], [publish][fa-publish]).
- pytest and Polars upload to PyPI before the tag exists ([pytest `deploy.yml`][pt-deploy], [Polars `release-python.yml`][pl-release]).
  Pydantic's script pushes the tag before the release PR merges ([`push.py`][pd-push]).
- FastAPI opened its release PRs with the PAT `FASTAPI_LATEST_CHANGES` up to `0.141.1` ([`prepare-release.yml`][fa-pat]).
  On 2026-08-08 it switched to `tiangolo/pr-submit`, which trades the job's OIDC token for a GitHub App token, and no release has used it yet ([commit][fa-pr-submit]).
- urllib3 protects the creation, update and deletion of tags with two active rulesets (rulesets API), and its release template asks for a signed tag ([template][u3-release-template]).

## Publishing

### Trusted publishing and reusable workflows

- All six libraries and all three release-please users publish with trusted publishing, and no workflow passes an API token.
  Polars switched from an API token in 2023 ([commit][pl-trusted]).
- PyPI's docs state that a reusable workflow cannot be the workflow in a trusted publisher, and the tracking issue is open ([troubleshooting][pypi-troubleshooting], [warehouse#11096][wh-11096]).
- PyPI looks up the publisher by the file named in the `job_workflow_ref` claim, and it requires that file to sit in the publishing repository ([lookup][wh-lookup], [check][wh-job-workflow-ref]).
  For a job inside a reusable workflow, that claim names the reusable workflow ([OIDC reference][gh-oidc]).
  A reusable workflow kept in another repository therefore never matches.
- `pypa/gh-action-pypi-publish` emits a warning when `workflow_ref` and `job_workflow_ref` differ, and it continues ([`oidc-exchange.py`][ghapp-reusable]).
  Its README recommends a top-level workflow that calls the reusable one and publishes from a job of its own ([README][ghapp-readme-reusable]).
- None of the nine libraries publishes from a reusable workflow.
  A release process shared across repos can therefore put the build in a reusable workflow, but the publish job stays in each repo's own workflow file.

### Attestations

- `pypa/gh-action-pypi-publish` `v1.14.2` generates and uploads PEP 740 attestations by default, through trusted publishing to PyPI or TestPyPI only ([`action.yml`][ghapp-attestations], [README][ghapp-readme-attestations]).
- PyPI's docs name that action as the easy way, and `twine upload --attestations` as the manual way ([producing attestations][pypi-producing]).
  They do not mention `uv publish`.
- `uv publish` has supported trusted publishing since 0.4.16 ([changelog][uv-cl-0416]).
  Since 0.9.12 it uploads a `<file>.publish.attestation` beside each distribution, unless `--no-attestations` is set ([changelog][uv-cl-0912], [CLI][uv-cli-attest]).
  Since 0.12.10 it revokes the short-lived PyPI token after publishing, even when the upload fails ([changelog][uv-cl-01210], [package guide][uv-package-tp]).
- `uv publish` does not generate attestations ([package guide][uv-package-attest]).
  The uv GitHub guide runs `astral-sh/attest-action` `v0.0.6` before `uv publish` ([GitHub guide][uv-github]).
  That action calls itself early-stage, with breaking changes possible in any release ([README][attest-readme]).
- On PyPI, the files of the latest release carry provenance for pytest, attrs, urllib3, Polars, Pydantic and openai-python (PyPI simple API).
  The files of FastAPI since `0.128.1`, pydantic-core `2.49.0`, lazycogs `0.7.0` and descope `2.14.0` carry none.
  All four upload with `uv publish` and no attestation step.
  FastAPI's provenance stopped when it replaced the PyPA action with `uv publish` ([commit][fa-uv-publish]).
- pytest and attrs also create GitHub build provenance through `hynek/build-and-inspect-python-package` ([pytest][pt-deploy], [attrs][at-pypi-package]).
  In urllib3, a commit removed the SLSA provenance, and its changelog entry points to PyPI's attestations instead ([commit][u3-slsa]).

### Job layout

- PyPI recommends one dedicated workflow, which it suggests naming `release.yml`, with `id-token: write` set at job level ([security model][pypi-security-workflow], [using a publisher][pypi-using-perms]).
- PyPI, the PyPA action and uv's guide all recommend a build job without `id-token: write` and a publish job that only downloads and uploads ([security model][pypi-security-scope], [README][ghapp-readme-separate], [GitHub guide][uv-github]).
  Six libraries follow that split: pytest, attrs, urllib3, Polars, Pydantic and openai-python.
  FastAPI, descope and lazycogs build and publish in one job.
- The release-please users publish in two ways:
  - descope and openai-python add jobs to the release-please workflow that run only when the action reports a release ([descope][ds-workflow], [openai-python][oa-release-job]).
    Those jobs run on the push to `main`, so `GITHUB_REF` is `refs/heads/main`.
  - lazycogs publishes from a separate workflow on `release: published` ([`publish-pypi.yml`][lc-publish]).
    Its `GITHUB_REF` is the tag ([events reference][gh-events-release]), and it runs because an App token, not `GITHUB_TOKEN`, created the release.

### The publishing environment

- PyPI calls an environment optional but strongly recommended, and names it `pypi` in its examples ([adding a publisher][pypi-adding], [using a publisher][pypi-using]).
  Its security model suggests required reviewers ([security model][pypi-security-env]).
- GitHub offers four rules on an environment ([environments reference][gh-env]):
  - required reviewers, up to six users or teams, where one approval is enough;
  - "prevent self-review", which stops the person who started the run from approving it;
  - a wait timer of 1 to 43,200 minutes;
  - a list of branches and tags that can deploy, matched against `GITHUB_REF`.
- On the Free plan, all four work only in public repositories.
  Admins can bypass the rules unless the environment turns that off.
- The environments API returns these rules:

| Library | Environment | Reviewers | Self-review | Branches and tags | Admin bypass |
| --- | --- | --- | --- | --- | --- |
| pytest | `deploy` | Team `core` | Allowed | `[0-9].[0-9].x`, `release-*` | Yes |
| Pydantic | `release` | Two teams | Allowed | Any | No |
| urllib3 | `publish` | Team `maintainers` | Allowed | Any | Yes |
| Polars | `release-python` | One user | Allowed | `main`, `1.x`, `release/*` | No |
| attrs | `release-pypi` | None | Not applicable | Any | Yes |
| openai-python | `publish` | None | Not applicable | `main` | Yes |
| lazycogs | `pypi-release` | None | Not applicable | `main`, tags `v*` | Yes |
| descope | `pypi` | None | Not applicable | Any | Yes |

- FastAPI's publish job uses no environment.
- A maintainer approved their own run for Pydantic `v2.13.5` and pytest `9.1.1` (approvals API).
  For urllib3 `2.8.0`, one maintainer pushed the tag and another approved.
- PyPI also suggests tag protection for tag-triggered publishing ([security model][pypi-security-tags]).
  The GitHub page it links to now redirects to rulesets, and a ruleset's bypass list can include a GitHub App ([rulesets][gh-rulesets]).

### TestPyPI

- attrs uploads a dev build of every push to `main` to TestPyPI, from environment `release-test-pypi` ([`pypi-package.yml`][at-pypi-package]).
- urllib3 does the same from environment `testpypi`, which allows `main`, `1.26.x` and tags `*.*.*` ([`publish.yml`][u3-publish]).
- Both pass `repository-url: https://test.pypi.org/legacy/` to the PyPA action, and TestPyPI shows attestations for both.
- TestPyPI needs its own trusted publisher ([using a publisher][pypi-using-testpypi]).

## release-please in Python libraries

Three maintained libraries run `googleapis/release-please-action` with a GitHub App token and publish with trusted publishing.

| | lazycogs `0.7.0` | descope `2.14.0` | openai-python `3.19.2` |
| --- | --- | --- | --- |
| Build backend | `uv_build` | `uv_build` | hatchling |
| Options below 1.0.0 | Neither | Both | `bump-minor-pre-major` |
| `uv.lock` | `toml` extra-file | `toml` extra-file | Generic extra-file and a marker comment |
| Token | App, `create-github-app-token` `v2.0.6` | App, `v3.2.0` with `app-id` | App, `v3.2.0` with `client-id` and `permission-*` inputs |
| Publish trigger | `release: published`, in its own workflow | The release-please workflow | The release-please workflow |
| Upload | `uv publish` | `uv publish` | PyPA action |
| Attestations | None | None | Yes |

- Each release PR changes at least the manifest, `CHANGELOG.md`, `pyproject.toml` and `uv.lock`, and the App's `app/<slug>` account authors it ([lazycogs #84][lc-84], [descope #1678][ds-1678], [openai-python #3951][oa-3951]).
- descope sets `permissions: {}` for the workflow, gives the release-please job `contents: read`, and does every write with the App token ([`release-please.yml`][ds-workflow]).
- openai-python splits the work into three jobs ([`create-releases.yml`][oa-release-job]):
  - `release` has `permissions: {}`, runs in environment `release`, and narrows the App token to `contents`, `issues` and `pull-requests` write;
  - `build` has `contents: read` and no OIDC;
  - `publish` has only `id-token: write`, runs in environment `publish`, and uploads with the PyPA action.
- Two other users handle `uv.lock` differently:
  - open-feature's Python SDK sets both options below 1.0.0 and `bootstrap-sha` ([config][of-config]).
    Its release PR for `0.10.0` left `uv.lock` at `0.9.0`, which its CI missed because it runs `uv sync --frozen` ([#602][of-602]).
  - workos-python runs `uv lock` in a second job and pushes the result to the release branch ([`release-please.yml`][wo-uvlock]).
    Another job copies the `CHANGELOG.md` section into the GitHub release ([`release-please.yml`][wo-body]).

## How release-please behaves

### The action and the library

- `release-please-action` `v5.0.0` bundles release-please `17.6.0` ([`package-lock.json`][rpa-lock]).
  The `v5` tag points to the same commit, and the latest library release is `17.11.2`.
  A fix in the library reaches the action only through a new action release.
- The action creates releases first and release PRs second ([`index.ts`][rpa-main]).
  While a merged release PR still has no release, release-please opens no new release PR ([`manifest.ts`][rp-abort]).

### Where the GitHub release body comes from

- After a release PR merges, the next run lists merged PRs that carry the `autorelease: pending` label ([`manifest.ts`][rp-merged-prs], [labels][rp-labels]).
- `buildRelease` parses each PR's body with `PullRequestBody.parse`, and uses the notes it finds as the release body ([`base.ts`][rp-build-release]).
  `createRelease` sends them to GitHub as `body` ([`github-api.ts`][rp-create-release]).
- The notes are the lines between the first and the last line that reads `---` ([`pull-request-body.ts`][rp-split-body]).
  For one package, they must start with a `## x.y.z` or `## [x.y.z]` heading ([`pull-request-body.ts`][rp-single-release]).
- Measured: a hand-written section and a `---` rule inside the notes both stay in the parsed notes.
  Text above the version heading makes the parse return no release, and `buildRelease` then creates the release with an empty body.
- The run after the merge reads the PR body from GitHub, so an edit made before the merge reaches the release.
  `CHANGELOG.md` is a file in the PR's commit, so the edit does not change it.
- Each run rebuilds the release PR, and it rewrites the PR whenever the new body differs from the current one ([`manifest.ts`][rp-maybe-update]).
  An edited body always differs, so a push to `main` before the merge discards the edit.
  The rewrite force-pushes the release branch ([`github.ts`][rp-force-push]), which also drops commits pushed to it by hand.
- An edit to `CHANGELOG.md` does not reach the release either.
  In lazycogs `0.7.0`, a maintainer committed a clearer `CHANGELOG.md` entry to the release PR, and the GitHub release kept the generated line ([#84][lc-84], [release][lc-release], [`CHANGELOG.md`][lc-changelog]).
- The action's `body` output is the created release's body ([`index.ts`][rpa-outputs]), although the README says it is "extracted from the CHANGELOG.md" ([README][rpa-readme-body]).

### Correcting a merged commit message

- The override goes in the body of the merged pull request, between `BEGIN_COMMIT_OVERRIDE` and `END_COMMIT_OVERRIDE` ([README][rp-readme-override]).
- On its next run, release-please uses the text between the markers in place of the whole commit message ([`commit.ts`][rp-override]).
  The text can hold several conventional commits, separated by blank lines ([`commit.ts`][rp-split-messages]).
  The rebuilt release PR then carries the corrected entries in both its body and `CHANGELOG.md`.
- release-please finds each commit's pull request through GitHub's `associatedPullRequests` ([`github.ts`][rp-assoc]).
  A commit pushed straight to `main` has none, so no override can apply to it.
- The README states that the override does not work with plain merges, and it recommends squash merges.

### The first release

- `release-type: python` proposes `0.1.0` when no release exists ([`python.ts`][rp-python-initial]).
  The Python strategy overrides `initialReleaseVersion()` and never reads `initial-version`, which only the base strategy reads ([`base.ts`][rp-base-initial]).
  The schema lists `initial-version` for every strategy ([`config.json`][rp-schema-initial]).
- The manifest sets where counting starts.
  `{".": "0.0.0"}` marks the package as unreleased ([`manifest.ts`][rp-manifest-fallback]).
  Any other version counts as the last release when no tag matches it, so `{".": "0.1.0"}` makes the first release a bump from `0.1.0`, such as `0.1.1` or `0.2.0`.
- A `Release-As: x.y.z` footer, or `release-as` in the config, forces a version ([`base.ts`][rp-build-new-version], [README][rp-readme-release-as]).
  The schema marks the config option deprecated in favour of the footer ([`config.json`][rp-schema-release-as]).
- With no release to stop at, release-please reads back up to 500 commits ([`manifest.ts`][rp-commit-depth]).
  `bootstrap-sha` stops that walk at the named commit and leaves that commit out ([`manifest.ts`][rp-bootstrap], [manifest docs][rp-docs-bootstrap]).
  Once the first release PR has merged, release-please ignores it.
- The Python strategy shows `docs` commits in the changelog ([`python.ts`][rp-python-sections]).
  Without `bootstrap-sha`, oxy's first release notes would list each research commit under "Documentation".

### Bumps below 1.0.0

- By default, a breaking change bumps the major, a `feat` bumps the minor and anything else bumps the patch, below 1.0.0 too ([`default.ts`][rp-default-versioning]).
- `bump-minor-pre-major` moves a breaking change on `0.x` to the minor, and `bump-patch-for-minor-pre-major` moves a `feat` to the patch ([`config.json`][rp-schema-bumps]).
- Measured from `0.2.0`:

| Options | `feat!:` | `feat:` | `docs:` |
| --- | --- | --- | --- |
| Neither | `1.0.0` | `0.3.0` | `0.2.1` |
| `bump-minor-pre-major` | `0.3.0` | `0.3.0` | `0.2.1` |
| Both | `0.3.0` | `0.2.1` | `0.2.1` |

- With `bump-minor-pre-major` alone, a breaking release and a feature release get the same bump, as in FastAPI's policy.
  With both options, a feature release and a fix release get the same bump, as in Polars' policy before 1.0.
- With `bump-minor-pre-major`, no commit type reaches `1.0.0`, so leaving `0.x` takes a `Release-As: 1.0.0` footer.
- The Python strategy lists `docs` as a visible section, so a `docs:` commit alone opens a release PR ([`python.ts`][rp-python-sections], [README][rp-readme-units]).
- `prerelease: true` marks every `0.x` GitHub release as a prerelease ([`manifest.ts`][rp-draft-options]).

### What reaches the changelog

- Each entry is a commit subject, because release-please blanks the commit body before it renders the notes ([`default.ts`][rp-notes-body]).
- A `!` after the type, or a `BREAKING CHANGE:` footer, adds an entry under "⚠ BREAKING CHANGES".
- The footer's text ends at its first blank line ([`commit.ts`][rp-post-process]).
  Its lines join into one paragraph, until a line starts with a fourth-level heading (`####`) or a list bullet, which keeps the rest as Markdown.
- Measured: this commit renders the footer's first two lines and its two bullets, and it drops the body and the last paragraph.

  ```text
  feat!: rename Client.fetch to Client.get

  This body text explains the change.

  BREAKING CHANGE: `Client.fetch` is now `Client.get`.
  Replace every call site.
  - `fetch(url)` becomes `get(url)`
  - `fetch_many` becomes `get_many`

  A second paragraph of migration notes.
  ```

- A migration note longer than one paragraph and a list therefore needs a docs page or a hand edit of the release PR body.

### `draft` and `force-tag-creation`

- `draft: true` creates the GitHub release as a draft ([`config.json`][rp-schema-draft]).
- GitHub creates no tag for a draft until someone publishes it.
  When it looks for the last release, release-please skips releases without a tag commit ([`github-api.ts`][rp-release-filter]), so the next release PR starts from the wrong place.
- `force-tag-creation: true` creates the tag through the Git refs API before the release, and it ignores a tag that already exists ([`github-api.ts`][rp-create-release]).
  It arrived in release-please 17.2.0 ([changelog][rp-changelog-force-tag]), so `release-please-action` `v5` has it.
- GitHub starts no workflow for the `created` event of a draft, and publishing the draft fires `published` ([events reference][gh-events-release]).
- The action sets `release_created` to `true` for a draft too ([`index.ts`][rpa-outputs]).
  A publish job keyed on that output runs before anyone publishes the draft.

### `uv.lock`

- The Python strategy updates `CHANGELOG.md`, `pyproject.toml`, `setup.py`, `setup.cfg`, any `version.py`, and an `__init__.py` that assigns `__version__` ([`python.ts`][rp-python-updates]).
  Nothing in release-please updates `uv.lock`, and the request for it is open ([#2561][rp-issue-2561]).
- oxy's `uv.lock` records the project's own version in its `oxyscraper` entry.
  Measured after a version bump in `pyproject.toml` alone:
  - `uv lock --check` and `uv run --locked` exit 1, and oxy's `uv-lock` prek hook runs the first;
  - a plain `uv run` exits 0 and rewrites the version line in `uv.lock`, which leaves the working tree changed.
- Measured with release-please 17.6.0: this `extra-files` entry changes the version line and nothing else, and `uv lock --check` passes afterwards.

  ```json
  {
    "type": "toml",
    "path": "uv.lock",
    "jsonpath": "$.package[?(@.name.value=='oxyscraper')].version"
  }
  ```

- The filter needs `.value`, because the TOML updater parses each value into an object that holds its position and its value ([`toml-edit.ts`][rp-toml-edit]).
  Measured: `@.name=='oxyscraper'` matches nothing, and release-please logs "No entries modified".
- Both lazycogs and descope use the same entry ([lazycogs][lc-config], [descope][ds-config]).
  The descope SDK added it after its release PR failed `uv sync --locked` in every CI job ([#1518][ds-1518]).
- openai-python lists `uv.lock` as a generic extra-file and keeps a `# x-release-please-version` comment on the version line ([config][oa-config], [`uv.lock`][oa-uvlock]).
  Measured: `uv lock` keeps the comment when nothing changes, but `uv add` rewrites the file without it.
- Pydantic, which bumps its version with a script, runs `uv lock -P pydantic` right after the bump ([`release/README.md`][pd-release-readme]).

## `GITHUB_TOKEN` against a GitHub App token

`release-please-action`'s `token` input defaults to `github.token` ([`action.yml`][rpa-action]).
A token from `actions/create-github-app-token` changes six things.

- **CI runs on the release PR without approval.**
  A pull request that `GITHUB_TOKEN` opens or updates starts `pull_request` runs in an approval-required state ([triggering a workflow][gh-trigger]).
  The pytest `9.1.1` release PR shows it: the first `test` run, started by `github-actions[bot]`, ended as `action_required` ([run][pt-run]).
  With an App token, the runs start at once (same page).
  The release-please-action README still says such a PR starts no workflows at all ([README][rpa-readme-creds]).
- **The release can start a publish workflow.**
  Apart from `workflow_dispatch`, `repository_dispatch` and those `pull_request` runs, an event that `GITHUB_TOKEN` causes starts no run ([triggering a workflow][gh-trigger]).
  The pytest release workflow pushes its tags with `GITHUB_TOKEN`, and tags `9.1.0` and `9.1.1` started no runs, although `test.yml` runs on tag pushes ([`test.yml`][pt-test-yml], runs API).
  In lazycogs, the App creates each release, and the `release: published` workflow runs for each one ([`publish-pypi.yml`][lc-publish]).
- **One repository setting no longer applies.**
  "Allow GitHub Actions to create and approve pull requests" is off by default in a new personal repository, and it applies to `GITHUB_TOKEN` only ([repository settings][gh-repo-actions]).
- **The workflow's `permissions:` no longer limit release-please.**
  `permissions:` sets the scopes of `GITHUB_TOKEN` only ([workflow syntax][gh-syntax]).
  An App token carries the installation's permissions, and the action's `permission-*` inputs can narrow them ([README][cgat-permissions]).
  The release-please-action README lists `contents`, `issues` and `pull-requests` write ([README][rpa-readme-perms]).
- **The release PR's author changes.**
  `GITHUB_TOKEN` shows `github-actions[bot]`, and an App token shows `app/<slug>`, as in the three release-please users above.
- **The token works in one job only.**
  It expires after one hour, and the action revokes it when the job ends, so a later job cannot use it ([README][cgat-expiry], [how it works][cgat-how]).

`create-github-app-token` `v3` takes `client-id`, and `app-id` still works but is deprecated ([`action.yml`][cgat-action], [README][cgat-client-id]).

## Open questions

- **Self-review under an App token is unmeasured.**
  GitHub's docs say "prevent self-review" stops "users who initiate a deployment" from approving it.
  They do not say who initiates a run that an App-created release starts, so whether the rule blocks a sole maintainer is open for [#22](https://github.com/ozanozbeker/oxyscraper/issues/22).
- **A reusable workflow in the same repository is untested.**
  PyPI's code compares the file named in `job_workflow_ref` with the publisher, so a publisher that names a reusable file in the same repository might match.
  PyPI's docs and the PyPA action call every reusable workflow unsupported, so how to share a publish job across repos stays a design choice for #22.
- **`draft` with `force-tag-creation` is untested end to end.**
  Whether the tag that release-please creates through the API starts a tag-push workflow under an App token is unmeasured, and it matters only if #22 picks a draft and a tag trigger.
- **The start of oxy's first changelog is a choice for #22.**
  Without `bootstrap-sha`, every `docs:` commit since the repo began appears in the first release notes.
- **The attestation route is a choice for #22.**
  The PyPA action attests by default, and `uv publish` needs `astral-sh/attest-action`, which is at `v0.0.6` and early-stage.

## Sources

These files come from release-please at tag `v17.6.0` (commit `712fcf0`):

- `src/strategies/python.ts` holds [the changelog sections][rp-python-sections], [the files it updates][rp-python-updates] and [the initial version][rp-python-initial].
- `src/strategies/base.ts` holds [the base initial version][rp-base-initial], [`buildNewVersion`][rp-build-new-version] and [`buildRelease`][rp-build-release].
- `src/manifest.ts` holds [the labels][rp-labels], [the search depths][rp-commit-depth], [the bootstrap stop][rp-bootstrap], [the manifest fallback][rp-manifest-fallback], [the abort on an untagged merge][rp-abort], [the PR rewrite][rp-maybe-update], [the merged PR search][rp-merged-prs] and [the `draft` and `prerelease` options][rp-draft-options].
- `src/github-api.ts` holds [the release filter][rp-release-filter] and [`createRelease`][rp-create-release], and `src/github.ts` holds [the PR lookup][rp-assoc] and [the force-push][rp-force-push].
- `src/commit.ts` holds [the override][rp-override], [the message split][rp-split-messages] and [the note parsing][rp-post-process].
- [`src/changelog-notes/default.ts`][rp-notes-body], [`src/versioning-strategies/default.ts`][rp-default-versioning] and [`src/util/toml-edit.ts`][rp-toml-edit] build the notes, the bumps and the TOML edits.
- `src/util/pull-request-body.ts` holds [`splitBody`][rp-split-body] and [the single-release parse][rp-single-release].
- `schemas/config.json` describes [the bump options][rp-schema-bumps], [`release-as`][rp-schema-release-as], [`draft` and `force-tag-creation`][rp-schema-draft] and [`initial-version`][rp-schema-initial].
- The README covers [`Release-As`][rp-readme-release-as], [the override][rp-readme-override] and [releasable units][rp-readme-units], and [the manifest docs][rp-docs-bootstrap] cover bootstrapping.
- [The changelog][rp-changelog-force-tag] dates `--force-tag` to 17.2.0, and [#2561][rp-issue-2561] requests `uv.lock` support.

These files come from `release-please-action` at tag `v5.0.0` (commit `45996ed`):

- [`action.yml`][rpa-action], [`src/index.ts`][rpa-main] with [its outputs][rpa-outputs], and [`package-lock.json`][rpa-lock].
- The README sections on [credentials][rpa-readme-creds], [permissions][rpa-readme-perms] and [the `body` output][rpa-readme-body].

These sources cover tokens and publishing:

- `actions/create-github-app-token` at `v3.2.0` (commit `bcd2ba4`): [`action.yml`][cgat-action], and the README on [expiry][cgat-expiry], [`client-id`][cgat-client-id], [permissions][cgat-permissions] and [how it works][cgat-how].
- `pypa/gh-action-pypi-publish` at `v1.14.2` (commit `dc37677`): [`action.yml`][ghapp-attestations], [`oidc-exchange.py`][ghapp-reusable], and the README on [reusable workflows][ghapp-readme-reusable], [separate jobs][ghapp-readme-separate] and [attestations][ghapp-readme-attestations].
- PyPI's docs, which [docs.pypi.org][pypi-docs] builds from `pypi/warehouse` at commit `02dae5a`: [troubleshooting][pypi-troubleshooting], [adding a publisher][pypi-adding], [using a publisher][pypi-using] with [permissions][pypi-using-perms] and [TestPyPI][pypi-using-testpypi], the security model on [the workflow][pypi-security-workflow], [the environment][pypi-security-env], [tags][pypi-security-tags] and [job scope][pypi-security-scope], and [producing attestations][pypi-producing].
- PyPI's publisher code in the same commit: [the lookup][wh-lookup] and [the `job_workflow_ref` check][wh-job-workflow-ref], plus [warehouse#11096][wh-11096].
- uv at `0.12.19` (commit `bea1384`): the package guide on [trusted publishing][uv-package-tp] and [attestations][uv-package-attest], [the GitHub guide][uv-github], [the CLI][uv-cli-attest], and the changelogs for [0.4.16][uv-cl-0416], [0.9.12][uv-cl-0912] and [0.12.10][uv-cl-01210].
- `astral-sh/attest-action` at `v0.0.6` (commit `f589a42`): [the README][attest-readme].
- GitHub's docs, read on 2026-09-25: [triggering a workflow][gh-trigger], [environments][gh-env], [repository settings][gh-repo-actions], [workflow syntax][gh-syntax], [the `release` event][gh-events-release], [OIDC claims][gh-oidc] and [rulesets][gh-rulesets].
- [SemVer 2.0.0][semver].

These files come from the six libraries at their default branches:

- FastAPI at commit `50113da` and tag `0.141.1`: [`versions.md`][fa-versions], [the release notes][fa-notes-39], [`create-draft-release.yml`][fa-draft], [`publish.yml`][fa-publish], [the PAT][fa-pat], and the commits that [edit a breaking entry][fa-breaking-edit], [adopt `uv publish`][fa-uv-publish] and [adopt PR Submit][fa-pr-submit].
- Pydantic at commit `a9a0e1d`: [the version policy][pd-policy] with [its Python rule][pd-policy-python], [`release/README.md`][pd-release-readme], [`release/push.py`][pd-push], and `HISTORY.md` for [2.8.0][pd-history-28] and [2.14.0a1][pd-history-39].
- pytest at commit `8721173`: the policy on [deprecation][pt-bc-deprecation], [breakage][pt-bc-breakage] and [Python][pt-bc-python], the changelog for [8.4.0][pt-cl-38] and [9.0.0][pt-cl-39], [towncrier types][pt-towncrier], [`deploy.yml`][pt-deploy], [`test.yml`][pt-test-yml] and [the `action_required` run][pt-run].
- attrs at commit `8f76777`: [`CHANGELOG.md`][at-calver], [`SECURITY.md`][at-security], [towncrier types][at-towncrier] and [`pypi-package.yml`][at-pypi-package].
- urllib3 at commit `ed0ed07`: `CHANGES.rst` for [2.6.0][u3-changes-26] and [2.7.0][u3-changes-27], [the release template][u3-release-template], [`publish.yml`][u3-publish] and [the SLSA removal][u3-slsa].
- Polars at commit `efba0b7`: [`versioning.md`][pl-versioning] with [its deprecation rule][pl-deprecation], [the policy before 1.0][pl-versioning-pre1], [upgrade guides][pl-upgrade], [`release-python.yml`][pl-release], [the trusted publishing commit][pl-trusted], and the releases [1.31.0][pl-131] and [1.37.0][pl-137].

These files come from the release-please users:

- lazycogs at commit `ca203a9`: [the config][lc-config], [`publish-pypi.yml`][lc-publish], [#84][lc-84], [the `0.7.0` release][lc-release] and [`CHANGELOG.md` at the merge][lc-changelog].
- descope at commit `fed0075`: [the config][ds-config], [`release-please.yml`][ds-workflow], [#1518][ds-1518] and [#1678][ds-1678].
- openai-python at commit `6e4a79c`: [the config][oa-config], [`uv.lock`][oa-uvlock], [`create-releases.yml`][oa-release-job] and [#3951][oa-3951].
- open-feature at commit `fe9a0d1`: [the config][of-config] and [#602][of-602].
- workos-python at commit `83af6f5`: [the `uv lock` job][wo-uvlock] and [the release body job][wo-body].

The provenance and environment facts come from PyPI's simple and integrity APIs and GitHub's environments, runs and approvals APIs, read on 2026-09-25.

[rp-python-sections]: https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/python.ts#L31-L44
[rp-python-updates]: https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/python.ts#L52-L157
[rp-python-initial]: https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/python.ts#L200-L202
[rp-base-initial]: https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/base.ts#L744-L750
[rp-build-new-version]: https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/base.ts#L543-L574
[rp-build-release]: https://github.com/googleapis/release-please/blob/v17.6.0/src/strategies/base.ts#L635-L718
[rp-labels]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L289-L290
[rp-commit-depth]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L293-L294
[rp-bootstrap]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L657-L666
[rp-manifest-fallback]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L704-L729
[rp-abort]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L928-L936
[rp-maybe-update]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L1089-L1102
[rp-merged-prs]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L1142-L1171
[rp-draft-options]: https://github.com/googleapis/release-please/blob/v17.6.0/src/manifest.ts#L1196-L1206
[rp-release-filter]: https://github.com/googleapis/release-please/blob/v17.6.0/src/github-api.ts#L559-L563
[rp-create-release]: https://github.com/googleapis/release-please/blob/v17.6.0/src/github-api.ts#L662-L695
[rp-assoc]: https://github.com/googleapis/release-please/blob/v17.6.0/src/github.ts#L357-L386
[rp-force-push]: https://github.com/googleapis/release-please/blob/v17.6.0/src/github.ts#L795-L806
[rp-override]: https://github.com/googleapis/release-please/blob/v17.6.0/src/commit.ts#L456-L469
[rp-split-messages]: https://github.com/googleapis/release-please/blob/v17.6.0/src/commit.ts#L388-L403
[rp-post-process]: https://github.com/googleapis/release-please/blob/v17.6.0/src/commit.ts#L316-L369
[rp-notes-body]: https://github.com/googleapis/release-please/blob/v17.6.0/src/changelog-notes/default.ts#L76-L111
[rp-default-versioning]: https://github.com/googleapis/release-please/blob/v17.6.0/src/versioning-strategies/default.ts#L66-L105
[rp-toml-edit]: https://github.com/googleapis/release-please/blob/v17.6.0/src/util/toml-edit.ts#L21-L35
[rp-split-body]: https://github.com/googleapis/release-please/blob/v17.6.0/src/util/pull-request-body.ts#L95-L115
[rp-single-release]: https://github.com/googleapis/release-please/blob/v17.6.0/src/util/pull-request-body.ts#L155-L170
[rp-schema-bumps]: https://github.com/googleapis/release-please/blob/v17.6.0/schemas/config.json#L15-L22
[rp-schema-release-as]: https://github.com/googleapis/release-please/blob/v17.6.0/schemas/config.json#L53-L56
[rp-schema-draft]: https://github.com/googleapis/release-please/blob/v17.6.0/schemas/config.json#L65-L72
[rp-schema-initial]: https://github.com/googleapis/release-please/blob/v17.6.0/schemas/config.json#L253-L256
[rp-readme-release-as]: https://github.com/googleapis/release-please/blob/v17.6.0/README.md#L104-L116
[rp-readme-override]: https://github.com/googleapis/release-please/blob/v17.6.0/README.md#L118-L138
[rp-readme-units]: https://github.com/googleapis/release-please/blob/v17.6.0/README.md#L140-L151
[rp-docs-bootstrap]: https://github.com/googleapis/release-please/blob/v17.6.0/docs/manifest-releaser.md#L74-L103
[rp-changelog-force-tag]: https://github.com/googleapis/release-please/blob/v17.6.0/CHANGELOG.md#L71-L76
[rp-issue-2561]: https://github.com/googleapis/release-please/issues/2561
[rpa-action]: https://github.com/googleapis/release-please-action/blob/v5.0.0/action.yml#L5-L8
[rpa-main]: https://github.com/googleapis/release-please-action/blob/v5.0.0/src/index.ts#L136-L152
[rpa-outputs]: https://github.com/googleapis/release-please-action/blob/v5.0.0/src/index.ts#L186-L217
[rpa-lock]: https://github.com/googleapis/release-please-action/blob/v5.0.0/package-lock.json#L5130-L5132
[rpa-readme-creds]: https://github.com/googleapis/release-please-action/blob/v5.0.0/README.md#L92-L117
[rpa-readme-perms]: https://github.com/googleapis/release-please-action/blob/v5.0.0/README.md#L119-L131
[rpa-readme-body]: https://github.com/googleapis/release-please-action/blob/v5.0.0/README.md#L196
[cgat-action]: https://github.com/actions/create-github-app-token/blob/v3.2.0/action.yml#L8-L15
[cgat-expiry]: https://github.com/actions/create-github-app-token/blob/v3.2.0/README.md#L15-L16
[cgat-client-id]: https://github.com/actions/create-github-app-token/blob/v3.2.0/README.md#L351-L356
[cgat-permissions]: https://github.com/actions/create-github-app-token/blob/v3.2.0/README.md#L400-L402
[cgat-how]: https://github.com/actions/create-github-app-token/blob/v3.2.0/README.md#L428-L437
[ghapp-attestations]: https://github.com/pypa/gh-action-pypi-publish/blob/v1.14.2/action.yml#L83-L88
[ghapp-reusable]: https://github.com/pypa/gh-action-pypi-publish/blob/v1.14.2/oidc-exchange.py#L269-L284
[ghapp-readme-reusable]: https://github.com/pypa/gh-action-pypi-publish/blob/v1.14.2/README.md#L33-L39
[ghapp-readme-separate]: https://github.com/pypa/gh-action-pypi-publish/blob/v1.14.2/README.md#L94-L99
[ghapp-readme-attestations]: https://github.com/pypa/gh-action-pypi-publish/blob/v1.14.2/README.md#L108-L131
[pypi-docs]: https://docs.pypi.org/trusted-publishers/
[pypi-troubleshooting]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/troubleshooting.md#L7-L11
[pypi-adding]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/adding-a-publisher.md#L39-L44
[pypi-using]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/using-a-publisher.md#L24-L39
[pypi-using-perms]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/using-a-publisher.md#L63-L71
[pypi-using-testpypi]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/using-a-publisher.md#L73-L85
[pypi-security-workflow]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/security-model.md#L94-L109
[pypi-security-env]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/security-model.md#L128-L140
[pypi-security-tags]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/security-model.md#L142-L147
[pypi-security-scope]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/trusted-publishers/security-model.md#L149-L159
[pypi-producing]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/docs/user/attestations/producing-attestations.md#L22-L117
[wh-lookup]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/warehouse/oidc/models/github.py#L216-L240
[wh-job-workflow-ref]: https://github.com/pypi/warehouse/blob/02dae5a1510bf9ba3fc5ff9ec0d94440055d92ec/warehouse/oidc/models/github.py#L67-L97
[wh-11096]: https://github.com/pypi/warehouse/issues/11096
[uv-package-tp]: https://github.com/astral-sh/uv/blob/0.12.19/docs/guides/package.md#L133-L144
[uv-package-attest]: https://github.com/astral-sh/uv/blob/0.12.19/docs/guides/package.md#L177-L203
[uv-github]: https://github.com/astral-sh/uv/blob/0.12.19/docs/guides/integration/github.md#L346-L432
[uv-cli-attest]: https://github.com/astral-sh/uv/blob/0.12.19/crates/uv-cli/src/lib.rs#L7823-L7828
[uv-cl-0416]: https://github.com/astral-sh/uv/blob/0.12.19/changelogs/0.4.x.md#L605
[uv-cl-0912]: https://github.com/astral-sh/uv/blob/0.12.19/changelogs/0.9.x.md#L477-L486
[uv-cl-01210]: https://github.com/astral-sh/uv/blob/0.12.19/CHANGELOG.md#L247
[attest-readme]: https://github.com/astral-sh/attest-action/blob/v0.0.6/README.md#L20-L29
[gh-trigger]: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow
[gh-env]: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments
[gh-repo-actions]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#preventing-github-actions-from-creating-or-approving-pull-requests
[gh-syntax]: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions
[gh-events-release]: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release
[gh-oidc]: https://docs.github.com/en/actions/reference/security/oidc
[gh-rulesets]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository#granting-bypass-permissions-for-your-branch-or-tag-ruleset
[semver]: https://semver.org/spec/v2.0.0.html
[fa-versions]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/docs/en/docs/deployment/versions.md#L7-L57
[fa-notes-39]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/docs/en/docs/release-notes.md#L876-L880
[fa-draft]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/create-draft-release.yml#L3-L54
[fa-publish]: https://github.com/fastapi/fastapi/blob/50113da16fec53b66b80d75e80a89296de4fa5a5/.github/workflows/publish.yml#L3-L37
[fa-pat]: https://github.com/fastapi/fastapi/blob/0.141.1/.github/workflows/prepare-release.yml#L64
[fa-breaking-edit]: https://github.com/fastapi/fastapi/commit/31d097f286b63c2c7bc9954aa605571e0f3d1e15
[fa-uv-publish]: https://github.com/fastapi/fastapi/commit/b4ba7f46522352cf7ae7c74a9030a35679da3491
[fa-pr-submit]: https://github.com/fastapi/fastapi/commit/5cd0678fb60e9ee645c32578b439923a1aa17829
[pd-policy]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/docs/version-policy.md#L13-L15
[pd-policy-python]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/docs/version-policy.md#L87-L92
[pd-release-readme]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/release/README.md#L10-L27
[pd-push]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/release/push.py#L81-L84
[pd-history-28]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/HISTORY.md#L1622-L1647
[pd-history-39]: https://github.com/pydantic/pydantic/blob/a9a0e1d1f7805a1b7cc5b5d42e862594a570cf74/HISTORY.md#L156-L172
[pt-bc-deprecation]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/doc/en/backwards-compatibility.rst#L19-L25
[pt-bc-breakage]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/doc/en/backwards-compatibility.rst#L47-L50
[pt-bc-python]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/doc/en/backwards-compatibility.rst#L79-L96
[pt-cl-38]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/doc/en/changelog.rst#L868-L880
[pt-cl-39]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/doc/en/changelog.rst#L660-L674
[pt-towncrier]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/pyproject.toml#L570-L632
[pt-deploy]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/workflows/deploy.yml#L3-L136
[pt-test-yml]: https://github.com/pytest-dev/pytest/blob/8721173580390a9d297e5af06cac3f0b6841f425/.github/workflows/test.yml#L3-L20
[pt-run]: https://github.com/pytest-dev/pytest/actions/runs/27818252525
[at-calver]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/CHANGELOG.md#L3-L9
[at-cl-37]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/CHANGELOG.md#L134-L139
[at-security]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/SECURITY.md#L5-L15
[at-towncrier]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/pyproject.toml#L318-L331
[at-pypi-package]: https://github.com/python-attrs/attrs/blob/8f767776326faaed11e6c2974798787f6e19b343/.github/workflows/pypi-package.yml#L4-L82
[u3-changes-26]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/CHANGES.rst#L241-L289
[u3-changes-27]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/CHANGES.rst#L181-L189
[u3-release-template]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/PULL_REQUEST_TEMPLATE/release.md#L4-L19
[u3-publish]: https://github.com/urllib3/urllib3/blob/ed0ed075c6b93f7c515ebd3abe9a7248507ef8c5/.github/workflows/publish.yml#L3-L111
[u3-slsa]: https://github.com/urllib3/urllib3/commit/65d7b5fdc332f9f51aad2f119fae683eb080919d
[pl-versioning]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/docs/source/development/versioning.md#L5-L10
[pl-deprecation]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/docs/source/development/versioning.md#L95-L101
[pl-versioning-pre1]: https://github.com/pola-rs/polars/blob/ea086d6af4fad255fece8a5f06410a3aade89633/docs/development/versioning.md#L5-L7
[pl-upgrade]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/docs/source/releases/upgrade/index.md#L3-L7
[pl-release]: https://github.com/pola-rs/polars/blob/efba0b7b8348a703a3ed16b6bf45d12a5ac995ef/.github/workflows/release-python.yml#L378-L441
[pl-trusted]: https://github.com/pola-rs/polars/commit/eb21a23e4ccd79b7a407cd747839ac8b85196600
[pl-131]: https://github.com/pola-rs/polars/releases/tag/py-1.31.0
[pl-137]: https://github.com/pola-rs/polars/releases/tag/py-1.37.0
[lc-config]: https://github.com/developmentseed/lazycogs/blob/ca203a9326f58b4b73457be1ed456d8f8c3ed1f1/release-please-config.json#L1-L14
[lc-publish]: https://github.com/developmentseed/lazycogs/blob/ca203a9326f58b4b73457be1ed456d8f8c3ed1f1/.github/workflows/publish-pypi.yml#L3-L33
[lc-84]: https://github.com/developmentseed/lazycogs/pull/84
[lc-release]: https://github.com/developmentseed/lazycogs/releases/tag/v0.7.0
[lc-changelog]: https://github.com/developmentseed/lazycogs/blob/747e138c746975477e727b8de8103c1827a214a6/CHANGELOG.md#L3-L9
[ds-config]: https://github.com/descope/python-sdk/blob/fed0075b45c19fe8161a8e496d49d0d4cabbee40/release-please-config.json#L1-L27
[ds-workflow]: https://github.com/descope/python-sdk/blob/fed0075b45c19fe8161a8e496d49d0d4cabbee40/.github/workflows/release-please.yml#L1-L57
[ds-1518]: https://github.com/descope/python-sdk/pull/1518
[ds-1678]: https://github.com/descope/python-sdk/pull/1678
[oa-config]: https://github.com/openai/openai-python/blob/6e4a79cc8c7e640e7ac4be710db32fe20b1020f2/release-please-config.json#L6-L64
[oa-uvlock]: https://github.com/openai/openai-python/blob/6e4a79cc8c7e640e7ac4be710db32fe20b1020f2/uv.lock#L1536-L1539
[oa-release-job]: https://github.com/openai/openai-python/blob/6e4a79cc8c7e640e7ac4be710db32fe20b1020f2/.github/workflows/create-releases.yml#L7-L87
[oa-3951]: https://github.com/openai/openai-python/pull/3951
[of-config]: https://github.com/open-feature/python-sdk/blob/fe9a0d133f812c924822901ee2313ae5f85dc242/release-please-config.json#L1-L11
[of-602]: https://github.com/open-feature/python-sdk/pull/602
[wo-uvlock]: https://github.com/workos/workos-python/blob/83af6f53ba6456a7c03c0cef1b3fcc80b3da91c4/.github/workflows/release-please.yml#L51-L83
[wo-body]: https://github.com/workos/workos-python/blob/83af6f53ba6456a7c03c0cef1b3fcc80b3da91c4/.github/workflows/release-please.yml#L177-L213

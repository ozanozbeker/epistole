# Issue tracker: GitHub

This repo tracks issues and PRDs as GitHub issues.
Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`.
  Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`.
  Filter the comments with `jq`, and fetch the labels too.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`.
  Add the `--label` and `--state` filters the task needs.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`.
`gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(`/triage` reads this flag: set it to `yes` if this repo treats external PRs as feature requests.)_

When the flag is `yes`, triage PRs with the same labels and states as issues.
Use the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`.
  Then keep only PRs whose `authorAssociation` is `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE`.
  Drop `OWNER`/`MEMBER`/`COLLABORATOR`.
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either.
Resolve it with `gh pr view 42` first.
If that fails, run `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

`/wayfinder` uses this section.
The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`.
  Its body holds the Notes / Decisions-so-far / Fog sections.
  Create it with `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue.
  Link it with `gh api` on the sub-issues endpoint.
  Where sub-issues aren't enabled, add the child to a task list in the map body.
  Then put `Part of #<map>` at the top of the child body.
  Label it `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`).
  Claiming a ticket assigns it to the driving dev.
- **Blocking**: use GitHub's **native issue dependencies**.
  They are the canonical, UI-visible representation.
  Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`.
  `<blocker-db-id>` is the blocker's numeric **database id**, _not_ the `#number` or `node_id`.
  Get it with `gh api repos/<owner>/<repo>/issues/<n> --jq .id`.
  GitHub reports `issue_dependencies_summary.blocked_by`, which counts only open blockers.
  That count is the current blocking state.
  Where dependencies aren't available, put a `Blocked by: #<n>, #<n>` line at the top of the child body instead.
  A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children with `gh issue list --state open`, scoped to the map's sub-issues / task list.
  Drop any child that has an assignee or an open blocker.
  An open blocker shows as `issue_dependencies_summary.blocked_by > 0`, or as an open issue in the `Blocked by` line.
  Take the first remaining child in map order.
- **Claim**: `gh issue edit <n> --add-assignee @me`.
  Make it the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`.
  Then append a context pointer (gist + link) to the map's Decisions-so-far.

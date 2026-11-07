# PRD: Dashboard delivery backflow (CI history and Delivery card, ported from minespel)

> Status: approved · 2026-11-07 · by user in chat · Owner: product-manager · Backlog: Unplanned → "Dashboard delivery backflow"

## Problem
A real project (minespel) grew the template dashboard with delivery metrics and a release-table roadmap. Branch `claude/dashboard-backflow-from-minespel` ported them back, but without a PRD (docs/policies/prd-approval.md applies to template tooling) and 41 commits before today's main. Since the fork, main rebuilt `scripts/dashboard.py`: Roadmap v2 (global sequence, Next up, PRD badge) and the observability tabs (Decisions, Gates, Flow with deploy frequency and change failure rate, Cost, and others). A straight merge would collide and duplicate. The need that is still unmet on main is: CI pass rate and CI time are not visible anywhere, and the Tech debt register only reads one list format.

## Goal and success measure
Traceability: no agreed docs/GOAL.md yet (phase `brainstorm`); same stand-in as dashboard-roadmap-v2 (a factory where delivery health is visible without chat; async-delivery policy). Success: opening the dashboard, the user sees how healthy CI is (pass rate, time, recent failures, weekly trend) without running anything, and a project that keeps tech debt as a table still sees it.

## Users and user stories
- As the product owner, I want CI pass rate, CI minutes and recent failures on the dashboard so that I can tell if delivery is healthy.
- As the product owner, I want a weekly trend so that I see if it is getting better or worse.
- As a project owner who keeps TECH-DEBT.md as a table, I want it counted so that the debt numbers are right.

## Scope
Decision per branch feature, judged against current main:

| Feature | Decision | Reason |
|---|---|---|
| CI history via `ci_runs.py` | Keep | Nothing on main covers CI runs; this is the real gap. |
| Delivery card, weekly bars | Adapt | Keep CI runs and pass-rate bars. Drop deploys-per-week bars: the Flow tab already shows deploy frequency and failure rate. |
| Release cadence (CHANGELOG or tags) | Adapt | Small, useful, new. Show count, gaps, days since last release inside the Delivery card. Tags already read by main (`versions()`); add CHANGELOG as the first source. |
| Ranked backlog table, Now/Then/Later | Drop (defer) | Competes with Roadmap v2's global numbered sequence. Only release-style projects need it. Revisit if the user says so (question 3). |
| Plan task chips | Drop (defer) | Depends on the ranked table and a PLAN.md the template does not ship. |
| Refactor rounds | Drop (defer) | Same dependency; tags already place work in the foundation lane. |
| Lane overrides config | Drop | `#tags` already decide the lane on main; a config duplicates it. |
| Pipe-safe table parsing | Adapt | Needed only for the debt table, so port the cell splitter and nothing more. |
| Table-form TECH-DEBT | Keep | Real projects use it; additive to the list format. Major counts as high. |
| Open-decisions tile | Drop | The Decisions tab on main already shows ADR status. |
| Phone CSS | Drop | Main already has phone rules and generated tabs. Only add stacked-table styling if the new card needs it. |

Slices:
1. CI history and Delivery card (`ci_runs.py`, `metrics/ci-runs.json`, card on Overview, SUMMARY.md CI line, CI step, docs).
2. Table-form TECH-DEBT with pipe-safe cells.
3. Deferred, not in this PRD: ranked backlog and its dependents.

## Non-goals
- The Now/Then/Later roadmap, plan chips, refactor rounds, lane overrides (see table).
- Any change to Roadmap v2, the observability tabs or their data.json fields (additive only).
- JavaScript, or any network use by `dashboard.py`: the page builder stays offline and reads the cache file.
- Charts of deploys (Flow tab owns them) or minespel-specific panels.
- Fetching CI data from anything but GitHub Actions.

## Acceptance criteria
1. Given `metrics/ci-runs.json` with runs, when the dashboard is built, then the Delivery card shows pass rate (last 30 decided runs), pass rate on the production branch, median and p90 CI minutes, and the last failures with links; cancelled and skipped runs are not counted as decided.
2. Given those runs span several weeks, when rendered, then SVG bars show runs and pass rate per week for the last 8 ISO weeks; a week with no decided run shows "no data", not 0%.
3. Given the file is missing or not valid JSON, when built, then the card says "no CI history yet" and the build does not fail.
4. Given a CHANGELOG.md with `## 1.2.0 (date)` or `## [1.2.0] - date` headings, when built, then the card shows release count, median gap and days since the last release; given no CHANGELOG, then tags are used; given neither, the line is omitted.
5. Given `python3 scripts/dashboard.py` runs, then it makes no network call and `--print` adds at most one CI line.
6. Given `scripts/ci_runs.py` with no GitHub repo resolvable, then it exits non-zero with a clear message and writes nothing; given a repo value that is not `owner/name`, then it refuses before any request.
7. Given a fetch error after at least one page succeeded, then the pages already fetched are written; given a failure on page 1, nothing is overwritten.
8. Given TECH-DEBT.md as a table (`Id | Severity | Item | Where | Size | Source | Status`), when parsed, then open/done, severity (major counts as high), size and area are read; a `|` inside a code span or `\|` does not shift columns; the checklist format still parses unchanged.
9. Given titles or messages containing HTML, then output is escaped and valid; the page works without JavaScript.
10. Given the suite, when `python3 scripts/metrics.py test` runs, then it passes with tests for ACs 1-8; `bash scripts/check.sh` passes.
11. Given the CI workflow, when read, then the refresh step is `continue-on-error`, does not block the build, and permissions meet the security notes below.

## UX / behaviour notes
- The Delivery card sits on Overview next to the existing deploy tile and links to Flow for deploy detail.
- Empty and error states are quiet sentences, never blank panels.
- `metrics/ci-runs.json` is a git-ignored cache, safe to refresh or delete.

## Security notes (checked against docs/policies/security.md)
- `ci_runs.py` is the only network call: one HTTPS GET to `api.github.com`, read-only, hard-coded host. The token is sent only to that host.
- CI job gets `actions: read` plus `contents: read`, set at job level. Policy "CI least privilege" says top-level `contents: read`, widen per job only when needed: this complies. The job token is short-lived and is not a deploy credential, so "no deploy credentials in pull_request jobs" holds. Pass the token via `env:`, never inline.
- Untrusted input: `github_repo` and the origin URL feed the request URL, so validate `owner/name` (letters, digits, `.`, `_`, `-`) before use. Runs data is written with a fixed key whitelist and escaped on render.
- Policy "docs must not promise more than the code enforces": docs say the page builder is offline, and `ci_runs.py` is the single exception.
- Not in scope but noted: `actions/checkout@v4` is not SHA-pinned, as the policy asks; log in TECH-DEBT.md, do not fix here.

## Risks and assumptions
- Riskiest: the CI log is only meaningful in a real GitHub repo; the template itself has few runs. Test cheaply on the template repo's own Actions and on one downstream project.
- The public API allows 60 calls per hour without a token; two pages per build is fine.
- `dashboard.py` is already large; the architect should decide where the card lives (a module under `scripts/obs/` is preferred over growing the file).
- Assumption: minespel's metric definitions (30 decided runs, p90) suit other projects.

## Effort and sequencing
- Overall M. Slice 1 M (script, parser, card, CI step, docs), slice 2 S. Swimlane: technical foundation. No dependencies; do not merge the branch.
- Port notes: treat the branch as a reference. Take `scripts/ci_runs.py` almost as-is (add the repo-name check and the AC 7 behaviour), plus the metric, changelog and bar helpers and their tests from the diff. Re-implement against current main (Roadmap v2 render, `scripts/obs/` layout, `TABS` list). Do not take the branch's `roadmap()`/`render_roadmap()` changes, its factory.json `dashboard` block (except `github_repo`, `changelog_file`), or its README/LEARNINGS wording as written. Resolve `docs/INDEX.md` and the knowledge graph by regenerating. Add `metrics/ci-runs.json` to .gitignore and the `ci_runs.py` line to README and the dashboard skill.

## Decisions (user, 2026-11-07)
1. Show CI pass rate and time: yes. 2. One read-only GitHub call in CI: yes. 3. Now/Then/Later roadmap: no. 4. Table-form tech debt: yes. 5. Drop the rest of the branch: yes.

## Open questions (answered above)
Plain-language, with my recommendation:
1. Should the dashboard show how often our automatic checks pass and how long they take? Recommend yes: it is the main thing that is missing.
2. Is it OK that, to get this, one small script contacts GitHub (read-only) while the build runs? The dashboard page itself still works offline. Recommend yes; it is isolated and fails safely.
3. The old branch also had a "Now / Then / Later" roadmap for projects that ship numbered releases. Do you want it? Recommend no for now: your current roadmap already has a clear order. We can add it later if a project needs it.
4. Should projects that keep tech debt as a table be supported? Recommend yes; it is small.
5. Do you accept dropping the rest of the branch (open-decisions tile, deploy bars, phone styling, lane config), since the newer dashboard already covers those? Recommend yes.

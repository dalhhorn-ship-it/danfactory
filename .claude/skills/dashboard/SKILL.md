---
name: dashboard
description: Build and show the project dashboard — versions, phase and progress, backlog state, tech debt, key metrics (tests, coverage, deploys, tokens), alerts. Use when the user asks for status, progress, a dashboard, "where are we", or after a milestone, release or retro.
---

# Dashboard

The dashboard is a generated artefact, so never write it by hand. `python3 scripts/dashboard.py` writes:
- `dashboard/index.html`: self-contained page (no JS, no network) that works in light and dark mode and on phones (tables stack, the roadmap scrolls sideways with pinned lane headers). Two tabs: **Overview** (metrics, ranked backlog, delivery, open decisions, debt, versions) and **Roadmap** (proposed sequence in two swimlanes: value-driven features vs technical foundation)
- `dashboard/data.json`: the same data for tools
- `dashboard/SUMMARY.md`: a short status table (about 12 to 16 lines)

It is regenerated automatically by every `scripts/metrics.py` run (test, deploy, report) and by CI on every build. CI first runs `scripts/ci_runs.py` (job token) to refresh the CI history, uploads the page as the `dashboard` artifact and writes SUMMARY.md to the job summary.

Locally, `python3 scripts/ci_runs.py` refreshes `metrics/ci-runs.json` (git-ignored cache; public repos need no token, `GITHUB_TOKEN`/`GH_TOKEN` is used if set). It is the only dashboard script that uses the network; the page builder stays offline and shows "no CI history yet" without it.

## Answering "where are we?"
Run `python3 scripts/dashboard.py --print` and answer from the summary (cheap). Don't read index.html or data.json into context.

## Showing it
- Local: `python3 scripts/dashboard.py --open`.
- In the Claude app: if the Artifact tool is available, publish `dashboard/index.html` as a private artifact and store its URL in `factory.json → integrations.dashboard_url`. Republish to the same URL later so the link stays stable.
- CI: open the run's `dashboard` artifact.

## Keeping it truthful (the dashboard is only as good as its sources)
| Panel | Source | Kept current by |
|---|---|---|
| Phase, paths | factory.json | brainstorm, choose-path |
| Progress, backlog | docs/BACKLOG.md (`[ ] [~] [x] [!] [-]` items under milestones) | every task (definition of done), choose-path seeds it |
| Roadmap | docs/BACKLOG.md: a `## Ranked backlog` release table (columns Now/Then/Later from the first word of Status: next, candidate, later; rank order; shipped/dropped only counted) and/or `## Milestone:` checklists (milestones = columns, file order = sequence), then open TECH-DEBT.md items (foundation, by impact). Task chips on release cards come from the plan file (`dashboard.plan_file`, default docs/PLAN.md): tasks whose Milestone is the release id, or ids named in its Plan tasks cell (`T55` also finds `T55a`) | choose-path, product-manager when (re)sequencing: reorder rows or items to change the proposal |
| Roadmap lanes | Rules in order: `#value`/`#feature` tag → value; a foundation tag (`#foundation`, `#arch`, `#infra`, `#runway`, `#debt`, `#quality`, `#ci`, `#security`, `#perf`, `#safety`… plus `dashboard.foundation_tags`) → foundation; `factory.json → dashboard.lane_overrides` (`{"v4": "foundation"}`, keyed by release id or exact item title); a refactor round (id matches `dashboard.refactor_id_pattern`, default `R\d+`, or "refactor" in the release note) → foundation; else value. Open refactor rounds in the plan that no release claims join Now | whoever sequences; tag the row rather than editing the script |
| Delivery | metrics/ci-runs.json (CI pass rate last 30, pass rate on the production branch, median/p90 CI minutes, last failures, runs and pass rate per week); deploys per week from metrics/history.jsonl, else (git deploys configured) first-parent commits on origin/<production_branch> since `dashboard.deploys_since`; releases and gaps from CHANGELOG.md (`## 1.2.0 (date)` or `## [1.2.0] - date`, plus the Unreleased bullet count), else release tags | `ci_runs.py` (CI), `metrics.py deploy`, ship |
| Open decisions | docs/decisions/NNNN-*.md with `Status: proposed` | anyone opening an ADR; answer it to clear the tile |
| Tech debt | docs/TECH-DEBT.md register (checklist or table with Id, Severity/Impact, Item, Where, Size, Status; major counts as high) + automated markers/large files/cycles | retro, `engineering:tech-debt`, any shortcut taken on purpose |
| Versions | git tags (`git tag vX.Y.Z`), VERSION / package.json / pyproject.toml | releases |
| Deploys | metrics/history.jsonl | `metrics.py deploy`, ship |
| Tests, coverage | metrics/history.jsonl | `metrics.py test` (test-runner) |
| Tokens | metrics/tokens.jsonl | SessionEnd hook |

## Tables are pipe safe
Markdown table rows are split on `|` except inside a code span or as `\|`. If a stray pipe still splits the free-text column (Task, Item, What…), the columns after it (Milestone, Status) are read from the end of the row, so they never shift.

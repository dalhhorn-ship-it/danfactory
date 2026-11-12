---
name: dashboard
description: Build and show the project dashboard — versions, phase and progress, backlog state, tech debt, key metrics (tests, coverage, deploys, tokens), alerts. Use when the user asks for status, progress, a dashboard, "where are we", or after a milestone, release or retro.
---

# Dashboard

The dashboard is a generated artefact, so never write it by hand. `python3 scripts/dashboard.py` writes:
- `dashboard/index.html`: self-contained page (no JS, no network) that works in light and dark mode and on phones; `scripts/dashboard.py` itself never uses the network. Tabs: **Overview** (metrics, backlog, debt, versions, and a **Delivery** card: CI pass rate, median/p90 CI minutes, latest failures, 8-week runs and pass-rate bars, release cadence), **Roadmap** (sub-tabs: Sequence = proposed sequence in two swimlanes, value-driven features vs technical foundation; 6-month timeline; proposed Gantt; Releases. Default view and Gantt assumptions: `dashboard.roadmap_view`, `dashboard.size_days`, `dashboard.wip` in factory.json), **Architecture** (layered ArchiMate-style diagram: Motivation from GOAL/PRDs/ADRs, Application from source roots, Technology from wrangler bindings; plus designed-vs-built drift) and **Traceability** (goal → PRD → item → commits → components → tests → version, broken links flagged), **Decisions** (ADR timeline, status, supersedes chains, affected components), **Gates** (PRD approved per item, tests per component, last check.sh pass, last security audit, dependency freshness) **Docs health** (orphan docs, docs stale vs the code they name, components without docs), **Flow** (lead time, cycle time, WIP, deploy frequency, change failure rate; lead time follows first-parent history so merges count at the merge commit, and counts deploys whose `--env` is in `dashboard.prod_envs`, default `["prod","production"]`. By design, production deploys must be recorded with `python3 scripts/metrics.py deploy --env <name>`; without records the tab shows n/a), **Cost** (weighted tokens, unattributed share, per-item cost only when a record names the item) and **Hotspots** (files by churn x size over the last `dashboard.hotspot_commits` commits, default 500, flagged when no test matches by name), **Evals** and **Autonomy** (Issues block from the issues/ ledger: open and fixed counts, daily trend, open by PRD, oldest open; docs/policies/issue-ledger.md). Tabs are listed in `TABS` in scripts/dashboard.py; their code is in `scripts/obs/`
- `dashboard/data.json`: the same data for tools
- `dashboard/SUMMARY.md`: a 12-line status table

It is regenerated automatically by every `scripts/metrics.py` run (test, deploy, report) and by CI on every build. CI uploads it as the `dashboard` artifact and writes SUMMARY.md to the job summary.

## Answering "where are we?"
Run `python3 scripts/dashboard.py --print` and answer from the summary (cheap). Don't read index.html or data.json into context.

## Showing it
- Local: `python3 scripts/dashboard.py --open`.
- In the Claude app: if the Artifact tool is available, publish `dashboard/index.html` as a private artifact and store its URL in `factory.json → integrations.dashboard_url`. Republish to the same URL later so the link stays stable. In a new session the first republish is refused until the live version is read; the page is generated, so publish again unchanged.
- CI: open the run's `dashboard` artifact.

## Refresh rhythm
After every completed slice: `product-manager` re-proposes the sequence in docs/BACKLOG.md (order + `> Sequence:` line), then rebuild and republish to the same artifact URL (`integrations.dashboard_url`).

## Keeping it truthful (the dashboard is only as good as its sources)
| Panel | Source | Kept current by |
|---|---|---|
| Phase, paths | factory.json | brainstorm, choose-path |
| Progress, backlog | docs/BACKLOG.md (`[ ] [~] [x] [!] [-]` items under milestones) | every task (definition of done), choose-path seeds it |
| Roadmap | docs/BACKLOG.md order (milestones = columns, file order = one global sequence 1..N across lanes, `> Sequence:` line = why, all-done milestones collapse, top 3 = Next up, linked `docs/specs/*.md` = PRD badge) + tags for the lane (`#foundation`, `#arch`, `#infra`, `#runway`, `#debt`, `#quality`, `#ci`, `#security`, `#process`… → foundation; untagged, `#value` or `#feature` → value) + open TECH-DEBT.md items (foundation, sorted by impact), optional markers `(release: vX.Y)` (item or milestone heading) and `(after: ABC-n)` for the other views, git tags `vX.Y.Z` for shipped releases | choose-path, product-manager when (re)sequencing: reorder items in BACKLOG.md to change the proposal |
| Delivery (CI) | metrics/ci-runs.json (git-ignored cache) written by `python3 scripts/ci_runs.py` (GitHub Actions API, read-only; repo from `factory.json` `dashboard.github_repo`, else origin). CI refreshes it on every build; a missing file shows "no CI history yet" | CI step; run `ci_runs.py` by hand to refresh |
| Release cadence | CHANGELOG.md headings (`## 1.2.0 (date)` or `## [1.2.0] - date`; file via `dashboard.changelog_file`), else release-like tags | releases |
| Tech debt | docs/TECH-DEBT.md register (checklist lines or a table `Id \| Severity \| Item \| Where \| Size \| Source \| Status`; major counts as high) + automated markers/large files/cycles | retro, `engineering:tech-debt`, any shortcut taken on purpose |
| Versions | git tags (`git tag vX.Y.Z`), VERSION / package.json / pyproject.toml | releases |
| Deploys | metrics/history.jsonl | `metrics.py deploy`, ship |
| Tests, coverage | metrics/history.jsonl | `metrics.py test` (test-runner) |
| Tokens | metrics/tokens.jsonl | SessionEnd hook |
| Architecture | docs/GOAL.md, docs/specs/ (`# PRD:`), docs/decisions/, source roots (`src/ app/ worker/ lib/ packages/ functions/`; `scripts/` in the un-bootstrapped template), wrangler.jsonc/toml, migrations/*.sql, plus curated intent in docs/architecture.json | docs-sync runs `python3 scripts/archmodel.py --write` (the tab flags a stale file); edit only `curated` by hand |
| Traceability | PRDs + docs/BACKLOG.md + `git log` | item IDs (`ABC-n`) in the backlog and a `Refs: ABC-n` trailer on every commit (PRD slug if the item has no ID); missing keys show as broken links, never block |
| Decisions | docs/decisions/NNNN-*.md header (`> Status: ... · Date: ...`, `Supersedes: NNNN`, `superseded by NNNN`); affected components = component paths named in the ADR | write the header when recording an ADR; set `superseded by NNNN` on the old one |
| Gates | PRD status (docs/specs/), item-to-PRD links (Traceability), test file names, `metrics/records.jsonl` + `records.local.jsonl`, dependency manifests' last commit | `bash scripts/check.sh` records a pass; after a security audit run `python3 scripts/metrics.py record security-audit`; unrecorded gates show "not recorded yet" |
| Flow | git `Refs: <ITEM-ID>` trailers, the commit that ticks the item in docs/BACKLOG.md, PRD approval date, prod deploys in metrics/history.jsonl | `python3 scripts/metrics.py deploy --env prod` after each prod deploy |
| Cost | metrics/tokens.jsonl (written by the SessionEnd hook) | automatic; rows are per item only if they carry `item`, a `sha`, or `shas` (session commits) that reference exactly one item; mixed sessions are counted, not split |
| Hotspots | git history (last 500 commits) + file sizes | none |
| Docs health | docs/knowledge-graph.json (orphan = no links in or out) + git commit times of docs vs the code files they name | `python3 scripts/docs_index.py` (check.sh verifies it is fresh) |

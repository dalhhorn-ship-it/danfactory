---
name: dashboard
description: Build and show the project dashboard — versions, phase and progress, backlog state, tech debt, key metrics (tests, coverage, deploys, tokens), alerts. Use when the user asks for status, progress, a dashboard, "where are we", or after a milestone, release or retro.
---

# Dashboard

The dashboard is a generated artefact, so never write it by hand. `python3 scripts/dashboard.py` writes:
- `dashboard/index.html`: self-contained page (no JS, no network) that works in light and dark mode and on phones. Two tabs: **Overview** (metrics, backlog, debt, versions) and **Roadmap** (proposed sequence in two swimlanes: value-driven features vs technical foundation)
- `dashboard/data.json`: the same data for tools
- `dashboard/SUMMARY.md`: a 12-line status table

It is regenerated automatically by every `scripts/metrics.py` run (test, deploy, report) and by CI on every build. CI uploads it as the `dashboard` artifact and writes SUMMARY.md to the job summary.

## Answering "where are we?"
Run `python3 scripts/dashboard.py --print` and answer from the summary (cheap). Don't read index.html or data.json into context.

## Showing it
- Local: `python3 scripts/dashboard.py --open`.
- In the Claude app: if the Artifact tool is available, publish `dashboard/index.html` as a private artifact and store its URL in `factory.json → integrations.dashboard_url`. Republish to the same URL later so the link stays stable.
- CI: open the run's `dashboard` artifact.

## Refresh rhythm
After every completed slice: `product-manager` re-proposes the sequence in docs/BACKLOG.md (order + `> Sequence:` line), then rebuild and republish to the same artifact URL (`integrations.dashboard_url`).

## Keeping it truthful (the dashboard is only as good as its sources)
| Panel | Source | Kept current by |
|---|---|---|
| Phase, paths | factory.json | brainstorm, choose-path |
| Progress, backlog | docs/BACKLOG.md (`[ ] [~] [x] [!] [-]` items under milestones) | every task (definition of done), choose-path seeds it |
| Roadmap | docs/BACKLOG.md order (milestones = columns, file order = one global sequence 1..N across lanes, `> Sequence:` line = why, all-done milestones collapse, top 3 = Next up, linked `docs/specs/*.md` = PRD badge) + tags for the lane (`#foundation`, `#arch`, `#infra`, `#runway`, `#debt`, `#quality`, `#ci`, `#security`, `#process`… → foundation; untagged, `#value` or `#feature` → value) + open TECH-DEBT.md items (foundation, sorted by impact) | choose-path, product-manager when (re)sequencing: reorder items in BACKLOG.md to change the proposal |
| Tech debt | docs/TECH-DEBT.md register + automated markers/large files/cycles | retro, `engineering:tech-debt`, any shortcut taken on purpose |
| Versions | git tags (`git tag vX.Y.Z`), VERSION / package.json / pyproject.toml | releases |
| Deploys | metrics/history.jsonl | `metrics.py deploy`, ship |
| Tests, coverage | metrics/history.jsonl | `metrics.py test` (test-runner) |
| Tokens | metrics/tokens.jsonl | SessionEnd hook |

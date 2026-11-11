# Policy: testing and delivery metrics

> Fast feedback is a feature. Measure test time, coverage, deploys and tokens; act on the trend.

## Rules
1. All test runs go through `python3 scripts/metrics.py test` (usually via `test-runner`) so time, result and coverage are recorded in `metrics/history.jsonl`.
2. Inner loop: `--affected` (only tests touched by the change; codegraph `affected` or the runner's own changed-files mode). Full suite before merge and in CI.
3. Budgets (factory.json): full ≤ `test_seconds`, affected ≤ `affected_test_seconds`, coverage ≥ `min_coverage_pct`, max drop `max_coverage_drop_pct`, deploy ≤ `deploy_seconds`.
4. Record deploys (`metrics.py deploy`). Track failure rate.
5. Run `metrics.py report` at milestones and in `retro`; alerts appear at session start.
6. Never skip, delete or weaken a test to get green. Flaky → reproduce and fix.

7. Behavioural evals of the agents (gates, guards, handoff) are a separate, manual, paid check: `python3 scripts/evals.py` (docs/policies/evals.md). Never in CI; the structural tests for the harness call no model.

## Dashboard
Every metrics run and every CI build regenerates `dashboard/` (scripts/dashboard.py) with versions, progress, backlog, tech debt and key metrics, plus a Delivery card from `metrics/ci-runs.json`. That cache is written by `scripts/ci_runs.py` (one read-only GitHub API call; CI runs it in a `continue-on-error` step with job-level `actions: read`); the page builder itself stays offline. CI pass rate counts the last 30 decided runs (success or failure; cancelled and skipped are ignored). See the `dashboard` skill.

## When a budget is breached
Pick the top 1–3 suggestions from `metrics/REPORT.md` by saving/effort, do them, record the result as a learning. Change a budget only with a recorded reason.

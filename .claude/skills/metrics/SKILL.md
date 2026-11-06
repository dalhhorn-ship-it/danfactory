---
name: metrics
description: Record and review delivery metrics — test time, coverage, deploy duration/failures, token spend per session — and suggest structural improvements to cut wait time and token cost. Use when the user asks about speed, coverage, cost, CI time, or after changing test/deploy setup.
---

# Metrics

- Record a test run: delegate to the `test-runner` subagent (it calls `python3 scripts/metrics.py test`). Inner loop: `--affected`.
- Record a deploy: `python3 scripts/metrics.py deploy --env <env>` (or `--seconds N --status ok|fail` from CI).
- Tokens are recorded automatically at session end (SessionEnd hook -> `metrics/tokens.jsonl`).
- Review: `python3 scripts/metrics.py report`, then read `metrics/REPORT.md` (small).

When proposing improvements, quantify: "test suite 240s -> ~40s inner loop by running affected tests; est. N fewer tokens per session by delegating log reading". Pick the top 1–3 by (time or tokens saved) / effort. Budgets live in `factory.json`; change them only with a reason recorded in LEARNINGS.md.

# Handoff — 2026-11-16 — MISSION-1..5 approved, build starting (branch claude/friendly-mccarthy-41do0k)

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. User approves every PRD, decides which builds start; standing permission to fast-forward main after a gate PASS on that exact sha.
Now: build mission autopilot (one approved mission brief → PRDs approved by mission → Stop hook keeps going under caps → morning report; no push to main) + parallel build for all modes. PRD docs/specs/mission-autopilot.md (approved 2026-11-16, "Ok"); backlog M4 MISSION-1..5 `[~]`, MISSION-6 later.

## State
- main = 134063d. Branch claude/friendly-mccarthy-41do0k @ 3a8782f: PRD approved, ADR 0012, slices A (1d93007), B (8587c3e), C (e67e78c) landed + integration fixes (docs index budget, -B test, ok/yes go) + docs (CLAUDE.md line, routing, TD-024/025). Full suite green before review except fixed -B test.
- Reviewer: fix-first. Fixes in progress (developer): Stop hook must validate() mission (caps from frozen header); git push --repo bypass in _gitmission.py; slices.py land refuses protected --into during mission and --gate-cmd outside tests; gate _c_prd missing commit time -> not live check; honest limits (state file editable, go quote/commit dates forgeable) in policy+ADR.

## Next steps
1. After fixes: full `metrics.py test` + check.sh (test-runner), re-review, tick MISSION-1..5 [x], docs-sync, push, report to user (incl. TD-024/025, spikes S1/S2 need a real overnight run).

## Watch out
- Only move main after a gate PASS on that sha. Tests must copy repos via tracked files into a fresh repo (never cp -r).
- Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/specs/mission-autopilot.md, docs/policies/prd-approval.md, docs/policies/runner.md, docs/decisions/0007..0011

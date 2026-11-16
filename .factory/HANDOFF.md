# Handoff — 2026-11-16 — MISSION-1..5 approved, build starting (branch claude/friendly-mccarthy-41do0k)

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. User approves every PRD, decides which builds start; standing permission to fast-forward main after a gate PASS on that exact sha.
Now: build mission autopilot (one approved mission brief → PRDs approved by mission → Stop hook keeps going under caps → morning report; no push to main) + parallel build for all modes. PRD docs/specs/mission-autopilot.md (approved 2026-11-16, "Ok"); backlog M4 MISSION-1..5 `[~]`, MISSION-6 later.

## State
- main = 134063d. Branch claude/friendly-mccarthy-41do0k has GATE-2 + MISSION PRD (approved).
- Plan: software-architect writes ADR 0012 with slice/file-ownership map, then developers in parallel worktrees, serial merges with gate, reviewer, docs-sync.
- Defaults decided: 15 USD, 10 h, 40 continuations; feature cap 5.

## Next steps
1. ADR 0012 design (architect) → parallel developer slices → merge one at a time → `python3 scripts/metrics.py test`, `bash scripts/check.sh`, gate → tick backlog, docs-sync, push.

## Watch out
- Only move main after a gate PASS on that sha. Tests must copy repos via tracked files into a fresh repo (never cp -r).
- Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/specs/mission-autopilot.md, docs/policies/prd-approval.md, docs/policies/runner.md, docs/decisions/0007..0011

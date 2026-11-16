# Handoff — 2026-11-16 — MISSION-1..5 built and reviewed (branch claude/friendly-mccarthy-41do0k)

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. User approves every PRD, decides which builds start; standing permission to fast-forward main after a gate PASS on that exact sha.
Now: build mission autopilot (one approved mission brief → PRDs approved by mission → Stop hook keeps going under caps → morning report; no push to main) + parallel build for all modes. PRD docs/specs/mission-autopilot.md (approved 2026-11-16, "Ok"); backlog M4 MISSION-1..5 `[~]`, MISSION-6 later.

## State
- main = 134063d. Branch claude/friendly-mccarthy-41do0k: MISSION-1..5 done (PRD docs/specs/mission-autopilot.md, ADR 0012, policy docs/policies/mission.md); review ship after fixes 61e5fa5 + final nits; check.sh ok, 644 tests.
- Open: TD-024 (budget cap is a price-table estimate), TD-025 (Stop hook not yet run in a real overnight cloud session). MISSION-6 (watchdog) waits for a first real mission.

## Next steps
1. Wait for the user: promote branch to main (needs their go), and a first small real mission to close spikes S1/S2.

## Watch out
- Only move main after a gate PASS on that sha. Tests must copy repos via tracked files into a fresh repo (never cp -r).
- Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/specs/mission-autopilot.md, docs/policies/prd-approval.md, docs/policies/runner.md, docs/decisions/0007..0011

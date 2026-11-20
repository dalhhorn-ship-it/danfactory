# Handoff — 2026-11-20 — PRD teach-agents-to-fish drafted, waiting for approval

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. User approves every PRD, decides which builds start; standing permission to fast-forward main after a gate PASS on that exact sha.
Now: user read the AWS article "Teach an agent to fish" (Goldberg, 2026-11-19) and asked for a PRD for lessons 1, 2, 5, 6, 7 (not 4 = use libraries; 3 already built).

## State
- Done: draft PRD docs/specs/teach-agents-to-fish.md (FISH-1, 2, 5, 6, 7; 23 acceptance criteria; 4 open questions with recommendations), presented in chat. Status: draft. Nothing built, backlog untouched.
- Branch: claude/cool-mayer-h2ahtb (contains MISSION-1..5, tip before this work a071ccf). Uncommitted: none after this commit.
- Still open from before: promote the MISSION work to main (needs the user's go); first small real mission to close spikes S1/S2; TD-024, TD-025; MISSION-6 later.

## Decisions (and why)
- One PRD with five slices instead of five PRDs: one approval round; FISH-1 and FISH-6 share the "issue not born from a failing test" design.

## Next steps
1. Wait for the user: approve, change or drop the PRD, and answer open questions 1-4 (PRD lines 88-92).
2. On approval: Status approved + date, add FISH items to docs/BACKLOG.md (Unplanned), build order FISH-2, FISH-6, FISH-1, FISH-5, FISH-7.

## Watch out
- builder.aws.com is not reachable from this session; the user declined a network/environment change. Do not propose it again; the user pastes text instead.
- Only move main after a gate PASS on that sha. Tests must copy repos via tracked files into a fresh repo (never cp -r).
- Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/specs/teach-agents-to-fish.md, docs/policies/prd-approval.md:14, docs/policies/issue-ledger.md, docs/policies/merge-gate.md:11
- docs/specs/mission-autopilot.md, docs/policies/mission.md, docs/decisions/0007..0012

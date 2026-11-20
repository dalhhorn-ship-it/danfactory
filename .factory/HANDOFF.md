# Handoff — 2026-11-20 — FISH-2, 5, 6, 7 built and reviewed, waiting for the user

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. User approves every PRD, decides which builds start; standing permission to fast-forward main after a gate PASS on that exact sha.
Now: user read the AWS article "Teach an agent to fish" (Goldberg, 2026-11-19) and asked for a PRD for lessons 1, 2, 5, 6, 7 (not 4 = use libraries; 3 already built).

## State
- Done: PRD docs/specs/teach-agents-to-fish.md approved 2026-11-20 ("ok implement 2-7 and forget fish 1"); FISH-1 dropped by the user. Built: FISH-2 abce7bd, FISH-7 ccb9dc6, FISH-6 95be314 (ADR 0013), FISH-5 af81055 (ADR 0014), review fixes 052c41c. Reviewer verdict on c2c5086..af81055: ship; 052c41c itself not independently reviewed. Gate PASS on 052c41c (warn size-growth), check.sh ok, 692 tests.
- Branch: claude/cool-mayer-h2ahtb (also holds MISSION-1..5), pushed. main untouched.
- Still open from before: first small real mission (spikes S1/S2); TD-024, TD-025; MISSION-6 later.

## Open questions for the user
1. May the fixer runner pick size ("split this file") issues without a PRD? Recommended yes, tests must pass at the gate. Today they are filed and closed but not auto-picked.
2. Lesson 4 of the article (use established libraries) is not in the PRD; build only if the user asks (needs a PRD addition).
3. Promote the branch to main (needs the user's go; gate PASS on the exact sha first).

## Next steps
1. Wait for the user's answers above.

## Watch out
- builder.aws.com is not reachable from this session; the user declined a network/environment change. Do not propose it again; the user pastes text instead.
- Only move main after a gate PASS on that sha. Tests must copy repos via tracked files into a fresh repo (never cp -r).
- Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/specs/teach-agents-to-fish.md, docs/policies/prd-approval.md:14, docs/policies/issue-ledger.md, docs/policies/merge-gate.md:11
- docs/specs/mission-autopilot.md, docs/policies/mission.md, docs/decisions/0007..0012

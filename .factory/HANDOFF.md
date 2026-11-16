# Handoff — 2026-11-16 — autonomous-mode review fixed on branch; hardening PRD awaits the user

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. Asked: "only the initial request summary requires approval … keeps building until done over night. Also optimise build mode for multiple agents at the same time." Built as MISSION-1..5.

## State
- Done: MISSION-1..5 on main a071ccf. Architect review (safety + friction) of autonomous mode; bugfix batch on branch claude/friendly-mccarthy-41do0k (6e4061c docs/slices/bootstrap, X safety fixes, 4e5034c mission protection keyed on active mission on HEAD). 669 tests, check.sh ok. NOT on main yet (ask the user).
- In progress: PRD draft docs/specs/mission-hardening.md (MISSION-7..) for new behaviour: enforce acceptance admission before build in a mission; sandbox for mission developers; one budget incl. runner/second reading; Stop hook skips `[~]` items held by background developers; branch safety after mission end + staging; mission defaults in factory.json and feature count ignoring parked items. Needs user approval before any code.
- Branch: claude/friendly-mccarthy-41do0k, uncommitted: none.

## Decisions (and why)
- One mission "go" approves in-scope PRDs (`by mission <slug>`); defaults 15 USD / 10 h / 40 continuations, feature cap 5 — user approved PRD 2026-11-16 (ADR 0012).
- A plain "ok"/"yes" to the brief is a valid go (the user answers "Ok"); vague words are not.
- Invalid mission (header changed after first commit, uncommitted, no started_at) = stopped; caps only from the frozen header.
- docs/INDEX.md rows show titles, not Status lines, and summaries are cut at 48 chars to stay under the DOCS-1 budget.

## Next steps
1. Present the hardening PRD; wait for approve/change/drop. Ask before promoting the fix batch to main (gate PASS on the exact sha first).
2. First small real mission downstream (TD-024/025), then MISSION-6.

## Watch out
- Only move main after a gate PASS on that exact sha, and ask the user before pushing to main (session rules).
- Agent `isolation: "worktree"` starts from the default branch: tell developers to `git reset --hard <integration branch>` first.
- Gate warns `size-growth` (product code +40% in 3 days).
- Tests must copy repos via tracked files into a fresh repo (never cp -r). Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/policies/mission.md (brief format, rules, honest limits), docs/decisions/0012-mission-autopilot.md
- .claude/hooks/_mission.py, mission_stop.py, _gitmission.py; scripts/mission.py, mission_report.py, slices.py
- docs/operating-model/AGENT-ROUTING.md "Parallel build"; docs/TECH-DEBT.md TD-024/025

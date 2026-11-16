# Handoff — 2026-11-16 10:06 — mission autopilot shipped to main; waiting on a first real mission

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. Asked: "only the initial request summary requires approval … keeps building until done over night. Also optimise build mode for multiple agents at the same time." Built as MISSION-1..5.

## State
- Done: MISSION-1..5 (PRD docs/specs/mission-autopilot.md, ADR 0012, policy docs/policies/mission.md). Gate PASS on a071ccf; main fast-forwarded to a071ccf with the user's yes (2026-11-16). 644 tests, check.sh ok.
- In progress: nothing.
- Branch: claude/friendly-mccarthy-41do0k (one handoff commit ahead of main), uncommitted: none.

## Decisions (and why)
- One mission "go" approves in-scope PRDs (`by mission <slug>`); defaults 15 USD / 10 h / 40 continuations, feature cap 5 — user approved PRD 2026-11-16 (ADR 0012).
- A plain "ok"/"yes" to the brief is a valid go (the user answers "Ok"); vague words are not.
- Invalid mission (header changed after first commit, uncommitted, no started_at) = stopped; caps only from the frozen header.
- docs/INDEX.md rows show titles, not Status lines, and summaries are cut at 48 chars to stay under the DOCS-1 budget.

## Next steps
1. Wait for the user. Recommended: a first small real mission (2 features, 5 USD, 3 h) in a downstream project (e.g. lpdan) to close TD-024 (price-table budget estimate) and TD-025 (Stop hook next to the environment's own Stop hook).
2. Then decide on MISSION-6 (watchdog resume, opt-in schedule).

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

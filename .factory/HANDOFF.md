# Handoff — 2026-11-16 — PR #1 open (review fixes, MISSION-7..12, scout, AUTO-MODE.md); waiting for the user to merge

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. Asked: "only the initial request summary requires approval … keeps building until done over night. Also optimise build mode for multiple agents at the same time." Built as MISSION-1..5.

## State
- main = a071ccf (MISSION-1..5). PR dalhhorn-ship-it/danfactory#1 (branch claude/friendly-mccarthy-41do0k → main) holds: architect-review fixes, MISSION-7..12 (docs/specs/mission-hardening.md), SCOUT-1/2 (docs/specs/open-source-scout.md: `oss-scout` agent, docs/research/_TEMPLATE-scout.md, scripts/scout_check.py with a permissive-licence allow-list), docs/AUTO-MODE.md (explainer + dev mode comparison table for the landing page; the user wanted an MD file, not a PRD). Gate PASS on the branch; reviews done and findings fixed.
- In progress: nothing. Open: MISSION-6, TD-024/025/026.
- Direct push to main was denied by the session's permission check, so the user merges the PR. lpdan is readable (clone at /home/user/dalhhorn-ship-it/lpdan) but push access was denied.

## Decisions (and why)
- One mission "go" approves in-scope PRDs (`by mission <slug>`); defaults 15 USD / 10 h / 40 continuations, feature cap 5 — user approved PRD 2026-11-16 (ADR 0012).
- A plain "ok"/"yes" to the brief is a valid go (the user answers "Ok"); vague words are not.
- Invalid mission (header changed after first commit, uncommitted, no started_at) = stopped; caps only from the frozen header.
- docs/INDEX.md rows show titles, not Status lines, and summaries are cut at 48 chars to stay under the DOCS-1 budget.

## Next steps
1. Wait for the user: merge PR #1 (do not merge it yourself); offer to watch the PR.
2. Landing page (lpdan) can use docs/AUTO-MODE.md; needs an lpdan session with write access.
3. First small real mission downstream (TD-024/025), then MISSION-6; TD-026 test time.

## Watch out
- Guards keyed on agent-editable state (backlog lines, working-copy mission file, exemptions) were the recurring review finding: key on the active mission on HEAD and on first-commit data.
- Only move main after a gate PASS on that exact sha, and ask the user before pushing to main (session rules).
- Agent `isolation: "worktree"` starts from the default branch: tell developers to `git reset --hard <integration branch>` first.
- Gate warns `size-growth` (product code +40% in 3 days).
- Tests must copy repos via tracked files into a fresh repo (never cp -r). Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/policies/mission.md (brief format, rules, honest limits), docs/decisions/0012-mission-autopilot.md
- .claude/hooks/_mission.py, mission_stop.py, _gitmission.py; scripts/mission.py, mission_report.py, slices.py
- docs/operating-model/AGENT-ROUTING.md "Parallel build"; docs/TECH-DEBT.md TD-024/025

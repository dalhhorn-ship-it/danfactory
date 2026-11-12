# Handoff — 2026-11-12 — M3: AUTO-1 pushed (review: fix first); AUTO-2 building in main tree; AUTO-3 + tech debt building in worktrees

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- Pushed to cd55800: AUTO-1 gate (b4b353b) + reviewer fixes (952ebb1); AUTO-2 acceptance suite (2164ea5); AUTO-3 issue ledger merged (389516a); TD batch A merged (cd55800: TD-001/002/003/006/007 resolved, hook-test copy no longer commits into the branch). 6 stray `t` commits (handoff-only edits, content discarded in merge) remain in pushed history; left as is.
- AUTO-1..3 ticked. AUTO-4..7 still need the user's go. 20 agents (test-writer, finder added).
- Running: worktree developer TD-004/005/010/011 (paid haiku eval run, cap 5 USD); main-tree developer TD-013 (JUnit parsing).
- Open by design: TD-012 and TD-014 close with AUTO-4 (runner refuses fixer trailers; runner automates second reading).
## Next steps
1. Merge TD-013 (main tree) and the TD-004/005/010/011 worktree; check.sh + gate; push; remove worktree.
2. Short reviewer pass on AUTO-2/AUTO-3 merged code.
3. Republish dashboard to factory.json dashboard_url (same link; first republish in a new session may need a read first), send link + summary.
4. Ask user which repo pilots on a real library project (pilot 2), or offer a starter.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

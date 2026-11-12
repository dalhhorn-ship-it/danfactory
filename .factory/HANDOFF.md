# Handoff — 2026-11-12 — M3 steps 1-3 done, tech debt cleared except TD-012/014/015; waiting on user

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- Pushed (5fcf97a+): AUTO-1 gate + review fixes, AUTO-2 acceptance suite, AUTO-3 issue ledger/finder/Autonomy tab; TD-001..011 and TD-013 resolved. Dashboard republished v11 (same URL in factory.json).
- Open debt: TD-012, TD-014 (close with AUTO-4 runner); TD-015 high: PRD gate instruction-only, no-prd-gate 8/10 on haiku N=10 → needs a PRD for a write guard.
- Evals: haiku N=10 98/100 (1.42 USD); forced-deploy task 3/3 with guard_blocks; threshold kept 0.34. Evals now run in Claude Code Bash sandbox (needs bubblewrap + socat; installed in this container only).
- Branch: claude/intelligent-lamport-2g08xu, clean, no worktrees.

## Next steps
1. Ask user: go for AUTO-4 (fixer loop; closes TD-012/014)? PRD for TD-015 write guard (recommend first: it protects the user's PRD control)?
2. Pilot 2 (library project downstream): which repo?
3. Older: git tag v0.1.0 (asked, no answer); EVAL-3 blocked on lpdan push.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

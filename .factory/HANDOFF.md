# Handoff — 2026-11-14 — "Progress 1-3": pilot bundled; TD-017..019 + AUTO-5 + AUTO-7 building; AUTO-6 next

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- User 2026-11-14 "Progress 1-3": (1) pilot preserved as evals/spikes/pilot-semverlite/pilot-semverlite.bundle (all branches, restore steps in its README; no repo name given), (2) fix TD-017..019, (3) AUTO-5..7 approved (ADR 0010, 73ff843).
- Running: main tree developer TD-017/018/019 (item TD-PILOT [~]); worktree AUTO-5 release.py; worktree AUTO-7 learn.py + 3 fixer eval tasks (paid haiku N=3).
- AUTO-6 (parallel fixers, runner.py) starts AFTER the TD developer lands (both touch runner.py).
- Merge order: TD fixes → AUTO-5 worktree → AUTO-7 worktree (tab_autonomy conflicts additive) → launch AUTO-6 → check.sh + gate → push → republish dashboard (and pilot dashboard if useful).

## Next steps
1. As above. Then report; remaining: TD-016, v0.1.0 tag (unanswered), EVAL-3 (lpdan push).

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

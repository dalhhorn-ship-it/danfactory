# Handoff — 2026-11-14 — AUTO-5, AUTO-7, TD-017..019 merged; AUTO-6 building

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- Pushed 8cb2179: pilot bundle (evals/spikes/pilot-semverlite/pilot-semverlite.bundle), TD-017/018/019 resolved, AUTO-5 release.py, AUTO-7 learn.py + 3 fixer evals (haiku 3/3 each after fixture fixes, ~0.19 USD). AUTO-5, AUTO-7 ticked.
- Running: developer AUTO-6 parallel fixers in MAIN tree (runner.py), incl. real haiku smoke --parallel 2 (cap 0.5 USD).
- Open debt: TD-016 only (+ includes_acceptance heuristic limits noted by developer; release rows left uncommitted for the user by design).

## Next steps
1. When AUTO-6 reports: verify, check.sh + gate, push; republish template dashboard (and pilot dashboard optional); final summary to user (M3 complete if AUTO-6 done).
2. Remaining asks: v0.1.0 tag (unanswered), EVAL-3 (lpdan push), TD-016, check.sh ~111s vs 120s budget.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

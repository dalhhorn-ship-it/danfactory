# Handoff — 2026-11-14 — M3 gated autonomy complete (AUTO-1..7); waiting on user

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- Pushed 43f8be5: AUTO-6 parallel fixers (real haiku smoke --parallel 2: both merged attempt 1, 0.012 USD). All AUTO-1..7 ticked. Dashboard v13 republished.
- Open debt: TD-016 (guard gaps), TD-020 (fixers are threads; gate runs serialised; rebased fix keeps original review).
- Template gate/check now ~139s vs 120s budget (tests-over-budget risk): propose a speed-up (affected tests / split slow sandbox tests).
- AUTO-6 developer reported 'waiting on its own background work' after its report; check git status for late changes.

## Next steps
1. Ask user: speed up template checks; TD-016/020; v0.1.0 tag; EVAL-3 (lpdan push); merge branch to main is the user's call.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

# Handoff — 2026-11-14 — FAST-1 + GRD-2 building; AUTO-8 next

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- User: "Ok keep doing that, PRD approved" → docs/specs/fast-checks-and-guard-gaps.md approved (3e63433): FAST-1 (check.sh within 120 s; was ~139 s), GRD-2 (TD-016: Bash-made writes, quoted waivers, eval prd-shell-write-forced N=5 haiku), AUTO-8 (TD-020: fixers as processes, re-review after rebase). All three `[~]`.
- Running: FAST-1 developer in MAIN tree; GRD-2 developer in a WORKTREE.
- NOT approved (still the user's call): v0.1.0 tag, lpdan push for EVAL-3, merging the branch to main.

## Next steps
1. FAST-1 reports → verify (check.sh 3x within budget, gate), push → launch AUTO-8 developer in main tree (runner.py, test_runner.py).
2. GRD-2 reports → merge worktree, check.sh + gate, push, remove worktree.
3. After AUTO-8: push, republish dashboard, summary.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

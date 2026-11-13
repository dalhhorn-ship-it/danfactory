# Handoff — 2026-11-13 — GRD-1 + AUTO-4 done, pilot 2 succeeded; waiting on user

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- Done + pushed (51115ae): GRD-1 PRD write guard (prd-write-forced eval 10/10 blocked; no-prd-gate 10/10), AUTO-4 runner + review hardening + pilot-driven fixes (pyc caches, ignored .env mount point, base-health precheck, failure detail, sandbox marker, project-safe template tests). AUTO-1..4 ticked.
- Pilot 2 (semverlite) local only: /tmp/claude-0/-home-user-danfactory/cdc1dcd8-8974-5b99-914f-84c5a2d6140a/scratchpad/pilot-semverlite (ephemeral!). ISS-0001 fixed on attempt 1 (0.22 USD), on staging, main untouched; evidence copied to evals/spikes/pilot-semverlite/. Pilot dashboard artifact: https://claude.ai/artifact/B1KtvSLx28ZzdfksKRdJro. Template dashboard v12 republished.
- Spend 2026-11-13: pilot 3.02 USD (0.29 useful), GRD-1 evals ~2.6 USD, runner smokes ~0.25 USD.
- Open debt: TD-016 (guard gaps), TD-017 (bootstrap keeps template records; commands.test must exclude acceptance), TD-018 (issue titles over-masked), TD-019 (runner doesn't ratchet acceptance baseline). Template check.sh now ~114s vs 120s budget.

## Next steps
1. Ask user: GitHub repo for the pilot (else it is lost with the container); go for AUTO-5..7; fix TD-017..019 (recommend: yes, small).
2. Older: v0.1.0 tag (no answer), EVAL-3 blocked on lpdan push.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

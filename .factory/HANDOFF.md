# Handoff — 2026-11-11 — Evals: slices 1-2 done, eval-visualizations PRD awaiting approval

## Task
User wants behavioural evals added to danfactory, shown on its dashboard and on the landing page (portfolio proof of LLM-engineering skill). PRD approved by user in chat 2026-11-11.

## State
- Done: PRD docs/specs/agent-eval-harness.md approved (5c7abf5). Slice 1 EVAL-1 (6a17052): scripts/evals.py (list|run|baseline|compare), scripts/evals_graders.py, evals/tasks/ (10 tasks), evals/base/, .factory/tests/test_evals.py, ADR 0006, docs/policies/evals.md, factory.json `evals` block, metrics/evals.jsonl (15 real haiku spike rows). 160 tests green, check.sh ok.
- Done: slice 2 EVAL-2 Evals dashboard tab (9f7ebe1), dashboard artifact republished (factory.json dashboard_url).
- Waiting: user approval of draft PRD docs/specs/eval-visualizations.md (EVAL-4 library/heatmap/coverage map, EVAL-5 cumulative flow); 5 open questions in it. No code before approval.
- Branch: ccr-13a7396b-z4lqjz (pushed), uncommitted: none.

## Decisions (and why)
- Runner = headless `claude -p` via Python, not `claude plugin eval` (plugin-suite shaped; ours needs git-diff graders in a template copy). ADR 0006.
- User answers: budget 5 USD/run set, N=3; publish real pass rates incl. bad ones with N/model/date; transcripts local, git-ignored, 30 days; LLM-judge advisory only, slice 3.
- Landing page = repo dalhhorn-ship-it/lpdan (public/index.html, live at danfactory.dalhhorn.workers.dev). Read-only clone at /home/user/dalhhorn-ship-it/lpdan.

## Next steps
1. On approval: build EVAL-4 then EVAL-5 (developer agent), republish dashboard artifact.
2. Run a baseline set (N=3, sonnet, ≤5 USD) once user OKs spend; `evals.py baseline`.
3. Slice 3 EVAL-3: lpdan needs its own PRD (its PRD gate) and push access — add_repo push was DENIED by the auto-mode classifier; user must allow it or use a session on lpdan. lpdan GOAL: every claim must be true to the danfactory repo.
4. Older: user to set CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50 on Default env; ask before deleting old branches (claude/auto-compact-handoff-loop, claude/dashboard-backflow-from-minespel, cf-smoke-test); TD-001..011.

## Watch out
- danfactory is the TEMPLATE repo: never build a project here; eval runs happen in temp copies.
- Delete metrics/history.jsonl before committing (test runs create it).
- deploy-direct task passes without exercising the hook (agent declines first) — weak proof; noted in PRD spike findings.
- User is not technical on infra: explain plainly, recommend one option.

## Pointers
- docs/specs/agent-eval-harness.md (AC list, Spike findings), docs/decisions/0006-agent-eval-harness.md, docs/policies/evals.md
- docs/TECH-DEBT.md TD-010 (no network isolation), TD-011

# Handoff — 2026-11-12 — Gated-autonomy PRD drafted; waiting on user approval

## Task
User (PM, portfolio) asked: evaluate danfactory for full agentic engineering against the article "How we built the agents that built AWS Emulator" (Amazon News, 2026-11-11); what is great, what is missing; a PRD MD on the missing capabilities and why they matter; how to apply the article's thinking in steps; keep it on point and consistent.

## State
- Done: draft PRD docs/specs/gated-autonomy.md (0871921), written by product-manager, consistency-edited by main agent; docs index regenerated; check.sh green (241 tests). Presented to user in chat with approve / change / drop.
- In progress: nothing. PRD is `Status: draft`. No backlog items added (policy: only on approval).
- Branch: claude/intelligent-lamport-2g08xu, pushed; uncommitted: none.

## Decisions (and why)
- Verdict: danfactory is strong "supervised agentic" (L-B); article is swarm (L-D); target is gated autonomy (L-C) with 2 to 4 fixers.
- C1..C7 = steps 1..7 = AUTO-1..AUTO-7: merge gate, locked acceptance suite, issue ledger + finder, fixer loop with rework, auto-merge + release train, safe unattended running + parallelism, learning from rejections.
- PRD gate stays: issues from failing acceptance tests of an approved PRD fall under the existing bug-fix exemption (docs/policies/prd-approval.md).
- Recommended slice A = steps 1+2 (11 working days by size_days), spike on evals/base first.

## Next steps
1. Wait for the user's answer on the PRD and its 5 open questions (recommended: slice A; cap 3; 5 USD/day; staging branch; pilot on a small library or evals/base).
2. On approval: set Status approved, add M3 with AUTO-n items to docs/BACKLOG.md, software-architect design + ADR, then build slice A via background `developer`.
3. Still open from before: git tag v0.1.0 (asked, no answer); EVAL-3 `[!]` blocked on lpdan push access; TD-001..011.

## Watch out
- TEMPLATE repo: never build a project here.
- metrics/history.jsonl IS tracked (one row at caeb33a). Don't delete it; if a test run changes it, `git checkout HEAD -- metrics/history.jsonl` before committing.
- Don't edit the working tree while an eval run is going (runs copy it).
- User not technical on infra: plain words, one recommendation.
- Coverage budgets only alert in metrics.py report (lines ~242-247); they fail nothing. CI runs only check.sh + project tests.

## Pointers
- docs/specs/gated-autonomy.md (PRD), docs/operating-model/AGENT-ROUTING.md (ladder), docs/policies/evals.md, .github/workflows/ci.yml, scripts/evals.py (sandbox pattern to reuse for the runner)

# Handoff — 2026-11-07 — Auto-compact loop + dashboard CI card on main

## Task
Template (danfactory) maintenance. User asked to push all updates to main; two unmerged branches got retroactive PRDs, were approved, ported and merged.

## State
- Done, on `main` (9348669): auto-compact handoff loop (docs/specs/auto-compact-handoff-loop.md, ADR 0005) and dashboard delivery backflow (docs/specs/dashboard-delivery-backflow.md: CI pass rate/time card in scripts/obs/delivery.py, scripts/ci_runs.py, table-form TECH-DEBT). Both backlog items ticked. Tests green, check.sh ok.
- Branch: claude/determined-thompson-9lj0yu (== main + this note), uncommitted: none.

## Decisions (and why)
- PRD answers (user, 2026-11-07): compaction at 50% yes; agent continues after compaction (gates still apply) yes; measure cost after a few long sessions yes; CI card yes; one read-only GitHub call in CI yes; Now/Then/Later roadmap NO; table debt yes; drop rest of minespel branch yes.
- CI token via `${{ github.token }}` (test_deploy_security forbids `secrets.` in PR jobs).

## Next steps
1. User must set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` on the Default cloud env in Settings (session tools refuse reserved vars). Ask if done.
2. Ask user before deleting old remote branches: claude/auto-compact-handoff-loop, claude/dashboard-backflow-from-minespel (ported; dropped parts lost), cf-smoke-test (throwaway).
3. After a few long sessions: check compactions/session and weighted tokens in metrics/REPORT.md (PRD 1 decision 4).
4. Older open items: TD-001..009, owner-only security checks (see docs/TECH-DEBT.md).

## Watch out
- danfactory is the TEMPLATE repo only: never build a project here.
- metrics/history.jsonl is created by test runs and is not tracked; delete before committing.
- Agent worktrees live in .claude/worktrees/ (gitignored).
- User is not technical on infra: explain plainly, recommend one option.

## Pointers
- docs/decisions/0005-auto-compact-handoff-loop.md, docs/policies/token-economy.md
- .factory/tests/test_template.py (DeliveryBackflow, auto-compact tests)

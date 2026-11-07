# Handoff — 2026-11-07 — Dashboard observability merged to main

## Task
Template (danfactory) improvements. The user confirmed: **danfactory is the reusable template, not a project.** Its purpose is a proper development flow built on best practices; the decision tree decides what each project's build needs to be. So no GOAL.md here: template mode applies (DECISION-TREE Q0b).

## State
- On `main`: dashboard observability M1 (10 tabs: Overview, Roadmap, Architecture, Traceability, Decisions, Gates, Docs health, Flow, Cost, Hotspots), TD fixes for check records and session cost attribution, M1 retro, merged with main's template mode, security hardening S1–S7 and Roadmap v2.
- Merge fixes: our ADR renumbered 0003 → 0004 (main owns 0003 deploy-credential-scoping); our TDs renumbered to TD-004..009 (main owns TD-001..003); Traceability/Gates read item["spec"] from Roadmap v2's parser; template-mode test copies scripts/obs/.
- check.sh green (102 tests). Dashboard artifact v4+: https://claude.ai/artifact/26kZii7ybp45ynQBB47X8D

## Decisions (and why)
- CSS-only tabs, no JS; ADR docs/decisions/0004-dashboard-observability-design.md.
- Per-run records (check) go to gitignored metrics/records.local.jsonl; only rare gate records are committed.
- Cost attributes a session only when its commits reference exactly one item; mixed sessions are counted, never split.

## Next steps
1. Open TDs: TD-001 (cf_scaffold route B, needs PRD), TD-002/003 (security follow-ups), TD-004..007 (dashboard).
2. Owner-only checks from the security work: is CLOUDFLARE_API_TOKEN a repo or production-env secret? does `npx wrangler@4 deploy --help` run without prompting?
3. Traceability shows many "done, no commits" for template items: main's items predate the `Refs:` trailer convention. Use `Refs:` going forward.

## Watch out
- danfactory is the TEMPLATE repo only: never build a project here.
- scripts/dashboard.py > 350 lines: targeted reads only. Tab modules live in scripts/obs/.
- check.sh fails if the docs index is stale: run `python3 scripts/docs_index.py` after doc edits.

## Pointers
- PRDs: docs/specs/dashboard-observability-tabs.md, template-mode.md, security-hardening-audit-1.md, dashboard-roadmap-v2.md
- docs/BACKLOG.md, docs/TECH-DEBT.md, docs/operating-model/LEARNINGS.md

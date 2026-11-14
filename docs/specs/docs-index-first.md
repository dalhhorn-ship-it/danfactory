# PRD: Docs index-first, doc size budget, docs sync

> Status: approved · 2026-11-14 · by user in chat ("update documentation, split files that are too big, ensure we index versus reading full docs") · Owner: product-manager · Backlog: Unplanned → DOCS-1 · Upstream of lpdan docs/specs/agents-index-first.md (approved there 2026-11-07)

## Problem
11 of 20 agents never mention docs/INDEX.md, so subagents can read whole docs instead of the section they need. The index lists sections only for some long docs. Size monitoring checks code but not docs: the biggest docs are dashboard-observability-design.md (~6.2k tokens), gated-autonomy.md (~5.0k), runner.md (~3.8k), README (~3.6k) and TECH-DEBT.md (~3.6k). And the docs need a sync after this week's changes (pack, size, fast checks, guard).

## Scope and acceptance criteria
1. Every agent file has a short "Finding things" line: start from docs/INDEX.md (sections with line numbers) and `docs_index.py --related <doc>`, then make targeted reads. A structural test enforces it for all agents.
2. docs_index.py lists sections with start lines for every doc over `budgets.size.doc_tokens_sections` (default 1500 tokens), so a reader can jump to one section.
3. Size monitoring flags docs over `budgets.size.doc_tokens_warn` (default 3000) with the action "split by topic, or rely on the indexed sections". Policies and guides over the budget are split by topic. Specs and ADRs are records: they are not split, but their sections are indexed.
4. docs-sync pass: README, CLAUDE.md quick facts, policies, AGENT-ROUTING, the decision tree and path playbooks match the code today (autonomy pack, size budgets, fast checks, PRD guard, release/learn, pilot evidence). Every claim checked against the code; stale lines are removed rather than kept.
5. CLAUDE.md stays within its budget (always-loaded ≤ 2500 tokens with the start note).

## Effort
M. #process.

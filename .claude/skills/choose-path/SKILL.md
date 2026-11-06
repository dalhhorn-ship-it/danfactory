---
name: choose-path
description: Phase 2. Walk the decision tree with the agreed goal, pick the operating model (primary + optional secondary path), and write docs/OPERATING-MODEL.md with the agents, practices, habits, policies, commands and budgets for this project. Use after brainstorm, or when the project's nature changes.
---

# Choose path — pick the operating model

## Steps

1. Read `docs/GOAL.md` and `docs/operating-model/DECISION-TREE.md` (whole file is fine; it is kept short).
2. Walk the tree **with the user**: state each answer you inferred from GOAL.md and ask only about the ones you can't infer. Mixed goals get a **primary** path plus **secondary** paths (e.g. software-product + data-spreadsheet for an app that also ships an Excel export).
3. Check `docs/operating-model/LEARNINGS.md` for entries tagged with the candidate paths — apply them.
4. Read only the chosen path file(s) in `docs/operating-model/paths/`.
5. Pick the agent roster from docs/operating-model/AGENT-ROUTING.md (path rosters + verification ladder for the rigor level). Propose the operating model in ≤15 bullets: path(s), rigor level, roster, key practices, quality gates, budgets. Get a yes.
6. Write `docs/OPERATING-MODEL.md` from its headings. Be concrete: real commands, real thresholds, which subagents/skills are used when. Where a path default doesn't fit, override it and say why.
7. Update `factory.json`: `paths.primary`, `paths.secondary`, `agents.roster`, `commands.*` (once the stack is known — leave blank rather than guess), `budgets` overrides, `"phase": "build"`.
8. Record the choice as an ADR: `docs/decisions/0002-operating-model.md` (copy 0000-template.md).
9. If no path fits well, pick the closest, note the gap in LEARNINGS.md tagged `[tree-gap]` — `retro` will turn it into a new branch.
10. Seed `docs/BACKLOG.md` with `product-manager` (tick M0 items done; first milestone as S/M/L slices). For L2+ software or data paths, run the architect (`software-architect` / `spreadsheet-architect`) before building.
11. Run `python3 scripts/docs_index.py` and `python3 scripts/dashboard.py`. Offer to scaffold the first milestone.

## Rigor dial (state it explicitly)

| Level | When | Means |
|---|---|---|
| L0 spike | throwaway, < 1 week | no coverage gate, no CI, kill/promote date |
| L1 light | personal/internal, low risk | smoke tests, lint, docs for setup |
| L2 standard | others depend on it | TDD for logic, CI, coverage gate, ADRs, review agent |
| L3 high-stakes | money, PII, public internet, regulated | L2 + security audit before release, threat model, deploy checklist, rollback plan |

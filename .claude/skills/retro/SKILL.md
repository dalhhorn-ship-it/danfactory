---
name: retro
description: Milestone retrospective. Reviews metrics (test time, coverage, deploys, tokens), what slowed us down or cost tokens, and enriches the decision tree, path playbooks and LEARNINGS.md so the next project starts smarter. Use at milestones, after a painful session, or when the user says "retro" or "what did we learn".
---

# Retro — keep the factory learning

1. `python3 scripts/metrics.py report` and read `metrics/REPORT.md`.
2. Look at recent history cheaply: `git log --oneline -30`, and ask the user 2 questions: what was slow/annoying? what worked surprisingly well?
3. Write 1–5 entries in `docs/operating-model/LEARNINGS.md` using its entry format. Tag each with the path(s) and one of `[practice]`, `[tree-gap]`, `[budget]`, `[tooling]`, `[anti-pattern]`.
4. Act on them, smallest change that sticks:
   - wrong path chosen / missing branch -> edit DECISION-TREE.md and bump its version + changelog line (also `template.decision_tree_version` in factory.json)
   - a path default was wrong -> edit that `paths/*.md`
   - a budget is unrealistic -> edit `factory.json` budgets with the reason in the learning
   - an agent was over/under-used or mis-picked -> edit docs/operating-model/AGENT-ROUTING.md (bump its changelog)
   - a recurring manual step -> propose a hook, script or subagent
5. Update `docs/TECH-DEBT.md`: add debt found (use `engineering:tech-debt` for a fuller audit), move paid-down items to Resolved. Close or re-plan milestones in `docs/BACKLOG.md`.
6. Mark learnings that are general (useful for every future project) with `[upstream]`. Tell the user: "N learnings are marked [upstream]; send them with `python3 scripts/upstream_learnings.py --template <path to danfactory clone>`".
7. `python3 scripts/docs_index.py` and `python3 scripts/dashboard.py` (publish it per the `dashboard` skill if the user follows it there). Summarise in ≤8 bullets.

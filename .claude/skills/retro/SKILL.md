---
name: retro
description: Milestone retrospective. Reviews metrics (test time, coverage, deploys, tokens), what slowed us down or cost tokens, and enriches the decision tree, path playbooks and LEARNINGS.md so the next project starts smarter. Use at milestones, after a painful session, or when the user says "retro" or "what did we learn".
---

# Retro — keep the factory learning

1. `python3 scripts/metrics.py report` and read `metrics/REPORT.md`. If the runner or gate has recorded rejections, also run `python3 scripts/learn.py report` and read `metrics/LEARN.md`: its candidate rules (codes recurring past `autonomy.learn_threshold`) are suggestions to put to the user, each needing a PRD before it becomes a rule.
2. Look at recent history cheaply: `git log --oneline -30`, and ask the user 2 questions: what was slow/annoying? what worked surprisingly well?
3. **Fix the machine, not the instance.** Run `python3 scripts/retro_failures.py`. It lists recurring agent failures from blocked issues (`issues/blocked/`, only when the autonomy pack is in), repeated gate fail codes (`metrics/gate.local.jsonl`) and guard blocks (`metrics/guard.local.jsonl`); without the pack it still runs on the gate and guard data. Record each as exactly one class, with a proposed backlog item:
   - **context**: the agent lacked or misread information -> a doc, an index entry, a Reference source, a clearer PRD
   - **tool**: the agent had no cheap right way to do it -> a script, hook, command or subagent
   - **guardrail**: the wrong thing was possible or silent -> a gate check, guard rule or budget
   Show the list to the user; they accept or drop each one. Only accepted ones go to docs/BACKLOG.md, written by `product-manager` (a PRD first if it changes behaviour). Log every choice, accepted or dropped, as a LEARNINGS.md entry (step 4) tagged `[tooling]`, titled `Fix the machine: <class>, <item> (accepted|dropped)`. Do not fix the single instance in this step.
4. Write 1–5 entries in `docs/operating-model/LEARNINGS.md` using its entry format. Tag each with the path(s) and one of `[practice]`, `[tree-gap]`, `[budget]`, `[tooling]`, `[anti-pattern]`.
5. Act on them, smallest change that sticks:
   - wrong path chosen / missing branch -> edit DECISION-TREE.md and bump its version + changelog line (also `template.decision_tree_version` in factory.json)
   - a path default was wrong -> edit that `paths/*.md`
   - a budget is unrealistic -> edit `factory.json` budgets with the reason in the learning
   - an agent was over/under-used or mis-picked -> edit docs/operating-model/AGENT-ROUTING.md (bump its changelog)
   - a recurring manual step -> propose a hook, script or subagent
6. Update `docs/TECH-DEBT.md`: add debt found (use `engineering:tech-debt` for a fuller audit), move paid-down items to Resolved. Close or re-plan milestones in `docs/BACKLOG.md`.
7. Mark learnings that are general (useful for every future project) with `[upstream]`. Tell the user: "N learnings are marked [upstream]; send them with `python3 scripts/upstream_learnings.py --template <path to danfactory clone>`".
8. `python3 scripts/docs_index.py` and `python3 scripts/dashboard.py` (publish it per the `dashboard` skill if the user follows it there). Summarise in ≤8 bullets.

---
name: brainstorm
description: Phase 1. Interview the user about what they want to build, sharpen it into an agreed goal, and write docs/GOAL.md. Use at the start of a new project (factory.json phase "brainstorm"), when the user says "let's start", or when the goal changes materially.
---

# Brainstorm — agree the goal

You are a sharp thinking partner, not a form. Goal: leave with a GOAL.md the user signs off on.

## How to run it

1. Read `factory.json` and `docs/GOAL.md` (it may hold a previous draft). Don't read anything else yet.
2. Ask **2–3 questions per turn**, never a wall of 10. Start broad, then narrow. Cover, in roughly this order:
   - **Outcome**: what exists when this is done? Who uses it, and what changes for them?
   - **Artifact type**: software (app/API/service), library/CLI, spreadsheet/data model, document/deck, automation script, research/analysis, infrastructure, or a throwaway prototype? Possibly a mix.
   - **Constraints**: deadline, budget (incl. token spend), tech the user must/mustn't use, where it runs, who maintains it.
   - **Risk**: users' data? money? public internet? regulated? — drives security and testing depth.
   - **Lifetime**: one-off, months, years? — drives how much rigor is worth paying for.
   - **Success**: 1–3 measurable acceptance criteria. Non-goals.
3. Push back where useful: challenge scope creep, name the riskiest assumption, offer a smaller first milestone.
4. Summarise back in ≤10 bullets and ask "is this right?" before writing.
5. Write `docs/GOAL.md` using its existing headings. Keep it under ~80 lines.
6. Put the first milestone into `docs/BACKLOG.md` as `## Milestone: M1 — <name>` with its known items.
7. Set `"phase": "operating-model"` and fill `project.name` / `project.one_liner` in factory.json.
8. Tell the user the next step is `choose-path` and offer to start it now.

## Don't

- Don't propose architecture or pick tools here — that's `choose-path`.
- Don't read the codebase or docs beyond the two files above (token economy).
- Don't write GOAL.md before the user confirms the summary.

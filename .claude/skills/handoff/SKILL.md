---
name: handoff
description: Write a short structured handoff note (.factory/HANDOFF.md) so work can continue in a fresh, short context. Use at logical boundaries (task done, milestone, topic switch, before a long new task) or when the context-watch hook says the context is long; then ask the user to /clear. Also use when the user says "handoff", "wrap up" or "save state".
---

# Handoff: restart with the task and a note, not the whole history

Agents lose almost no accuracy when they restart from a short, structured note instead of the full history, and every turn gets cheaper (NVIDIA, "You don't need long context"). This skill writes that note.

## When
- **Good moments:** a task is done (definition of done met), a milestone closes, the topic changes, or the context-watch hook fired and you've reached a boundary.
- **Never** in the middle of debugging or a half-applied change. Finish the step or revert it first, so the next session starts from a consistent state.

## Write `.factory/HANDOFF.md` (40 lines or fewer, replace the previous note)
```markdown
# Handoff — <YYYY-MM-DD HH:MM> — <short title>

## Task
<the user's goal for this work, in 1–2 lines, in their words where possible>

## State
- Done: <what is finished and verified, with commit shas>
- In progress: <exactly where it stopped>; next command/edit: <…>
- Branch: <branch>, uncommitted: <none | files>

## Decisions (and why)
- <decision> — <reason> (ADR link if any)

## Next steps
1. <concrete next action>
2. <…>

## Watch out
- <gotchas, failed approaches not to retry, user preferences learned>

## Pointers
- <file:line or doc for each thing the next session needs; no pasted content>
```

Rules:
- Facts only: shas, paths, commands. No narrative of how you got here.
- Point to files instead of quoting them. The next session reads them on demand.
- Keep the user's open questions and preferences. Those get lost first.
- Commit the note with the work (`chore: handoff`), so cloud sessions on other machines can pick it up.

## Then
Tell the user: "Handoff written. Type `/clear` to continue in a fresh context. The note reloads automatically." If they'd rather keep the history, `/compact` also works; CLAUDE.md tells the compaction what to keep.

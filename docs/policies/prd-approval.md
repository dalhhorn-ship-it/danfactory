# Policy: PRD before build

> No feature work starts until the product-manager has written a PRD and the user has approved it in chat. Approval is explicit, recorded in the PRD, and never assumed.

## When it applies
Any new feature or change in user-facing or system behaviour, whatever its size, including changes to this template's own tooling (dashboard, scripts, agents).

Exempt (say so in chat when you use an exemption):
- A bug fix that restores behaviour an approved PRD or GOAL.md already specifies.
- Pure chores with no behaviour change: typos, docs-only edits, dependency bumps, formatting.
- An explicit prototype spike the user asked for (throwaway, never merged as-is).
- The user waives it in chat for a named piece of work ("skip the PRD for X"). A waiver covers only that work.

## Flow
1. **Ask arrives** → don't touch code. Delegate to `product-manager` to write `docs/specs/<slug>.md` from `docs/specs/_TEMPLATE.md` with `Status: draft`.
2. **Present it in chat**: post the PRD (or for long ones: problem, scope, acceptance criteria, non-goals, open questions, effort) plus the file path, and ask: *approve, change, or drop?*
3. **Stop and wait.** End the turn. Silence, "looks interesting", or answering an open question is not approval.
4. **Changes requested** → the product-manager revises, the main agent re-presents. Repeat.
5. **Approved** (an explicit "approve", "go", "build it" or similar) → set `Status: approved · <YYYY-MM-DD> · by user in chat`, add or update the item in docs/BACKLOG.md with a link to the PRD, then build.
6. **Scope drift during build** → a change to acceptance criteria or scope goes back to step 2 as a PRD revision. Implementation details inside the agreed scope don't.

## Enforcement
- The main agent checks for an approved PRD before writing code or delegating to `developer`, `code-writer` or `data-builder`.
- `developer` refuses to start (replies `BLOCKED — no approved PRD`) when the caller can't point to a PRD with `Status: approved`, unless the caller cites an exemption above.
- `jenny` and `task-completion-validator` verify against the approved PRD's acceptance criteria.

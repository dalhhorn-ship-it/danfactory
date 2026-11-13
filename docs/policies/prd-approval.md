# Policy: PRD before build

> No feature work starts until the product-manager has written a PRD and the user has approved it in chat. Approval is explicit, recorded in the PRD, and never assumed.

## When it applies
Any new feature or change in user-facing or system behaviour, whatever its size, including changes to this template's own tooling (dashboard, scripts, agents).

Exempt (say so in chat when you use an exemption):
- A bug fix that restores behaviour an approved PRD or GOAL.md already specifies.
- Pure chores with no behaviour change: typos, docs-only edits, dependency bumps, formatting.
- An explicit prototype spike the user asked for (throwaway, never merged as-is).
- The user waives it in chat for a named piece of work ("skip the PRD for X"). A waiver covers only that work. Urgency is not a waiver: "quick job", "just do it", "I'm in a hurry" or "do it all in this session" never skip the PRD. The user must name the work and say to skip the PRD step.

## Flow
1. **Ask arrives** → don't touch code. Delegate to `product-manager` to write `docs/specs/<slug>.md` from `docs/specs/_TEMPLATE.md` with `Status: draft`.
2. **Present it in chat**: post the PRD (or for long ones: problem, scope, acceptance criteria, non-goals, open questions, effort) plus the file path, and ask: *approve, change, or drop?*
3. **Stop and wait.** End the turn. Silence, "looks interesting", or answering an open question is not approval.
4. **Changes requested** → the product-manager revises, the main agent re-presents. Repeat.
5. **Approved** (an explicit "approve", "go", "build it" or similar) → set `Status: approved · <YYYY-MM-DD> · by user in chat`, add or update the item in docs/BACKLOG.md with a link to the PRD, then, at rigor L2+ or in autonomy mode, the acceptance tests before any build: `test-writer` writes them from the PRD, a separate fresh agent writes a throwaway implementation from the PRD alone (second reading), `python3 scripts/acceptance.py admit <slug> --reference-dir DIR` admits them. Ambiguities the test-writer finds come back to the user as PRD questions (a PRD revision), never settled silently. Then build.
6. **Scope drift during build** → a change to acceptance criteria or scope goes back to step 2 as a PRD revision. Implementation details inside the agreed scope don't.

## Enforcement
- The main agent checks for an approved PRD before writing code or delegating to `developer`, `code-writer` or `data-builder`.
- `developer` refuses to start (replies `BLOCKED — no approved PRD`) when the caller can't point to a PRD with `Status: approved`, unless the caller cites an exemption above.
- `jenny` and `task-completion-validator` verify against the approved PRD's acceptance criteria.
- **Write guard (GRD-1, docs/specs/prd-write-guard.md):** the PreToolUse hook `.claude/hooks/guard_prd_write.py` blocks Edit, Write, MultiEdit and NotebookEdit on product paths unless docs/BACKLOG.md has an in-progress item (`[~]`) linked to a `docs/specs/<slug>.md` with `Status: approved`, or an exemption is claimed for today. Subagents are not exempt. Always open: `docs/`, `issues/`, `tests/acceptance/`, `metrics/`, `.factory/`, `factory.json` (phase changes happen before any PRD can exist) and `*.md` at the repo root. Everything else is product, including `.claude/` (hooks and settings) and `CLAUDE.md`, which steer the agent and so need approved work. In project mode a `phase` before `build` blocks product writes whatever the backlog says; template mode (origin is `template.source_repo`) skips the phase check. A block prints what is missing and three ways forward: write and approve a PRD and mark the item `[~]`; claim an exemption; ask the user. The hook fails open (with a warning) only on its own internal errors, never on a missing PRD. It does not see Bash-generated writes (`echo > file`); the gate catches those.
- **Exemptions:** claim one by appending a line to `.factory/prd-exemption`: `YYYY-MM-DD <kind>: <reason>`, kind `bugfix` (restores behaviour an approved PRD or GOAL.md specifies), `chore`, `waiver` (the user waived it in chat for named work) or `spike` (a prototype the user asked for; the only kind that opens a pre-build phase). A line is valid on its own date only, so it lapses overnight; the file is tracked, so every claim is visible in git. The gate verdict lists active and expired claims. A claim is self-asserted: it makes a bypass visible, not impossible. Say so in chat when you use one.
- **Merge gate check `prd`** (docs/policies/merge-gate.md): commits in range that change product paths need `Refs:` to a backlog item (or PRD slug, or `ISS-n` whose issue names a PRD) with `Status: approved`, or a `PRD-Exempt: <reason>` trailer. Code `no-approved-prd`; `gate.prd` is `required` (default), `advisory` or `off`. This template sets `advisory` because it predates the rule.
- Blocks are counted in `metrics/guard.local.jsonl` (git-ignored); the dashboard Gates tab shows them with open exemptions and gate runs carrying `no-approved-prd`.

# PRD: PRD write guard (enforce "no approved PRD, no code")

> Status: approved · 2026-11-13 · by user in chat ("Ok build the guard", after the TD-015 finding was explained) · Owner: product-manager · Backlog: Unplanned → GRD-1 · Closes: TD-015

## Problem
The PRD gate is your main control over what gets built, but it is only an instruction. In the haiku N=10 eval run (TD-011), the agent wrote product code before any PRD existed in 2 of 10 runs of the no-prd-gate task. Nothing in the tools stops it, and CI does not check it either.

## Goal and success measure
An edit to product code is blocked unless approved work covers it, both while the agent works (hook) and at merge (gate). Success: the no-prd-gate eval passes 10/10 on haiku with the guard providing the block, and the gate fails a range that changes product code without an approved PRD or a stated exemption.

## Users and user stories
- As the product owner, I want code edits blocked until I approved the work, so that my PRD approval is a real gate and not a request.
- As a developer agent, I want a clear message that says what is missing, so that I write the PRD or mark the item instead of working around the block.

## Scope
1. **Hook.** A PreToolUse guard on Edit, Write, MultiEdit and NotebookEdit. A write to a product path is allowed only when docs/BACKLOG.md has an in-progress item (`[~]`) linked to a `docs/specs/<slug>.md` whose status is approved, or a current exemption exists. Some paths are always allowed: docs/, issues/, tests/acceptance/ (the test-writer), metrics/, .factory/, and docs-only files. In project mode a phase before `build` blocks product writes, except on the prototype-spike path. Template mode skips the phase check but keeps the in-progress rule.
2. **Exemption.** The policy's exemptions (bug fix restoring approved behaviour, chore, user waiver) are claimed in `.factory/prd-exemption`, one line with a reason and a date, valid for the current day. Every claim is visible in git and in the gate verdict.
3. **Gate check `prd`.** Product-code commits in range must carry `Refs:` to an item with an approved PRD, a `PRD-Exempt: <reason>` trailer, or a runner trailer for an issue of an approved PRD. The failure code is `no-approved-prd`. The mode is set by `gate.prd`: `required` by default in projects, `advisory` in the template.
4. **Eval.** Rerun no-prd-gate and behaviour-change-prd (N=10, haiku) and record proof strength.
5. **Dashboard.** The Gates tab shows guard blocks in the last 30 days, open exemptions and the `no-approved-prd` count.

## Non-goals
- Judging whether an edit is inside the PRD's scope (that stays with the reviewer and the acceptance suite).
- Blocking Bash-generated file writes (`echo > file`); the gate's `prd` check catches those at merge.

## Acceptance criteria
1. Given no in-progress item with an approved PRD and no exemption, when the agent edits a product file, then the edit is blocked with a message naming what is missing.
2. Given an in-progress item linked to an approved PRD, when the agent edits a product file, then the edit is allowed.
3. Given any state, when the agent edits a file under docs/, issues/, tests/acceptance/, metrics/ or .factory/, then the edit is allowed.
4. Given a same-day exemption line, when the agent edits a product file, then the edit is allowed and the exemption shows in the next gate verdict.
5. Given a commit range with product-code commits and no `Refs:` to an approved item and no `PRD-Exempt:` trailer, when the gate runs with `gate.prd: required`, then it fails with `no-approved-prd`.
6. Given haiku N=10, when no-prd-gate runs, then it passes at least 9 of 10 runs and the guard block shows in the hook evidence.
7. Given a project in phase brainstorm, when the agent edits product code, then the edit is blocked even if an item is in progress.

## Risks and assumptions
Main risk: false blocks slowing honest work. Mitigation: a clear message, the exemption file, and docs-only paths always open. Measure guard blocks on the dashboard.

## Effort and sequencing
M. Lane: technical foundation (#security). Build before step 4 merges, because the runner relies on it.

# PRD: Teach agents to fish (four lessons for the template's own tooling)

> Status: approved · 2026-11-20 · by user in chat ("ok implement 2-7 and forget fish 1") · Owner: product-manager · Backlog: Unplanned → FISH-2, FISH-5, FISH-6, FISH-7

## Problem
The AWS article "Teach an agent to fish and it will maintain your code for a lifetime" (Matt Goldberg, 2026-11-19, on AWS Emulator built by autonomous agents) says agents fail in repeatable ways, and the fix is to improve the machine, not patch the one case. Four lessons fit danfactory. Today: the test-writer sees only the PRD. The only protected path is `tests/acceptance/**`. The size check only warns. Retro does not force a "fix the machine" shape. GOAL.md is still the blank template, so traceability is to the template's purpose (gated autonomy, docs/specs/gated-autonomy.md).

## Goal and success measure
Each miss by the agents becomes a visible defect with one machine-level fix. Success: test-writer tests cite their sources; framework code has a safe owner; oversized files get split, not just flagged; retro ends with accepted or dropped backlog items.

## Users and user stories
- As the user, I want tests written against real docs I chose, so tests match the real world.
- As the user, I want shared conventions in code only humans change, so agents get an easy right path.
- As the user, I want big files split automatically, so agents can read them and merges stop clashing.
- As the user, I want each recurring failure turned into one concrete fix I can accept or drop.

## Scope
**FISH-2 Reference sources for the test-writer (S; base).** Optional "Reference sources" section in the PRD template. Test-writer reads the listed sources first and reports which it used. The second-reading agent gets them too.

**FISH-5 Human-owned framework code (M; base).** Guidance in software-product, library-cli and the software-architect agent: put cross-cutting conventions (auth, error format) in one framework folder with a default and one explicit override hook, and list the folder in `gate.protected`. Plus a way for a human-approved change to pass the gate: a second trailer `Framework-Change: <reason>`, valid only on paths in a new `gate.framework` list.

**FISH-6 File size as a rule, plus a split issue (M; gate half is base, issue half touches the pack).** New gate setting `gate.size` makes `file-over-size` fail instead of warn when a change grows a product file past `budgets.size.file_lines_max`. A file over budget also opens a "split this file" issue for the fixer.

**FISH-7 Fix the machine, not the instance (S; base, uses pack data when present).** Retro step: each recurring agent failure is recorded as exactly one of context, tool or guardrail, with a proposed backlog item for the user to accept or drop. Inputs: blocked issues, repeated gate fail codes, guard blocks.

**Shared design (FISH-6).** Only FISH-6 needs an issue not born from a failing test. An issue has a source (`test` by default, or `size`). A size issue has a machine-run closing check: the named file is at or under `budgets.size.file_lines_max`, and the tests pass. Today `issues.py sync` closes an issue only when it lists tests and all pass, so a non-test issue would never close. Keep it the smallest design that fits; it can be extended later.

## Non-goals
- FISH-1 (human-reported bugs with a class, dashboard report form): dropped by the user 2026-11-20; a bug the user reports is still handled in chat as today.
- Lesson 4 (use established libraries): not selected.
- Lesson 3 (issues reference failing tests): already built.
- Any internet access for agents; any change to the PRD approval gate.
- Auto-discovering sources.

## Acceptance criteria
**FISH-2**
1. Given a PRD with Reference sources, when test-writer runs, then its reply lists which sources it read and which it skipped.
2. Given a PRD without that section, when test-writer runs, then behaviour is unchanged.
3. Given a source that is not a file in the repo, when test-writer runs, then it does not fetch it; it reports "source missing" as a question.
4. Given text in a source that looks like an instruction, then test-writer treats it as data and its agent file says so.

**FISH-6**
5. Given gate setting `size: fail`, when a change grows a product file past `file_lines_max`, then the gate fails with `file-over-size`.
6. Given the default setting, then it still warns and never fails.
7. Given the fixer runner, then its own gate runs use `fail`.
8. Given a product file over budget, when the finder runs, then one split issue exists for it (no duplicates on rerun).
9. Given a split issue, when it is fixed, then all tests pass and no product file is over max; the issue then closes.

**FISH-5**
10. Given the two paths and the architect agent, then each tells agents to keep conventions in a framework folder with a default and one override hook, and to list it in `gate.protected`.
11. Given a framework folder in `gate.protected`, when a commit changes it without the approved trailer, then the gate fails `protected-path`.
12. Given the same change with a `Framework-Change` trailer on a path in `gate.framework`, then the gate passes.
13. Given an unattended fixer run, when it edits the folder, then the runner reverts it (as it does today for protected paths) and never writes the trailer itself.

**FISH-7**
14. Given recurring failures (blocked issues, repeated gate codes, guard blocks), when retro runs, then each is listed with exactly one of context, tool, guardrail and a proposed item.
15. Given the list, when the user accepts or drops each, then only accepted ones are written to the backlog (via product-manager) and the choice is logged in LEARNINGS.md.
16. Given a project without the autonomy pack, then retro still runs on gate and guard data.

## UX / behaviour notes
Plain words in every message. Without the pack there is no ledger, so the FISH-6 split issue is available only with the pack (docs/decisions/0011). FISH-2, FISH-5, FISH-7 and the FISH-6 gate setting work without it.

## Risks and assumptions
- Riskiest: the non-test (size) issue in FISH-6. Verified: `sync` needs a test list; the runner only picks open issues of approved PRDs. Build the design once, small.
- Verified: gate.py never reads `autonomy.enabled`; "mode" for the gate is its own keys (`review`, `prd`: off, advisory, required). So the size setting follows that pattern.
- Verified: the protected check accepts only `Acceptance-Change: <slug>` of an approved PRD that the test manifest knows. Framework code uses the separate trailer (decision 1).
- Verified: test-writer has no web tools, so URL sources cannot be fetched. Assumption: the user saves reference docs into the repo.
- Not verified: whether a new PRD section confuses `acceptance.py map`, and whether large reference files trip the doc-size flag. Check in the first FISH-2 test.
- Scale: the article's limit is 5,000 lines; ours is 700 (read-in-one-go budget). We keep ours.
- Trailers are self-asserted (TD-012); a human can still write their own.
- Touches protected machinery (gate.py, gate_checks.py, issues.py, runner): the fixer cannot edit these; humans build them.

## Effort and sequencing
Sizes: FISH-2 S, FISH-6 M, FISH-5 M, FISH-7 S. About 8 days at the dashboard's S=1, M=3. All technical foundation.
Build order: 1) FISH-2 (small, independent). 2) FISH-6 (sets the non-test issue design). 3) FISH-5 (after FISH-6: both edit the gate). 4) FISH-7 (last, reads the others' data).
Build status: not started

## Decisions (user, 2026-11-20)
1. Framework changes pass the gate with a second trailer `Framework-Change: <reason>`, valid only on paths in a new `gate.framework` list, never written by fixers or the runner.
2. The second-reading agent also gets the Reference sources.
3. The size setting is `gate.size`: `warn` (default) or `fail`; the fixer runner's own gate runs use `fail`.

Open questions: none.

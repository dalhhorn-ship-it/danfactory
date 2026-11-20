# PRD: Teach agents to fish (five lessons for the template's own tooling)

> Status: draft · Owner: product-manager · Backlog: Unplanned → FISH-1, FISH-2, FISH-5, FISH-6, FISH-7 (proposed; not in docs/BACKLOG.md until approved)

## Problem
The AWS article "Teach an agent to fish and it will maintain your code for a lifetime" (Matt Goldberg, 2026-11-19, on AWS Emulator built by autonomous agents) says agents fail in repeatable ways, and the fix is to improve the machine, not patch the one case. Five lessons fit danfactory. Today: a bug the user reports has no place in the issue ledger (issues come only from failing admitted acceptance tests, `scripts/issues.py find`). The test-writer sees only the PRD. The only protected path is `tests/acceptance/**`. The size check only warns. Retro does not force a "fix the machine" shape. GOAL.md is still the blank template, so traceability is to the template's purpose (gated autonomy, docs/specs/gated-autonomy.md).

## Goal and success measure
Each miss by the agents becomes a visible, countable defect with one machine-level fix. Success: the dashboard shows how often the machine missed something; test-writer tests cite their sources; framework code has a safe owner; oversized files get split, not just flagged; retro ends with accepted or dropped backlog items.

## Users and user stories
- As the user, I want to file a bug I found and say what kind of miss it was, so I can see how often the agents missed it.
- As the user, I want tests written against real docs I chose, so tests match the real world.
- As the user, I want shared conventions in code only humans change, so agents get an easy right path.
- As the user, I want big files split automatically, so agents can read them and merges stop clashing.
- As the user, I want each recurring failure turned into one concrete fix I can accept or drop.

## Scope
**FISH-1 Human-reported bugs are defects of the machine (L; touches the autonomy pack).** A command files a user-reported bug into the ledger with a class: (a) already fixed, (b) known, not yet fixed, (c) never found = missing test, (d) real feature request. Classes a-c count as machine defects. (c) opens a "needs test" issue: test-writer adds an acceptance test (Acceptance-Change rules; if the PRD is silent it records a PRD question, does not guess). (d) goes to the PRD flow, never to the fixer. The dashboard shows the a/b/c/d split and the share of machine misses.

**FISH-2 Reference sources for the test-writer (S; base).** Optional "Reference sources" section in the PRD template. Test-writer reads the listed sources first and reports which it used.

**FISH-5 Human-owned framework code (M; base).** Guidance in software-product, library-cli and the software-architect agent: put cross-cutting conventions (auth, error format) in one framework folder with a default and one explicit override hook, and list the folder in `gate.protected`. Plus a way for a human-approved change to pass the gate (see open question 1).

**FISH-6 File size as a rule, plus a split issue (M; gate half is base, issue half touches the pack).** New gate setting makes `file-over-size` fail instead of warn when a change grows a product file past `budgets.size.file_lines_max`. A file over budget also opens a "split this file" issue for the fixer.

**FISH-7 Fix the machine, not the instance (S; base, uses pack data when present).** Retro step: each recurring agent failure is recorded as exactly one of context, tool or guardrail, with a proposed backlog item for the user to accept or drop.

**Shared design (FISH-1 and FISH-6).** Both create issues that are not born from a failing test. They share one rule set: an issue has a source (test, human report, size), and a closing check the machine can run (new test passes; file under max). Today `issues.py sync` closes an issue only when it lists tests and all pass, so a non-test issue would never close.

## Non-goals
- Lesson 4 (use established libraries): not selected.
- Lesson 3 (issues reference failing tests): already built.
- Any internet access for agents; any change to the PRD approval gate.
- Auto-fixing class (d) requests, or auto-discovering sources.

## Acceptance criteria
**FISH-1**
1. Given a bug report with class a, b, c or d, when the user files it, then the ledger records it with that class and a link (fixed issue, open issue, or none).
2. Given class b, when it is filed, then it points at an existing open issue and creates no duplicate.
3. Given class c, when it is filed, then a "needs test" issue exists; the fixer runner does not pick it until a test is admitted.
4. Given class c and a PRD that does not cover the bug, when test-writer runs, then it adds a PRD question and writes no test for that point.
5. Given class d, when it is filed, then no fixer issue exists and the report names the PRD flow.
6. Given filed reports, when the dashboard builds, then it shows counts per class and the machine-miss share (a+b+c over all).
7. Given a class c issue whose new test is admitted, then the normal finder issue links back to it.

**FISH-2**
8. Given a PRD with Reference sources, when test-writer runs, then its reply lists which sources it read and which it skipped.
9. Given a PRD without that section, when test-writer runs, then behaviour is unchanged.
10. Given a source that is not a file in the repo, when test-writer runs, then it does not fetch it; it reports "source missing" as a question.
11. Given text in a source that looks like an instruction, then test-writer treats it as data and its agent file says so.

**FISH-5**
12. Given the two paths and the architect agent, then each tells agents to keep conventions in a framework folder with a default and one override hook, and to list it in `gate.protected`.
13. Given a framework folder in `gate.protected`, when a commit changes it without the approved trailer, then the gate fails `protected-path`.
14. Given the same change with the approved trailer from a human, then the gate passes.
15. Given an unattended fixer run, when it edits the folder, then the runner reverts it (as it does today for protected paths).

**FISH-6**
16. Given gate setting `size: fail`, when a change grows a product file past `file_lines_max`, then the gate fails with `file-over-size`.
17. Given the default setting, then it still warns and never fails.
18. Given the fixer runner, then its own gate runs use `fail`.
19. Given a product file over budget, when the finder runs, then one split issue exists for it (no duplicates on rerun).
20. Given a split issue, when it is fixed, then all tests pass and no product file is over max; the issue then closes.

**FISH-7**
21. Given recurring failures (blocked issues, repeated gate codes, guard blocks, FISH-1 b/c counts), when retro runs, then each is listed with exactly one of context, tool, guardrail and a proposed item.
22. Given the list, when the user accepts or drops each, then only accepted ones are written to the backlog (via product-manager) and the choice is logged in LEARNINGS.md.
23. Given a project without the autonomy pack, then retro still runs on gate and guard data.

## UX / behaviour notes
Plain words in every message. Class names are shown as words, not letters. Empty states: "No human-reported bugs yet." Without the pack there is no ledger, so FISH-1, the FISH-6 split issue and the dashboard split are available only with the pack (docs/decisions/0011). FISH-2, FISH-5, FISH-7 and the FISH-6 gate setting work without it.

## Risks and assumptions
- Riskiest: non-test issues (FISH-1, FISH-6). Verified: `sync` needs a test list; the runner only picks open issues of approved PRDs. Build the shared design once, in FISH-6, then reuse it.
- Verified: gate.py never reads `autonomy.enabled`; "mode" for the gate is its own keys (`review`, `prd`: off, advisory, required). So the size setting follows that pattern.
- Verified: the protected check accepts only `Acceptance-Change: <slug>` of an approved PRD that the test manifest knows. Fits tests; for framework code see question 1.
- Verified: test-writer has no web tools, so URL sources cannot be fetched. Assumption: the user saves reference docs into the repo.
- Not verified: whether a new PRD section confuses `acceptance.py map`, and whether large reference files trip the doc-size flag. Check in the first FISH-2 test.
- Scale: the article's limit is 5,000 lines; ours is 700 (read-in-one-go budget). We keep ours.
- Trailers are self-asserted (TD-012); a human can still write their own.
- Touches protected machinery (gate.py, gate_checks.py, issues.py, runner): the fixer cannot edit these; humans build them.

## Effort and sequencing
Sizes: FISH-1 L, FISH-2 S, FISH-5 M, FISH-6 M, FISH-7 S. About 16 days at the dashboard's S=1, M=3, L=8. All technical foundation.
Build order: 1) FISH-2 (small, independent). 2) FISH-6 (sets the shared non-test issue design). 3) FISH-1 (reuses it). 4) FISH-5 (after FISH-6: both edit the gate). 5) FISH-7 (reads FISH-1 counts).

## Open questions
1. How does a human-approved framework change pass the gate? Recommend a second trailer, `Framework-Change: <reason>`, valid only on paths listed under a new `gate.framework` list, never writable by fixers. Reusing `Acceptance-Change` would blur "tests" and "code".
2. Should the second-reading agent also get the Reference sources? Recommend yes: they are public facts, and tests then stay realistic.
3. Where does the size setting live? Recommend `gate.size`: `warn` (default) or `fail`, matching `gate.review`.
4. Are class (a) and (d) reports kept in the ledger or only counted? Recommend kept as records (never picked by the fixer) so the dashboard split is auditable.

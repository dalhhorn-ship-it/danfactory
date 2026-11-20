# 0013 — Size issues

> Status: accepted · Date: 2026-11-20

## Context
FISH-6 (docs/specs/teach-agents-to-fish.md) wants a "split this file" issue for a product file over `budgets.size.file_lines_max`. Until now an issue was born from failing acceptance tests and `issues.py sync` closed it only when it listed tests and all passed, so an issue without tests would never close. The runner picks only open issues of an approved PRD that list tests.

## Options
1. Fake a test per big file in the acceptance suite. Pollutes the locked acceptance area; rejected.
2. A second ledger for size issues. Duplicates find, sync, status and the dashboard.
3. One ledger; an issue gets a `source` (`test` default, `size`) and a source-specific closing check. Small: one optional header suffix and one module.

## Decision
Option 3. Header gains an optional ` · Source: size · File: <path>`; files without it read as `test`, so existing ledgers are unchanged. A size issue has no tests and `PRD: -`. Its closing check is "the file is at or under the max", run by `issues.py sync` (and the file filed once per path by `find`, reopened on regrowth, never duplicated). The code lives in `scripts/issues_size.py` (autonomy pack) so `issues.py` stays under the size budget. `find` is the finder's flow: no new subcommand.
"Tests pass" is part of the PRD's closing check, but `sync` does not re-run the suite: the gate (which the runner and every merge pass) already fails a change that breaks tests, so a split that closes the issue arrived through a green gate.
Size issues are not auto-picked by the runner. They have no PRD, and the `prd` gate check needs an approved PRD or exemption for the commit that fixes them; whether a behaviour-preserving split counts as covered is a policy decision for the user, not made here. The runner's own gate runs use `gate.size: fail` regardless of factory.json, so a fixer can never grow a file past the max.

## Consequences
Oversized files become visible work items that close themselves. A later decision can let the runner pick them. Dashboard counts include size issues (0 tests, PRD `-`). Closing depends on the file only, not on who split it.

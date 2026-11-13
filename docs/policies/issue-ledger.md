# Policy: issue ledger

> Failing admitted acceptance tests become files; fixed ones move. Design: docs/decisions/0008-issue-ledger-and-finder.md. Linked from docs/policies/merge-gate.md.

## Use
- `python3 scripts/issues.py find` files or updates issues from `acceptance.py run --json` (or `--from-json FILE`). Running it again creates no duplicate.
- `python3 scripts/issues.py sync` moves an open issue to `issues/fixed/` (with date and HEAD sha) once all its tests pass, and reopens a fixed one whose tests fail again.
- `merge ISS-a ISS-b` folds b into a; `split ISS-a <test-id>...` moves tests to a new issue; `list [--json]`; `status [--json]` gives the counts the dashboard uses.
- In autonomy mode the `finder` agent runs these after a build or a failing gate and writes the suspected root cause. Commit the ledger: issues are durable work items.
- `block ISS-a [--log TEXT]` parks an open issue in `issues/blocked/` (the fixer runner does this after its attempt cap, with an attempt log); `unpark ISS-a` moves it back to `issues/open/`. `find` leaves a parked issue alone and files no duplicate for its tests; `status` counts `blocked`. See docs/policies/runner.md.
- docs/BACKLOG.md stays the human roadmap; issues are the fine-grained work derived from failing tests.

## File format
`issues/open/ISS-NNNN-<slug>.md` (NNNN is sequential across both folders and never reused). Header line `> Status · PRD · Item · Fingerprint · Opened · Updated · Fixed`, then `## Failing tests`, `## Repro`, `## Suspected root cause`, `## Notes`. Failing tests and repro are regenerated on every run; the other sections are kept.

## Grouping
Fingerprint = hash of PRD slug, exception type, message with numbers and quoted literals masked, and the `where` frame without its line number. Tests already listed in an open issue stay with it; new failures join the open issue with the same fingerprint, else open a new one. Mechanical grouping is a first cut: the finder merges and splits.

## Dashboard
Autonomy tab, Issues block: open, fixed and blocked counts, opened and fixed per day (from git history of `issues/`), open by PRD, oldest open age, open issues. Empty until `issues/` exists.

## Honest limits
- The daily trend only counts committed ledger changes.
- The repro line uses `acceptance.py run --ids <id> <id>` (space-separated, as the AUTO-2 CLI takes them).

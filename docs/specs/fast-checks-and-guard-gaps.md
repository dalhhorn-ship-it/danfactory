# PRD: Fast template checks, PRD-guard gaps, parallel-fixer limits

> Status: approved · 2026-11-14 · by user in chat ("Ok keep doing that, PRD approved", after the recommendation to speed up checks and close TD-016 and TD-020) · Owner: product-manager · Backlog: Unplanned → FAST-1, GRD-2, AUTO-8

## Problem
1. The template's own check (`check.sh`, the gate's `structure` step) now takes about 139 s against the 120 s budget. Slow checks make every gated change slower and cost agent time.
2. The PRD write guard misses file writes made through shell commands (`echo > file`, `sed -i`, `tee`, `cp`, `python -c "open(...).write"`), and an agent can claim its own exemption (TD-016).
3. Parallel fixers run as threads in one process, so gate runs queue behind each other, and a fix that had to be rebased keeps its original review (TD-020).

## Scope and acceptance criteria
**FAST-1 Fast checks**
1. Given the template's check on this repo, when it runs on a typical change, then it finishes within `budgets.test_seconds` (120 s), and the gate's `structure` step does too.
2. Given slow tests (real sandbox, git-heavy, eval structure), when the everyday check runs, then they run in parallel or in a separate `slow` set that CI still runs in full on every push. No test is deleted or weakened.
3. Given CI, when it runs, then the full suite runs, and the timing per set is shown in the step summary.

**GRD-2 Guard gaps (TD-016)**
4. Given no approved in-progress item, when the agent writes a product file through a shell command (redirect, `tee`, `sed -i`, `cp`/`mv` into a product path, inline interpreter writes), then the Bash guard blocks it with the same message as the edit guard.
5. Given an exemption line written by the agent itself, when the guard reads it, then only `bugfix` and `chore` claims are honoured without the user. A `waiver` must carry the user's words in quotes from the chat and is shown as a warning in every gate verdict until it expires.
6. Given the gate in a project, when a range contains product files changed without a covering commit trailer, then `prd` fails as today. Bash-made writes are caught at merge even if a hook was bypassed.

**AUTO-8 Parallel-fixer limits (TD-020)**
7. Given `--parallel N`, when fixers run, then each attempt (fixer, review, gate) runs in its own process, so gate runs no longer wait on each other.
8. Given a fix that was rebased onto a newer staging tip, when it is merged, then the reviewer is run again on the rebased diff first; a `fix-first` verdict fails the attempt (`stale-after-merge`).

## Non-goals
Changing what the checks verify. Network access for fixers. Removing the user's controls.

## Effort and sequencing
FAST-1 M, GRD-2 M, AUTO-8 M; all technical foundation. FAST-1 and GRD-2 in parallel; AUTO-8 after FAST-1 (both touch the runner tests).

# 0010 — Release train, parallel fixers, learning from rejections

> Status: accepted · Date: 2026-11-14 · PRD: docs/specs/gated-autonomy.md (C5, C6, C7; criteria 11 to 18) · Builds on ADR 0009

## Context
Step 4 merges single fixes to staging. The user keeps three controls (PRD Decisions 6): approving PRDs, starting builds, and pushing or promoting to main. Steps 5 to 7 add batch safety, throughput and learning without moving any of those controls to an agent.

## Decision

### C5: release train (`scripts/release.py`)
- **`verify`**: a fresh checkout of the staging tip goes through the full gate, with the acceptance suite run against the baseline and every check, in the tree sandbox. It writes a promotion report to `metrics/releases.jsonl`, which is tracked. The report holds:
  - the commits staging has that main lacks;
  - the issues fixed;
  - the verdict and its codes;
  - cost since the last promotion.
- **`report`** prints the latest report in plain words, followed by the exact commands the user runs to promote: `git checkout main && git merge --no-ff staging && git push`. The script itself never merges into or pushes to the production branch.
- **`smoke-failed <sha> [--reason]`**: called by the user or deploy-watcher after a failed post-deploy smoke. It creates `revert/<sha>`, a branch with `git revert` of the promoted merge, and files an issue in the ledger with the smoke reason. The user pushes the revert. Nothing is pushed automatically.
- **Dashboard (Autonomy tab):** staging lead over main, the last verify verdict, time since the last promotion, and open revert branches.

### C6: parallel fixers
- **`runner.py run --parallel N`** (N from 1 to `autonomy.max_parallel`, default 1, cap 4) picks N open issues of approved PRDs that share no failing test and no fingerprint. Each gets its own worktree and fixer, in separate processes.
- **Merges stay serial.** Only one merge to staging at a time. Each fix is re-gated against the current staging tip before it merges. A fix that conflicts or fails after another merge gets one rebase-and-regate. If that fails it counts as a failed attempt, coded `stale-after-merge`.
- **The budget is shared.** Before each paid call the runner checks the daily cap against all fixers' spend so far plus the mean cost of the running calls.
- **Scheduled runs.** The runner refuses `--scheduled` unless `autonomy.schedule_ok` is true, which defaults to false and is the user's standing go. It then only works issues of PRDs already approved and in progress. The template never creates a schedule; docs/policies/runner.md shows how a user sets one up.
- **Network.** Fixers and reviewers keep the Bash sandbox with no network; this step adds none.

### C7: learning from rejections (`scripts/learn.py`)
- **`report`** reads `metrics/runner.jsonl` and the gate rows. It counts failure codes per period and the first-try pass rate. Codes that recur past `autonomy.learn_threshold` (default 3 in 14 days) are written to `metrics/LEARN.md` (gitignored) as candidate rules, with example attempts. `retro` reads that file.
- **New eval tasks, cheap and deterministic:**
  - `fixer-protected` (the fixer is asked to edit an acceptance test; graded by the protected path being unchanged);
  - `fixer-scope` (unrelated files untouched);
  - `fixer-reuse` (a stdlib facility exists; graded by the absence of a hand-rolled replacement pattern).

  They are mapped in evals/rules.json and run N=3 on haiku once (paid, small).
- **Autonomy view:** failure codes over time, rework per fixed issue, cost per fixed issue, candidate rules, and first-try pass trend. Empty states throughout.

## Consequences
Parallel fixers raise spend per hour; the shared cap bounds it per day. Serial merges with re-gating keep staging green at the cost of some re-runs. Candidate rules are suggestions: a human turns them into rules through the normal PRD gate.

# 0009 — Fixer runner: one issue, one sandboxed agent, gate decides, staging only

> Status: accepted · Date: 2026-11-13 · PRD: docs/specs/gated-autonomy.md (C4; criteria 8, 9, 10) · Closes: TD-012, TD-014

## Context
Steps 1 to 3 give a gate, a locked goal and bounded issues. Step 4 turns an open issue into a merged fix without a human editing code. The user's decisions bound it:
- the user starts every run (decides which builds happen);
- at most 3 attempts per issue;
- at most 5 USD per day;
- merges go to a staging branch only, and the user promotes to main.

## Decision
`scripts/runner.py` (stdlib):
- `run [--issue ISS-n | --next] [--model sonnet] [--max-attempts N] [--dry-run]`
- `status [--json]`
- `unpark ISS-n`

`second-reading <slug>` is added to `scripts/acceptance.py`.

**Preconditions.** All of these must hold, or the runner refuses with a reason:
- `factory.json` has `autonomy.enabled: true`, which defaults to false;
- the issue's PRD is approved;
- the working tree is clean;
- today's spend in `metrics/runner.jsonl` plus the mean attempt cost stays under `autonomy.daily_budget_usd` (5);
- the run's spend stays under `autonomy.run_budget_usd` (2).

The runner checks the budget before every attempt, never after.

**Attempt loop**, up to `autonomy.max_attempts` (3):
1. **Fresh worktree.** The runner makes a fresh git worktree from the tip of `autonomy.staging_branch` (`staging`, created from the current branch if missing) at `.claude/worktrees/runner-ISS-n`, on branch `fix/ISS-n`.
2. **Fixer runs in the sandbox.** A headless `claude -p` runs there with the same sandbox as the evals (allow-listed environment, throwaway HOME, Claude Code Bash sandbox with no network, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`, `acceptEdits` with an explicit tool list, `max_turns`). The shared code moves into `scripts/sandbox.py`, and evals behaviour does not change. The prompt holds:
   - the issue file;
   - the PRD path;
   - the rule never to edit tests/acceptance, the manifest or the baseline, and not to commit;
   - from attempt 2 on, the previous gate verdict's reasons.
3. **Runner commits.** The runner commits the fixer's changes itself, with trailers it controls: `Refs: ISS-n`, `Fixer-Attempt: k`, `Runner: <run id>`. A change under `gate.protected` is reverted and counts as a failed attempt with code `fixer-touched-protected`. A fixer can therefore never produce `Acceptance-Change` or `Review` trailers, which closes TD-012 for unattended work.
4. **Independent review.** A second headless agent with the reviewer prompt reads the diff and returns `ship` or `fix-first`. The runner writes the `Review:` trailer from that verdict, so the review is no longer self-asserted.
5. **Gate.** `gate.py --base <staging tip>` runs with `review: required` in the worktree.
6. **Pass.** The runner merges `fix/ISS-n` into staging with `--no-ff`, runs `issues.py sync`, and removes the worktree.
7. **Fail.** The runner records the failure codes and starts the next attempt.

**Cap reached** (criterion 8): the issue moves to `issues/blocked/` with an attempt log (codes, cost, last gate summary), and nothing merges. `unpark` moves it back after the user acts. issues.py and the dashboard learn the `blocked` state.

**Records.** `metrics/runner.jsonl` is tracked, like evals.jsonl: durable evidence of unattended work. It gets one row per attempt: run id, issue, attempt, model, cost, tokens, seconds, gate verdict and codes, review verdict, outcome. The rows are committed on staging with the merge or park.

**Never.** The runner never pushes, never touches the production branch, and never runs without the user's command. Promotion is the user's: `git checkout main && git merge --no-ff staging && git push` (documented, not scripted).

**Second reading (TD-014).** `acceptance.py second-reading <slug> [--model]` runs a headless agent in the same sandbox. It sees only the PRD and the public package layout, and it writes a throwaway implementation into a temp dir. Then `admit --reference-dir <tmp>` runs and the temp dir is deleted. Cost is recorded in runner.jsonl with kind `second-reading`.

**Dashboard.** The Autonomy tab gets a Runner block:
- runs and attempts;
- first-try pass rate;
- rework per fixed issue;
- cost per fixed issue;
- spend today against the cap;
- parked issues with their last codes;
- the staging branch's lead over main (commits not yet promoted).

## Consequences
Every attempt costs model money (fixer plus reviewer); the caps bound it. Fixes stack on staging until the user promotes. AUTO-5 adds batch re-verification and rollback. Parallel fixers wait for AUTO-6, so this runner is serial.

## Implementation notes (2026-11-13, AUTO-4)
Details the build settled, none of which change the decision:
- **Staging is the runner's ledger.** Rows, the `blocked` move and `unpark` are committed on `staging`; the runner merges the current branch into `staging` first when it moved ahead, and reads spend from the working tree plus the committed copy on `staging` so a checkout of main sees today's total. The project tree is written only by that merge.
- **Own gate module, extra protected paths.** The gate runs in-process from the runner's own scripts with `review: required` forced (no gate.py change). `RUNNER_PROTECTED` adds the gate and runner machinery, factory.json, `.claude/`, `issues/` and `metrics/` to `gate.protected` for fixer changes.
- **The issue's own tests are checked by the runner** before review and gate (`issue-not-fixed`): the gate's baseline comparison does not cover tests that were failing when admitted.
- **A fixer's own commit is squashed** (`git reset --soft` to the base) so only the runner's message and trailers survive.
- **Reviewer** is read-only (Read, Glob, Grep) and gets the diff in the prompt; its last line `VERDICT: ship|fix-first` decides the trailer.
- **Sandbox artifacts.** The smoke run showed Claude Code's Bash sandbox leaving empty mount-point files (`.env`, `package.json`, ...) in the working directory, which failed the gate (`env-file-added`). The runner removes the known untracked 0-byte ones before committing.
- **Second reading** shows the agent file paths and public signatures, not bodies; `scripts/sandbox.py` holds the shared sandbox, and `metrics/runner.jsonl` rows carry `kind` attempt, park, stop, unpark or second-reading.

## Hardening after review (2026-11-13, AUTO-4)
A review of the first build found seven safety gaps. None changes the decision; each is fixed inside it, with a test in `.factory/tests/test_runner.py`:
1. **Fixer-written code ran unsandboxed.** The runner evaluates a worktree only through `sandbox.TreeSandbox`: an allow-listed environment with no model credential and no proxy, throwaway HOME and TMPDIR, and bubblewrap with no network, the real home and the main project directory hidden, `scripts/`, `tests/acceptance/`, `factory.json`, `.claude/`, `.github/`, the baseline and `.git` mounted read-only. That covers `issues.results`, the gate's build, lint, tests and acceptance commands (`gate.WRAP`, set by the runner and by the new `gate.py --sandbox`; without the option the gate is unchanged) and the post-merge `issues sync` (which now reads results from a sandboxed fresh checkout via `--from-json`). No bwrap, or not Linux: refuse, like evals (`EVALS_SANDBOX=off` opts out of the isolation, not of the environment scrub). `$ACCEPTANCE_JUNIT` and the unittest result file now sit in a directory the runner creates outside the worktree and are rejected unless written after the run started.
2. **Ignored or untracked files** were invisible to the protected-path check but present when tests ran. After the runner commits, tests, review and gate each run on a FRESH detached checkout of the commit (verified clean with `status --ignored`), so they see exactly what would merge. Ignored files that match a protected path, and a changed `.gitignore` that would ignore a protected path, count as `fixer-touched-protected`.
3. **The reviewer was not read-only** (`--allowedTools` only pre-approves). It now runs with `--tools Read,Glob,Grep`, `--permission-mode dontAsk` (this claude version has no `default` mode; `dontAsk` denies anything not pre-approved) and a deny list, in its own fresh checkout, never the tree that is gated. After the review the runner checks that checkout's HEAD, git dir and status (`reviewer-modified-tree` otherwise).
4. **Diff truncation and verdict echo.** A diff over `DIFF_MAX` fails the attempt (`diff-too-large`) instead of being truncated. The verdict is read only from the last line of the reviewer's answer, which must be the JSON `{"verdict": ..., "nonce": ...}` with a per-review random nonce; text echoed from the diff counts for nothing (`review-unparsed`).
5. **Worktree identity.** Every runner git call on the fix worktree names `-C`, `--git-dir` and `--work-tree` taken from the main repository when the worktree was created. Before and after the fixer and the reviewer the runner checks `.git` (bytes), git dir, common dir and that HEAD is `refs/heads/fix/ISS-n` (`worktree-tampered`). Runner git commands run with `core.hooksPath=/dev/null`.
6. **Budget.** The cap is checked before every paid call (fixer, reviewer, second reading) and `--max-budget-usd` carries the remaining budget; the first estimate is `autonomy.attempt_estimate_usd` (0.5), not 0. A call that gives no usage (timeout, crash) is recorded at the estimate with `cost_estimated: true`. `acceptance.py second-reading` checks and records against the same daily cap.
7. **Lock and config.** The lock is taken inside the try/finally that releases it; a lock whose pid is gone or that is older than 2 hours is reclaimed with a note. `max_attempts` below 1 is a refusal, not a park.

Limits that remain are listed in docs/policies/runner.md (a test can still forge its own result file; the model credential still reaches claude).

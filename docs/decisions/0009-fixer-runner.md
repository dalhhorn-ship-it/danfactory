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

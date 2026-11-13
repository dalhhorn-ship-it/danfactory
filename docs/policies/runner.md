# Policy: fixer runner (autonomy mode)

> One open issue, one sandboxed agent per attempt, the gate decides, merges go to a staging branch only. Design: docs/decisions/0009-fixer-runner.md. Needs the ledger (docs/policies/issue-ledger.md) and the gate (docs/policies/merge-gate.md).

## Start a run
1. Set `factory.json` `autonomy.enabled` to `true` (it is `false` by default: nothing here runs, and no gate check changes, until you do). Settings: `staging_branch` (staging), `max_attempts` (3), `daily_budget_usd` (5), `run_budget_usd` (2), `model` and `review_model` (sonnet), `max_turns` (40). On Linux the Bash sandbox needs `bwrap` and `socat` (same as evals).
2. Have a clean working tree, an approved PRD for the issue, and the issue in `issues/open/` (`python3 scripts/issues.py find`; commit it).
3. `python3 scripts/runner.py run --next` (lowest open issue whose PRD is approved) or `--issue ISS-0007`. Add `--dry-run` to see the choice and the budget without spending. `--model haiku` and `--max-attempts 2` override the settings for one run. You start every run; nothing starts one for you.
4. `python3 scripts/runner.py status` (or the dashboard Autonomy tab) shows runs, attempts, first-try pass rate, rework per fixed issue, cost per fixed issue, spend today against the cap, parked issues with their last codes, and how far staging is ahead of main.

Exit codes: 0 fixed and merged (or nothing to do), 1 parked, 2 refused or usage error, 3 stopped by a budget cap.

## What a run does
Per attempt, at most `max_attempts`:
1. A fresh worktree from the tip of `staging` at `.claude/worktrees/runner-ISS-n` on branch `fix/ISS-n`. `staging` is created from your current branch if missing; when your branch has moved ahead, it is merged into `staging` first (a conflict stops the run).
2. A headless fixer (`claude -p`) works there in the eval sandbox: allow-listed environment, throwaway HOME and TMPDIR, Bash sandbox without network, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`, `acceptEdits` with an explicit tool list. The prompt holds the issue file, the PRD path, the rules, and from attempt 2 the previous gate reasons and reviewer notes.
3. The runner commits the result itself with its own trailers (`Refs: ISS-n`, `Fixer-Attempt: k`, `Runner: <run>`). A commit the fixer made on its own is squashed away. A change to `gate.protected` or to the gate and runner machinery (`RUNNER_PROTECTED` in scripts/runner.py: factory.json, `.claude/`, `issues/`, `metrics/`, gate.py, acceptance.py, runner.py, sandbox.py, issues.py, metrics.py, check.sh) is reverted and the attempt fails with `fixer-touched-protected`. A fixer therefore cannot produce an `Acceptance-Change` or `Review` trailer (TD-012 for unattended work).
4. The issue's own tests must pass (`issue-not-fixed` otherwise; the gate's baseline check does not cover tests that were failing when admitted). Then a second, read-only agent (Read, Glob, Grep) reviews the diff and ends with `VERDICT: ship` or `VERDICT: fix-first`; the runner writes the `Review:` trailer from it (no verdict line counts as fix-first, `review-unparsed`).
5. `gate.py` runs in the worktree with `review: required` (the runner's own gate module judges, not the fixer's copy).
6. Pass: `fix/ISS-n` is merged into `staging` with `--no-ff`, `issues.py sync` moves the issue to `issues/fixed/`, rows and ledger are committed on staging, the worktree is removed. Fail: the next attempt starts again from the staging tip with the reasons.

After the cap the issue moves to `issues/blocked/` with an attempt log and the last gate reasons, and nothing merges (the branch `fix/ISS-n` stays so you can read the last attempt). `python3 scripts/runner.py unpark ISS-n` puts it back in `issues/open/` after you acted (a PRD clarification, a test fix, a manual change). The finder does not file a duplicate for a parked issue.

## Caps
The budget is checked before every attempt, never after: stop if today's spend plus the mean attempt cost would pass `daily_budget_usd`, or this run's spend plus the mean attempt cost would pass `run_budget_usd`. A stop keeps the results so far, prints why, and leaves the issue open (exit 3). An attempt costs the fixer plus the reviewer. `metrics/runner.jsonl` (tracked, committed on staging) holds one row per attempt, park, stop, unpark and second reading; the daily total reads it from the working tree and from staging, so a checkout of main still sees today's spend. Days are UTC.

## Promote staging to main (you do this)
The runner never pushes and never touches the production branch. Review what accumulated, then:
```
git log --oneline main..staging          # what would land
python3 scripts/gate.py --base main      # optional: one gate over the whole stack (checkout staging first)
git checkout main && git merge --no-ff staging && git push
```
Update the acceptance baseline yourself (`python3 scripts/acceptance.py baseline`, with an `Acceptance-Change` trailer) once you accept the fixes: the runner does not ratchet it. After promoting, `staging` is merged forward by the next run.

## Second reading (TD-014)
`python3 scripts/acceptance.py second-reading <slug> [--model M]` starts an agent in the same sandbox in a temp directory. It sees the PRD and a layout of the project's source files (paths and public signatures, no bodies, no tests, no docs) and writes a throwaway implementation, then `admit --reference-dir` runs and the directory is deleted. Cost goes to `metrics/runner.jsonl` (kind `second-reading`). The separation is real (different process, no access to the tests or implementation) but not proven: see limits.

## Honest limits
- The fixer's worktree sits inside the project tree (`.claude/worktrees/`), not outside it. Writes outside it are blocked by the Bash sandbox and by `acceptEdits`, but the fixer can read the project tree around it (including an untracked `.env` in your checkout). Keep real secrets out of the project directory, or run the runner in a clone.
- The model credential reaches claude itself (it needs it); `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` hides it from the agent's commands. `EVALS_HOME=real` and `EVALS_SANDBOX=off` behave as in docs/policies/evals.md (the latter removes the isolation; the runner then is not isolated).
- Claude Code's sandbox leaves empty mount-point files (`.env`, `package.json`, `.gitmodules` and similar) in the working directory; the runner deletes the known ones before it commits (only untracked, 0 bytes).
- The reviewer is a second model run, not an independent human: it catches special-casing and scope creep, not everything. The gate and your promotion step are the real controls.
- Human-driven commits can still write their own trailers (TD-012 remains for them; the gate only makes it visible). One runner at a time (lock file); parallel fixers wait for AUTO-6.
- Cost is per attempt and varies by model and issue; haiku attempts in the smoke run cost about 0.01 USD, sonnet costs several times more. The mean-attempt estimate means the first attempt of a day is never blocked by the estimate.

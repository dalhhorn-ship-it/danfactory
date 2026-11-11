# Policy: agent evals

> Behavioural evals for the factory: a fixed task suite run by headless `claude -p` in disposable copies, graded by deterministic checks. Manual only, capped by a budget, never in CI.

## Why
The 124+ structural tests prove hooks and scripts work. They cannot tell whether the agent still honours the PRD gate, the deploy guard or the handoff loop after a change to CLAUDE.md, a hook, a skill or a model. Evals measure that as pass rates (PRD: docs/specs/agent-eval-harness.md, ADR: docs/decisions/0006-agent-eval-harness.md).

## How to run
```
python3 scripts/evals.py list                         # tasks, gates, graders
python3 scripts/evals.py run [--task ID] [--n 3] [--model sonnet]   # spends money
python3 scripts/evals.py baseline [--set SET]         # promote a run set (default: latest) to metrics/evals-baseline.json
python3 scripts/evals.py compare [--set SET]          # per-task and per-gate deltas; exit 1 on a drop beyond the threshold
```
Settings live in factory.json `evals`: `n` (runs per task), `model`, `budget_usd` (hard cap per run set), `regression_threshold` (pass-rate drop that counts as a regression; 0.34 means two lost runs of three), `max_turns`. The runner stops before the next run when cumulative cost plus the mean cost so far would pass the cap, keeps the rows, and says why.

Runs go round-robin (run 1 of every task, then run 2) so a stop leaves even coverage. Results: one row per run in `metrics/evals.jsonl` (append-only); raw transcripts in `metrics/eval-transcripts/` (git-ignored, pruned after 30 days, never publish). A task passing some but not all runs is flagged flaky. Rows whose claude call produced no result (infra error) are kept but not counted.

## Rules
1. **Manual only.** No eval step in any CI workflow or git hook; a structural test enforces it. Run after changing CLAUDE.md, a hook, a skill, an agent or the model.
2. **Cost.** Spend is real. Measured with haiku: roughly 0.01 to 0.06 USD per simple task run; a feature task costs more. Use `--task` and `--model haiku` while iterating; run the default model for baselines.
3. **Sandbox.** Each run copies the git-tracked files (working-tree content, so uncommitted template changes are tested; untracked new files are not) into a temp dir, turns it into a project copy (no `origin`, so not template mode; the template-mode task is the exception), overlays `evals/base/` and the task fixture, commits a baseline, then runs claude there. The graders, fixtures and eval docs are not copied in. danfactory's own tree is never written.
4. **Environment.** Only allow-listed variables reach the agent (see `ENV_ALLOW` in scripts/evals.py): PATH, locale, proxy and CA settings, and what claude itself needs to reach the API (`ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`). `CLOUDFLARE_*`, `GITHUB_*`, cloud and SSH variables are dropped. HOME is a throwaway directory. Where claude logs in through `~/.claude` (no token or base URL in the environment), set `EVALS_HOME=real`; the agent can then read that login, so only do it on a machine where that is acceptable.
5. **Permissions.** Runs use `--permission-mode acceptEdits` with an `--allowedTools` list, not `--dangerously-skip-permissions`, so the copy's settings deny rules and PreToolUse hooks still apply (verified: SessionStart, PreToolUse, PostToolUse and UserPromptSubmit hooks fire under `-p`, and the copy's CLAUDE.md loads).
6. **Graders** (scripts/evals_graders.py) check files, `git status` against the baseline and the tool-call log, not wording. The one answer check (`answer_matches`) tests a fact from the fixture. A command counts as run only if a guard did not block it. A task that depends on a model reply being accurate would need a judge; those wait for slice 3.
7. **Adding a task.** `evals/tasks/<id>/task.json` (id equal to the directory, title, gates, prompt, max_turns, graders; each grader has an id, a type from GRADERS and one of the task's gates) plus an optional `fixture/` overlay, `generate` (big files) and `write` (files .gitignore would hide). The structural tests validate the schema, build every fixture and check that a do-nothing agent does not pass outcome tasks.
8. **Dashboard.** The Evals tab (scripts/obs/tab_evals.py) shows the latest run set: pass rate per task and per gate, trend over run sets, tokens and cost per passing run, last run date, model, N, flaky tasks and regression status against `metrics/evals-baseline.json` ("no baseline" when absent). It only reads `metrics/evals.jsonl`; malformed lines are skipped and it never calls the model or the network. `python3 scripts/dashboard.py --print` has one Evals row.

# 0006 — Agent eval harness: headless runner, disposable sandbox, deterministic graders

> Status: accepted · Date: 2026-11-11 · PRD: docs/specs/agent-eval-harness.md

## Context
Gates and routing are instructions plus hooks; structural tests cannot show the agent still follows them. We need repeatable, cheap evidence per change, without CI cost or secret exposure.

## Options
1. `claude plugin eval` (case.yaml graders): aimed at plugin suites; weaker fit for filesystem checks in a template copy.
2. Headless `claude -p` driven by a Python stdlib runner: full control of sandbox, env and grading; JSON output carries cost, tokens, turns.
3. Agent SDK: more code and a dependency for no gain here.

## Decision
Option 2 (user, 2026-11-11), as `scripts/evals.py` plus `scripts/evals_graders.py`.
- **Runner:** `claude -p` on stdin, `--output-format stream-json --verbose --include-hook-events` (tool calls and hook events are needed for command-log graders and to prove hooks fire), `--permission-mode acceptEdits` and an explicit `--allowedTools`, never `--dangerously-skip-permissions` (it would also skip the guards under test). Cost is the cumulative `total_cost_usd`; tokens and turns are summed over result events (a background subagent can produce a second one).
- **Sandbox:** tracked files copied from the working tree into a temp dir, made a non-template project (template mode keys on the `origin` remote, so a copy without one is project mode), base project plus fixture overlaid, baseline commit so graders can diff. Allow-listed environment, throwaway HOME. Graders, fixtures and eval docs are excluded from the copy so the agent cannot read the answers.
- **Graders:** pure functions `(workdir, events, **params) -> (ok, detail)`, declared per task in JSON, each tagged with a gate; per-gate pass rate is derived from them. Filesystem, git status and tool-call log first; wording only for a fixture fact.
- **Results:** append-only `metrics/evals.jsonl` (committed), baseline in `metrics/evals-baseline.json`, transcripts local and pruned after 30 days. Regression = per-task or per-gate pass-rate drop beyond `evals.regression_threshold`.
- **Cost control:** `factory.json` `evals.budget_usd`, round-robin order, stop before a run when spend plus the mean run cost would pass the cap. Manual only; no CI step.

## Consequences
Evals need a working claude login and cost real money, so they are a maintainer action. Small N is noisy (see the spike findings in the PRD): treat a single drop as a prompt to rerun that task, not as proof. Fixtures depend on template files and can drift; the structural tests build every fixture to catch that. A guard that blocks a command and an agent that never tries it both pass the deploy task; only the first proves the hook, which is why the hook behaviour was checked separately in the spike.

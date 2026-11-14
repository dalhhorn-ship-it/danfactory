# 0011 — Autonomy as an optional pack; split large files

> Status: accepted · Date: 2026-11-14 · PRD: docs/specs/size-monitoring.md (SIZE-2, SIZE-3, approved by user in chat 2026-11-14)

## Context
SIZE-1 found about 4,500 lines that only matter in autonomy mode (opt-in, rigor L2+) but ship with every project. It also found five product files too large for an agent to read whole.

## Decision

### SIZE-2: the autonomy pack
**What moves.** These files move into the pack, listed in `packs/autonomy.json`:
- scripts: runner.py, release.py, learn.py and issues.py;
- the Autonomy tab, scripts/obs/tab_autonomy.py;
- tests: test_runner, test_release, test_learn and test_issues, plus the fixer eval tasks;
- the `finder` agent;
- policies: docs/policies/runner.md and issue-ledger.md.

**What stays in the base.** acceptance.py and sandbox.py stay, because the merge gate (L2+) and the evals need them. So does gate.py.

**The template keeps the full source.** In the template repo, the pack's files stay where they are, so the template still tests everything in one tree. The manifest only names them.

**Removal in new projects.** `bootstrap.sh` removes the pack's files unless `--with-autonomy` is given. It records the template commit it came from in `factory.json` `template.ref`, and `packs.autonomy` is set to false.

**Install later.** `python3 scripts/pack.py add autonomy` fetches exactly the manifest's files from `template.source_repo` at `template.ref`, a pinned full SHA verified like the skill installs (no curl|sh). It copies them in, sets `packs.autonomy: true` and runs the pack's tests. `pack.py remove autonomy` undoes it. `pack.py status` shows which packs are in and the lines each adds.

**Choosing it.** `choose-path` offers autonomy mode only at rigor L2+ with an approved executable spec. Choosing it runs `pack.py add autonomy` and sets `autonomy.enabled`.

**Without the pack.** Every base feature works: the dashboard shows "Autonomy pack not installed" with the one command to add it, the gate is unaffected, and the hooks are unaffected.

### SIZE-3: split the large files
Split runner.py (inside the pack's file list), acceptance.py, gate.py, dashboard.py and guard_bash_policy.py into modules under `budgets.size.file_lines_max`. The rules:
- behaviour, CLI and public imports stay the same;
- the existing tests pass unchanged, except for import paths where a test reached into internals;
- the manifest is updated for the moved runner modules.

**Module layout (built 2026-11-14).** Modules depend one way (no import cycles) except where noted; each old file stays as the facade.
- `scripts/runner.py` (CLI, commands, lock, `run_issue`) re-exports every name from `runner_core` (settings, rows, budget, summary), `runner_git` (worktrees, staging), `runner_agent` (prompts, `call_claude`), `runner_attempt` (`attempt`, `gate_verdict`), `runner_pick`, `runner_child` (attempt processes, AUTO-8), `runner_parallel`. `DIFF_MAX` lives in `runner_attempt`, so a test patches it there. The `runner_*.py` files are in `RUNNER_PROTECTED` and the pack manifest.
- `scripts/gate.py` keeps the helpers, `WRAP`, `config`, the basic checks and `run_gate`. `scripts/gate_checks.py` holds `security`, `prd` and `size`; it looks helpers up through `import gate` at call time so `gate.WRAP` and in-process patches stay in force. `gate.py` run as a script re-imports itself as `gate` for the same reason.
- `scripts/acceptance.py` keeps `config`, mapping, admit and the commands; `scripts/acceptance_exec.py` holds the unittest child, sandbox hook and JUnit parser (it must not import `config`, which tests patch).
- `scripts/dashboard.py` keeps `collect`, rendering and the tabs; `scripts/obs/board.py` holds backlog and debt parsing, versions, metric view and the roadmap model.
- `.claude/hooks/guard_bash_policy.py` keeps the command analysis; `.claude/hooks/_secretreads.py` holds the secret-file checks.

## Consequences
A new project starts about 4,500 lines lighter. The cost is one network fetch from a pinned commit when autonomy is chosen. Pack versions follow the template's commits; there is no separate versioning.

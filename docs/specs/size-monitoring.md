# PRD: Size monitoring (is the template still fit for purpose?)

> Status: approved · 2026-11-14 · by user in chat ("Overall evaluate how large this program has become, it needs to be fit for purpose. Implement size monitoring also in the dashboard to flag issues like this") · Owner: product-manager · Backlog: Unplanned → SIZE-1

## Problem (evaluation, 2026-11-14)
In three days (caeb33a → b2123fa) product code grew from 7,167 to 12,547 lines (+75%), tests from 3,389 to 7,223, scripts from 34 to 43, hooks from 8 to 11, agents from 18 to 20. Fixed context per session is still small (CLAUDE.md ~780 tokens, start note ~900 tokens). The costs are elsewhere:
- **Files agents cannot read whole.** The large-read guard stops at 350 lines; runner.py (1,199), acceptance.py (831), gate.py (724), dashboard.py (715) and guard_bash_policy.py (602) must be read in pieces every time, which costs tokens and invites mistakes.
- **Every project inherits all of it.** About 4,000 lines (runner, release, learn, issues, acceptance, sandbox) only matter in autonomy mode, which is opt-in. A vibe coder's landing page carries them anyway.
- **More surface, more defects.** The pilot found six template bugs, and TD-021 (git config wiped during parallel tests) is open.
- **Nothing warned.** Growth was only noticed because someone asked.

## Goal and success measure
Size is measured on every dashboard build and in the gate, with budgets in factory.json, so growth is a visible, deliberate decision. Success: today's oversized files and the growth spike show as flags; a change that pushes a file or area past its budget gets a gate warning naming it.

## Scope
1. **Measures** (scripts/obs, stdlib, offline): lines per area (product code, tests, docs, hooks, agents, skills, evals), file count, largest files, always-loaded context (CLAUDE.md tokens, SessionStart output tokens, agent and skill counts), test-to-code ratio, and growth over 7 and 30 days from git history.
2. **Budgets** in `factory.json` `budgets.size`, with defaults:
   - `file_lines_warn` 400, `file_lines_max` 700 (product code; tests excluded);
   - `always_loaded_tokens_max` 2500 (CLAUDE.md plus the start note);
   - `agents_max` 20;
   - `code_growth_30d_pct_warn` 25.
3. **Flags**: every breach shows as a dashboard alert (Overview) and on a new **Size** block in the Hotspots tab, with the file, the number, the budget and one suggested action (split the module, move it to an optional pack, raise the budget with a reason).
4. **Gate**: a `size` check that warns (never fails) with `file-over-size` or `size-growth` when the change range pushes a file or area past its budget.
5. **History**: the size snapshot is part of the dashboard data, so the trend can be plotted from git history without new tracked files.

## Non-goals
Splitting the big files or moving autonomy into an optional pack (separate decisions, proposed below); failing builds on size.

## Acceptance criteria
1. Given this repo today, when the dashboard builds, then runner.py, acceptance.py, gate.py, dashboard.py and guard_bash_policy.py appear as flagged files with their line counts, and the 30-day growth flag is raised.
2. Given a change that adds lines to a file already over `file_lines_max`, when the gate runs, then it warns `file-over-size` naming the file; the verdict still passes.
3. Given budgets edited in factory.json, when the dashboard builds, then the flags follow the new numbers.
4. Given a project without git history, when the dashboard builds, then growth shows "not enough history" and nothing fails.
5. `python3 scripts/dashboard.py --print` has a Size row.

## Follow-ups (approved by user in chat 2026-11-14: "ok implement these two, after size monitoring lands"; design ADR 0011)
- **SIZE-2:** move the autonomy machinery into an optional pack that `choose-path` installs only when autonomy mode is chosen. A new project then starts about 4,000 lines lighter.
- **SIZE-3:** split runner.py, acceptance.py, gate.py and dashboard.py below the budget, keeping behaviour and tests unchanged.

## Effort
M. Technical foundation (#quality).

## Acceptance criteria for the follow-ups
6. SIZE-2: given `bootstrap.sh` without `--with-autonomy`, when a new project is made, then the pack's files are absent, `factory.json` records `template.ref` and `packs.autonomy: false`, and check.sh, the dashboard and the gate pass.
7. SIZE-2: given that project, when `pack.py add autonomy` runs, then exactly the manifest's files arrive from the pinned commit and their tests pass. `pack.py remove autonomy` restores the lighter state.
8. SIZE-2: given the template repo itself, when check.sh runs, then the pack's tests still run (the template keeps the full tree).
9. SIZE-3: given the five large files, when split, then no product file exceeds `file_lines_max`, the CLIs behave the same, and the test suite passes without weakened tests.

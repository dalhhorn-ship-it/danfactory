# PRD: Eval visualizations (eval library, results heatmap, gate coverage map, cumulative flow)

> Status: draft · Owner: product-manager · Backlog: M2 → EVAL-4, EVAL-5

## Problem
The Evals tab (EVAL-2) shows pass rates, trend bars and flags, but it cannot answer three questions the maintainer now has. What does each eval actually test, and how much does a pass prove? Which factory rules have no eval at all? How does eval coverage relate to the work we ship? Today a pass can be weak: the direct-deploy task passes because the agent declined before reaching the deploy guard, so the hook was never exercised. Nothing on the page says so, and nothing lists the rules (CLAUDE.md, hooks, policies) that no task touches. The owner agreed on 2026-11-11 to two slices that make the suite legible and point the eval backlog at real gaps.

## Goal and success measure
Traceability: docs/GOAL.md is still the empty template; same stand-in as docs/specs/agent-eval-harness.md (a factory whose behaviour is verifiable and visible without chat). Success: from the Evals tab alone the maintainer can (a) see for each task what it tests, how strong its proof is and its recent runs, (b) see every factory rule that no eval covers, and (c) see backlog progress next to eval-verified progress over time.

## Users and user stories
- As the factory maintainer, I want one row per eval with gate, graders, covered backlog items, recent results and cost so that I know what the suite is and what it costs.
- As the maintainer, I want a "proof strength" label so that a pass where the agent never reached the guard is not mistaken for evidence the guard works.
- As the maintainer, I want a tasks-by-run-sets heatmap so that I see where results changed between sets.
- As the maintainer, I want a gate coverage map so that the uncovered rules become the eval backlog.
- As a user of a project created from the template, I want a cumulative flow of backlog items with a "covered by a passing eval" band so that I see how much of my delivered work is verified.

## Scope
Slice A (EVAL-4), all on the Evals tab, offline, no JS, inline SVG, like EVAL-2:
1. **Eval library.** One row per task in `evals/tasks/*/task.json`: what it tests (title and prompt summary), gate(s), backlog items it covers, graders, fixture link, date added (first commit of its task.json in git log), dot strip of the last 10 runs (pass/fail), cost per run, and proof strength.
   - Proof strength: **strong** = the guard or hook fired in the run (for example a recorded PreToolUse block); **weak** = the agent declined or never reached the guard; **n/a** for tasks with no hook to fire (for example fixture-only checks); **unknown** for runs recorded before the field existed.
   - This requires the runner to record hook-fired evidence per run: a new field in `metrics/evals.jsonl` rows (for example which hook events fired and whether any blocked). The runner already reads `--include-hook-events` streams; the new field is additive and old rows stay valid.
2. **Results heatmap.** Tasks (rows) by run sets (columns); each cell is that set's pass rate for the task, shown as colour plus the number (not colour alone). Empty cell where a task was not in the set.
3. **Gate coverage map.** A list of factory rules (CLAUDE.md rules, hooks in `.claude/settings.json`, `docs/policies/*`) with whether at least one eval covers each, and with what proof strength. The uncovered list is the eval backlog, shown first.

Slice B (EVAL-5): **Cumulative flow diagram** of backlog items over time with bands todo, doing, done, and done and covered by a passing eval.
- Needs a `covers: [backlog ids]` field in `task.json` (optional; absent means none).
- Item dates come from git history of docs/BACKLOG.md (when an item appeared, was started, was ticked).
- "Covered by a passing eval" means a task whose `covers` lists the item has a passing latest run set (rule fixed in design).
- Caveat: danfactory has about 16 items, so its chart is staircase-like. The real value is in projects created from the template, which accumulate more items. The slice must still render sensibly with few items.

## Non-goals
Deferred, may return later:
- Pass rate with confidence intervals.
- Trend with change markers (gate, hook or CLAUDE.md change annotated on the trend).
- Cost versus pass per model.

Not doing:
- Running evals from the dashboard, or any write action; the tab stays read-only.
- Auto-generating new eval tasks from uncovered rules.
- Network calls, JavaScript, or external chart libraries.
- Changing EVAL-3 (landing page and LLM-judge; blocked on push access to `dalhhorn-ship-it/lpdan`); it stays as is.
- Changing existing graders, task pass/fail semantics or the regression threshold.

## Acceptance criteria
1. Given tasks in `evals/tasks/`, when the dashboard builds, then the library shows exactly one row per task with title, gate(s), covered backlog items, graders, fixture link, date added, last-10-runs dot strip, cost per run and proof strength.
2. Given a run whose recorded hook evidence shows a guard or hook blocked a tool call, when the library renders, then that task's proof strength reads "strong"; given the agent never reached the guard, then "weak"; given no evidence field on any run, then "unknown", not an error.
3. Given the direct-deploy task as it passes today (agent declines before the guard), when the library renders with runs that carry the new field, then it is labelled "weak".
4. Given a new run, when the runner writes its row, then the row includes the hook-fired evidence field, and rows written before this change still parse and display.
5. Given two or more run sets, when the heatmap renders, then each task-by-set cell shows the pass rate as number and colour, a task absent from a set shows an empty cell, and the legend is present.
6. Given the rule inventory (source per open question 1), when the coverage map renders, then each rule shows covered or uncovered and by which tasks; uncovered rules are listed first as the eval backlog with their count.
7. Given a rule is covered only by weak-proof tasks, when the coverage map renders, then it is marked "covered (weak)", distinct from covered (strong) and uncovered.
8. Given tasks with `covers` ids and git history of docs/BACKLOG.md, when the flow diagram renders, then it shows cumulative counts per day for todo, doing, done, and done-and-covered-by-a-passing-eval, and the bands sum to the total item count at each date.
9. Given a backlog item id in `covers` that does not exist in docs/BACKLOG.md, when the dashboard builds, then it is ignored and listed as a data warning; the build does not fail.
10. Given fewer than 3 distinct dates of history (or zero items), when the flow diagram renders, then it shows a quiet sentence or a minimal staircase, never an empty axis or an exception.
11. Given `metrics/evals.jsonl` is missing or empty, or `evals/tasks/` is empty, when the dashboard builds, then each new view shows a quiet empty state with the command to run, and the build does not fail.
12. Given malformed input (a bad jsonl line, a task.json missing fields or invalid JSON, a git history that is unavailable such as a shallow clone or a copy without `.git`), when the dashboard builds, then the bad item is skipped or shown as "unknown", and the build does not fail.
13. Given the built page, when inspected, then it contains no `<script>`, no external URL fetch and no network call; charts are inline SVG and colour is never the only carrier of meaning.
14. Given `python3 scripts/metrics.py test`, when it runs, then structural tests for the library, heatmap, coverage and flow data derivations pass using fixture jsonl and fixture git history, without calling any model; `bash scripts/check.sh` passes.
15. Given a project created from the template (no danfactory-specific files), when the dashboard builds, then all views work from the template's own `evals/`, `.claude/settings.json`, CLAUDE.md and docs/policies, with no hard-coded danfactory paths or ids.

## UX / behaviour notes
- Order on the tab: gate coverage (uncovered first), library, heatmap, then flow in slice B. Existing EVAL-2 content stays.
- Dot strip: filled for pass, hollow for fail, oldest to newest; a task with fewer than 10 runs shows fewer dots.
- Proof strength is explained by a one-line legend and a tooltip text equivalent in plain text (no JS).
- "Date added" shows "unknown" when git history is unavailable.
- Heatmap columns are run sets in time order; show set date and N in the header.
- Cost per run is the mean over the runs shown, with currency stated.

## Risks and assumptions
- Riskiest: proof strength depends on the hook-fired evidence being captured reliably from the stream under `claude -p`. The spike (EVAL-1) showed hook events are emitted and a block is visible, but only a forced probe showed a block. Test cheaply: add the field, rerun the direct-deploy task and one forced-block probe, and confirm weak versus strong are told apart before building the label UI.
- Rule inventory: a scan of CLAUDE.md prose is fuzzy; a curated list can drift. See open question 1.
- Mapping tasks to rules relies on the `gates[]` field today; rules with no matching gate name may show as falsely uncovered. Mitigate with an explicit mapping in the inventory.
- Flow diagram value is low on danfactory itself (about 16 items). Assumption: it pays off in template-created projects; if not, it is the first thing cut. Hence slice B is sequenced second and can be dropped independently.
- Git-derived dates are approximate (a tick commit may batch several items) and absent in shallow clones; the page must label them as derived.
- Old rows lack the new field: proof strength is "unknown" for history, which can look like a regression in clarity; mitigate by showing it as grey "unknown", not weak.

## Effort and sequencing
- Slice A (EVAL-4): M. Runner field (S) plus three views. Technical dependency: the runner change must land first so the strength label has data.
- Slice B (EVAL-5): M. Depends on EVAL-4 (shares the task metadata reading) and on the `covers` field. Swimlane: both user value, with the runner field as a small foundation inside slice A.
- Order: A before B (higher value per effort, and B is the one with the weaker case on danfactory). Cut for now: confidence intervals, change markers, per-model cost.
- Architect decides module layout, how `covers` and the rule inventory are parsed, and the evidence field's shape.

## Open questions
1. Rule inventory source: a curated list file (for example `evals/rules.json`, one entry per rule with the gate name it maps to) or a scan of CLAUDE.md, `.claude/settings.json` hooks and docs/policies? Recommend a curated list seeded from a one-off scan, plus a structural test that every hook in `.claude/settings.json` appears in the list, so drift fails the tests.
2. Proof strength for tasks with no hook to fire (for example the PRD gate, which is an instruction, not a hook): label "n/a" or treat the gate grader result as strong? Recommend "n/a" with its own legend, so strong always means a hook fired.
3. "Covered by a passing eval" in the flow diagram: latest run set passing, or any passing run set? Recommend latest run set with pass rate at or above the regression threshold, so coverage lapses when an eval regresses.
4. Backlog "doing" state: BACKLOG.md has only open and ticked boxes. Derive doing from the first commit that references the item id, or drop the doing band? Recommend derive from first commit referencing the id, and show it as approximate.
5. Should slice B ship at all before a template-created project exists to try it on? Recommend build it (it is M and independent), but review it after the first real project and drop it if the staircase tells nothing.

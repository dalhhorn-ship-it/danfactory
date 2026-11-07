# Agent routing

> Which agent gets involved when. The main agent coordinates and decides; subagents are delegated to only when they save tokens or time, or add independence. Enriched by `retro`.

## Principles
1. **Main agent first** for small, conversational or judgment-heavy work. Delegate when the work is bulky (reading, logs, boilerplate), parallelisable, or needs a fresh, unanchored view.
2. **Cheapest adequate model**: Haiku for mechanical work, Sonnet for building and judging, Opus only for architecture and hard debugging.
3. **Verification ladder, not ritual**: run only the verifiers the rigor level asks for (below). Recommendations inside an agent's reply ("consult @x") are hints; follow them only if the ladder or a concrete finding justifies it.
4. **Never wait**: long-running watchers (deploy-watcher, big test runs) go in the background.

## By moment

| Moment | Trigger | Agent | Model |
|---|---|---|---|
| Adopt an existing build | in the other repo: `/danfactory:adopt` | bulk-reader (scan questions), karen (does it run?), product-manager (as-built backlog), software-architect (L2+) | mixed |
| Goal | phase `brainstorm` | main agent + `brainstorm` skill (needs the user live) | – |
| Plan | after choose-path; milestone start; backlog messy; after every slice (re-propose the build sequence before the dashboard refresh) | `product-manager` | sonnet |
| PRD (gate) | any feature or behaviour change, before design or build; user approves in chat (docs/policies/prd-approval.md) | `product-manager`, then main agent presents and waits | sonnet |
| Design (software) | software-product / library-cli / infra-ops at L2+, or a risky or large feature at any level | `software-architect` | opus |
| Design (spreadsheet/data) | data-spreadsheet path; restructuring a model | `spreadsheet-architect` | sonnet |
| Build: small change (< ~50 lines, one area) | – | main agent | – |
| Build: specified backlog item | approved PRD exists; can run in its own context; parallel slices | `developer` | sonnet |
| Build: boilerplate from a pattern | reference file exists | `code-writer` | sonnet |
| Build: workbook / data outputs | design exists | `data-builder` | sonnet |
| Read big things | file > 350 lines, 3+ files, logs, long diffs | `bulk-reader` | haiku |
| Run tests / builds | run `metrics.py test` directly (one line when green); delegate when it fails or output is long | `test-runner` | haiku |
| Debug | first attempt by the main agent fails, or production incident | `ultrathink-debugger` | opus |
| UI changed | user-facing screens or flows touched | `ui-comprehensive-tester` | sonnet |
| Task done? | see ladder | `task-completion-validator` | sonnet |
| Too complex? | see ladder | `code-quality-pragmatist` | sonnet |
| Ready to merge | see ladder | `reviewer` | sonnet |
| Follows our rules? | see ladder; drift suspected | `claude-md-compliance-checker` | haiku |
| Milestone done? | milestone claimed complete | `karen` (runs it) then, if spec-heavy, `jenny` | sonnet |
| Context getting long | context-watch nudge, or a logical boundary after a long session | `handoff` skill (main agent), then the user runs `/clear` | – |
| Docs | end of every task that changed behaviour | `doc-keeper` | haiku |
| Deploy | after every push | `deploy-watcher` (background) | haiku |
| Security | on request / L3 release | `security-audit-run` skill | – |

## Verification ladder (per task, by rigor in OPERATING-MODEL.md)

| Rigor | Always | Add when |
|---|---|---|
| L0 spike | – | – |
| L1 light | test-runner green | `ui-comprehensive-tester` if UI touched |
| L2 standard | test-runner green; `reviewer` before merge | `task-completion-validator` for M/L items · `code-quality-pragmatist` if a new abstraction or a diff over ~300 lines · `ui-comprehensive-tester` if UI touched |
| L3 high-stakes | L2 + `task-completion-validator` on every item | `claude-md-compliance-checker` before release · `security-audit-run` before release · `ultrathink-debugger` for any production incident |

Milestone end (L2+): `karen` always; `jenny` when GOAL.md or a spec has more than ~5 acceptance criteria; then `retro`.

## Tie-breakers (overlapping verifiers)

| Question | Pick |
|---|---|
| "Is this diff correct and mergeable?" | `reviewer` |
| "Does this one task really work?" | `task-completion-validator` |
| "Does the whole thing work, as claimed in BACKLOG/dashboard?" | `karen` |
| "Does it match the spec / acceptance criteria?" | `jenny` |
| "Is it over-built for our rigor level?" | `code-quality-pragmatist` |
| "Does it follow CLAUDE.md and our policies?" | `claude-md-compliance-checker` |
| "Feature work: developer or main agent?" | developer if specified and context-heavy or parallel; main agent if small or exploratory |
| "Design: which architect?" | code/services → software-architect; workbook/model → spreadsheet-architect; both if the product has both |

## Path rosters (defaults; choose-path writes the project's roster into OPERATING-MODEL.md and factory.json `agents.roster`)

| Path | Roster |
|---|---|
| software-product | product-manager, software-architect, developer, code-writer, test-runner, reviewer, task-completion-validator, ui-comprehensive-tester, karen, deploy-watcher, doc-keeper |
| library-cli | product-manager, software-architect, developer, code-writer, test-runner, reviewer, code-quality-pragmatist, doc-keeper |
| data-spreadsheet | product-manager, spreadsheet-architect, data-builder, test-runner, reviewer, karen, doc-keeper |
| documents-content | product-manager, reviewer, jenny, doc-keeper |
| research-analysis | product-manager, bulk-reader, reviewer, jenny |
| automation-script | developer, code-writer, test-runner, code-quality-pragmatist, deploy-watcher |
| infra-ops | software-architect, developer, reviewer, claude-md-compliance-checker, deploy-watcher |
| prototype-spike | developer, bulk-reader |
| adopt-existing | bulk-reader, karen, product-manager, software-architect, developer, ui-comprehensive-tester, doc-keeper |

`bulk-reader`, `test-runner` and `ultrathink-debugger` are available on every path when their trigger fires.

## Changelog
- 1.1.0 — adopt-existing moment and roster.
- 1.0.0 — 18 agents, ladder by rigor, tie-breakers, path rosters. Verifiers adapted from darcyegb/ClaudeCodeAgents (MIT).

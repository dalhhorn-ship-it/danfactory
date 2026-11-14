# danfactory

> A template for starting Claude Code projects. It gives you a guided start (brainstorm → decision tree → operating model), saves tokens by design, keeps the docs indexed, tracks delivery metrics, runs security audits on request, and deploys to Cloudflare via git.

## Start a new project

1. On GitHub: **Use this template → Create a new repository** (turn on *Settings → Template repository* for danfactory once). Or copy it by hand:
   ```bash
   git clone https://github.com/dalhhorn-ship-it/danfactory my-project && cd my-project && rm -rf .git && git init
   ```
2. Bootstrap. Add `--codegraph` to install the local code graph:
   ```bash
   bash scripts/bootstrap.sh "my-project" "one line description"   # flags: --codegraph, --cloudflare (Worker scaffold, route A: connect the repo in the Cloudflare dashboard)
   ```
   Bootstrap gives the project clean records: BACKLOG.md holds only the M0 set-up milestone, TECH-DEBT.md is empty, and the template's own PRDs, ADRs 0002 and up and LEARNINGS entries are removed (they stay in the template repo). It refuses to run in the template repo itself.
3. Start Claude Code (`claude`) and say **"let's start"**. The SessionStart hook tells Claude which phase you're in.

## Adopt an existing build (e.g. migrate a Lovable app)

Install danfactory once as a Claude Code plugin. Then, inside the other repo, run the `adopt` skill:

```bash
/plugin install danfactory --marketplace dalhhorn-ship-it/danfactory
```

```bash
/danfactory:adopt
```

It works on a `danfactory/adopt` branch and never overwrites your files:
1. Scans what was built (origin, stack, tests, CI, hosting, security and quality findings) into `docs/ADOPTION-REPORT.md`.
2. Uses the decision tree (Q0 → adopt-existing → the path to continue on) to choose the operating model.
3. Installs hooks, agents, skills, scripts, the docs index and CI, and merges settings, `CLAUDE.md` and `.gitignore`.
4. Drafts GOAL.md from the as-built state, seeds BACKLOG.md and TECH-DEBT.md, builds the dashboard, and writes `docs/NEXT-BUILDS.md`.

Lovable specifics (two-way sync, Supabase RLS, moving hosting to Cloudflare) are in docs/operating-model/paths/adopt-existing.md. Without plugins, run `bash scripts/install-adopt-skill.sh` from a danfactory clone; it installs `/danfactory-adopt` for your user.

## The flow

| Phase | Skill | Output |
|---|---|---|
| 1. Agree the goal | `brainstorm` (talks it through with you) | docs/GOAL.md |
| 2. Choose how to work | `choose-path` (decision tree, rigor L0–L3) | docs/OPERATING-MODEL.md, factory.json, ADR |
| 3. Build | path playbook + subagents | code / workbook / document … |
| Milestones | `retro`, `metrics` | LEARNINGS.md, tree updates, metrics/REPORT.md |
| Every build | `dashboard` (automatic) | dashboard/index.html: versions, progress, backlog, tech debt, key metrics, a Delivery card (CI pass rate, time, latest failures, weekly bars, release cadence from CHANGELOG or tags), a Hotspots tab with a Size block (files and growth against `budgets.size`, flags as alerts), a Roadmap tab (value vs technical-foundation swimlanes, one global build sequence, Next up, PRD badges; optional 6-month, proposed Gantt and Releases views) and an Evals tab (eval library with proof strength, results heatmap, rule coverage map, cost vs pass rate per model, flow of backlog items covered by evals). Styled after IBM's open-source Carbon design system, light and dark, offline, no JavaScript |
| What is broken right now | `python3 scripts/issues.py status` (`find`, `sync`; finder agent) | failing admitted acceptance tests become files in `issues/open/`, fixed ones move to `issues/fixed/`; dashboard Autonomy tab (docs/policies/issue-ledger.md) |
| Fix issues on their own (autonomy mode) | `python3 scripts/runner.py run --next` (`status`, `unpark`; `autonomy.enabled` in factory.json) | one sandboxed fixer per attempt, an independent review, the gate decides; up to 3 attempts and 5 USD a day; merges to `staging` only, you promote to main; failures are parked in `issues/blocked/` (docs/policies/runner.md) |
| Fix several issues at once, or on a schedule | `python3 scripts/runner.py run --next --parallel 3` (`autonomy.max_parallel`, default 1, cap 4); `--scheduled` only with `autonomy.schedule_ok: true` | one worktree and fixer per issue, merges one at a time and re-gated against the newest staging tip (`stale-after-merge` when that fails), one shared daily budget; a schedule is yours to create (cron or routine), runs only issues of approved PRDs whose backlog item is `[~]` (docs/policies/runner.md) |
| Promote autonomous fixes (you) | `python3 scripts/release.py verify`, then `report`; `smoke-failed <sha>` after a failed smoke | the staging batch goes through the full gate in the sandbox; the report lists commits, issues, verdict, cost and the exact promote commands; nothing pushes or merges to main, a failed smoke gets a `revert/<sha>` branch and an issue (docs/policies/runner.md) |
| Learn from rejected fixes | `python3 scripts/learn.py report` (`retro` runs it) | failure codes per week, first-try pass rate, and candidate rules (codes recurring 3 times in 14 days, `autonomy.learn_threshold`) with example attempts in `metrics/LEARN.md`; Autonomy tab Learning block; suggestions only, a rule needs a PRD (docs/policies/runner.md) |
| Ready to merge | `python3 scripts/gate.py` (CI job `gate`) | one verdict with reason codes: structure, build, lint, tests, acceptance, protected paths, review trailer, security scan of added lines, size warnings; recorded locally and shown on the dashboard Gates tab |
| On request | `python3 scripts/evals.py run` | behavioural evals: 13 tasks (incl. three fixer-loop tasks) run headless in throwaway copies of the template, checked on files, git diff and commands (not wording); results in metrics/evals.jsonl, compared with a stored baseline; budget cap in factory.json; never in CI |
| On request | `security-audit-run`, `ship` | audit report, live deploy |

### Agents (docs/operating-model/AGENT-ROUTING.md)

The 20 agents are routed by moment and rigor, not all run every time. A verification ladder decides how many checkers a task gets (none at L0, up to five at L3).

| Role | Agents |
|---|---|
| Plan & design | product-manager, software-architect (Opus), spreadsheet-architect |
| Build | developer, code-writer, data-builder |
| Cheap helpers (Haiku) | bulk-reader, test-runner, doc-keeper, deploy-watcher, claude-md-compliance-checker |
| Verify | reviewer, task-completion-validator, code-quality-pragmatist, karen, jenny, ui-comprehensive-tester |
| Autonomy | finder (files failing acceptance tests as issues, sonnet; software-product and library-cli) |
| Debug | ultrathink-debugger (Opus, only after a failed first attempt) |

The verifiers and debugger are adapted from [darcyegb/ClaudeCodeAgents](https://github.com/darcyegb/ClaudeCodeAgents) (MIT).

### Paths (docs/operating-model/paths/)

The paths are deliberately different, so a spreadsheet isn't run like a SaaS app.

| Path | Use for | Heavy lifting |
|---|---|---|
| software-product | apps, APIs, services | vertical slices, TDD, CI, git → Cloudflare |
| library-cli | packages, SDKs, CLIs | API-first, semver, examples as tests |
| data-spreadsheet | workbooks, models, CSV/reports | `data-builder` generator scripts + xlsx skill |
| documents-content | docs, decks, handbooks | outline-first, docx/pptx/pdf skills |
| research-analysis | research, comparisons, analysis | deep-research fan-out, sources ledger |
| automation-script | glue, jobs, bots | idempotent, dry-run, cron on Cloudflare |
| infra-ops | IaC, pipelines, DNS | plan/apply split, least privilege |
| prototype-spike | throwaway learning | time-box, kill/promote date |

## What's inside

| Piece | Where | Idea taken from |
|---|---|---|
| PRD write guard (no approved PRD, no product-code edit; gate check `prd`) | .claude/hooks/guard_prd_write.py, docs/policies/prd-approval.md | own design (GRD-1), closes TD-015 |
| Large-read guard + delegation subagents | .claude/hooks/guard_large_read.py, .claude/agents/ | [spotify shunt](https://github.com/spotify/portal-ai-plugins/tree/main/plugins/shunt), re-targeted from AiKA to native Haiku/Sonnet subagents |
| Docs quick-reference + doc knowledge graph | docs/INDEX.md, docs/knowledge-graph.json, scripts/docs_index.py | generated from headings and links; auto-refreshed by a hook |
| Code knowledge graph | `bash scripts/install-codegraph.sh` | [codegraph](https://github.com/colbymchenry/codegraph) (local, telemetry off) |
| Metrics: test time, coverage, deploys, tokens | scripts/metrics.py, metrics/ | budgets in factory.json; token use recorded at SessionEnd |
| Build dashboard | scripts/dashboard.py, docs/BACKLOG.md, docs/TECH-DEBT.md | regenerated by every metrics run and CI build; CI uploads it as an artifact |
| Behavioural evals | scripts/evals.py, scripts/evals_graders.py, evals/, docs/policies/evals.md | headless `claude -p` runs with deterministic graders; ADR 0006 |
| Security audit (on request) | `security-audit-run` skill | [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill), installed on demand |
| Short contexts + handoff notes | handoff skill, .claude/hooks/context_watch.py, pre_compact.py, session_start.py, CLAUDE.md compact instructions | NVIDIA "You don't need long context": note at logical boundaries, auto-compaction resets, note reloads automatically and work continues (no `/clear` needed) |
| No waiting on git/CI/Cloudflare | deploy-watcher subagent, scripts/wait-for-url.sh, .githooks/pre-push, docs/policies/async-delivery.md | push-and-continue, bounded waits, test once, skip docs-only builds |
| Deploy via git to Cloudflare | `ship` skill, templates/deploy-cloudflare.yml | [cloudflare-deploy skill](https://github.com/davila7/claude-code-templates/blob/main/cli-tool/components/skills/development/cloudflare-deploy/SKILL.md), installed on demand |

On-demand skills are listed in `factory.json → integrations.skills`. Install one with `bash scripts/install-skill.sh <name>`. They are git-ignored, so the template stays small and every install pulls the current version.

## Commands

```bash
bash scripts/check.sh                  # template self-checks (CI runs this)
python3 scripts/docs_index.py          # regenerate docs index + knowledge graph
python3 scripts/metrics.py test        # run tests, record time + coverage
python3 scripts/metrics.py report      # metrics/REPORT.md with alerts + suggestions
python3 scripts/dashboard.py --open    # build + open the project dashboard
python3 scripts/evals.py run --n 3 --model haiku   # behavioural evals (costs tokens; see docs/policies/evals.md)
python3 scripts/evals.py compare       # pass-rate change vs metrics/evals-baseline.json
python3 scripts/ci_runs.py            # refresh metrics/ci-runs.json (CI pass rate and time for the Delivery card; the only script that uses the network)
python3 scripts/archmodel.py --write   # refresh docs/architecture.json (dashboard Architecture tab)
bash scripts/install-skill.sh security-audit
bash scripts/install-skill.sh cloudflare-deploy
```

Requirements: git and python3 (stdlib only). Node/npm are needed for codegraph and wrangler only when you use them.

## Template mode (maintainers)

A checkout whose git `origin` is `template.source_repo` in factory.json (`dalhhorn-ship-it/danfactory`) is the template itself. There the session-start hook says "TEMPLATE repo" instead of suggesting brainstorm, the dashboard shows "Template maintenance" (open tech debt, then open Unplanned backlog items) instead of phase and progress, and `python3 scripts/metrics.py test` runs `.factory/tests` (`commands.test` stays empty so projects are unaffected). Any other origin, no remote or no git means project mode. Detection reads local git config only (helper `template_mode()` in .claude/hooks/_common.py). If you rename or move the template repo, update `template.source_repo`. A plain `git clone` of the template keeps its origin and so counts as the template until you change the remote.

## Feeding learnings back into the template

`retro` tags learnings that apply to every project with `[upstream]`. From the project, run `python3 scripts/upstream_learnings.py --template ../danfactory`: it appends unsent entries to the template's LEARNINGS.md, marks them `[upstreamed]`, and lists which shared docs (tree, routing, paths) differ, for you to port. Then open a PR in the template and bump the tree version. New projects then start from the improved tree.

## License

MIT, see [LICENSE](LICENSE). Some agents in `.claude/agents/` are adapted from darcyegb/ClaudeCodeAgents (MIT, see `.claude/agents/LICENSE-ClaudeCodeAgents.txt`). Skills fetched by `scripts/install-skill.sh` keep their own licenses (listed in factory.json under `skills`).

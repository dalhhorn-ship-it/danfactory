# danfactory

> A template for starting Claude Code projects. It gives you a guided start (brainstorm → decision tree → operating model), saves tokens by design, keeps the docs indexed, tracks delivery metrics, runs security audits on request, and deploys to Cloudflare via git.

## Start a new project

1. On GitHub: **Use this template → Create a new repository** (turn on *Settings → Template repository* once). Or copy by hand:
   ```bash
   git clone https://github.com/dalhhorn-ship-it/danfactory my-project && cd my-project && rm -rf .git && git init
   ```
2. Bootstrap. Add `--codegraph` to install the local code graph:
   ```bash
   bash scripts/bootstrap.sh "my-project" "one line description"   # flags: --codegraph, --cloudflare (Worker scaffold, route A: connect the repo in the Cloudflare dashboard), --with-autonomy, --template-ref <sha>
   ```
   Bootstrap cleans the records, omits the autonomy pack unless `--with-autonomy`, records the template commit (`template.ref`, found automatically) and lists the template's files in `.factory/template-files.txt` (unchanged ones are upstream, not your dashboard flags).
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
1. Scans what was built (stack, tests, CI, hosting, findings) into `docs/ADOPTION-REPORT.md`.
2. Uses the decision tree (Q0 → adopt-existing → the path to continue on) to choose the operating model.
3. Installs hooks, agents, skills, scripts, the docs index and CI, and merges your settings, `CLAUDE.md` and `.gitignore`.
4. Drafts GOAL.md from the as-built state, seeds the backlog and tech debt, and writes `docs/NEXT-BUILDS.md`.

Lovable specifics are in docs/operating-model/paths/adopt-existing.md. Without plugins, run `bash scripts/install-adopt-skill.sh` from a danfactory clone.

## The flow

| Phase | Skill | Output |
|---|---|---|
| 1. Agree the goal | `brainstorm` (a conversation) | docs/GOAL.md |
| 2. Choose how to work | `choose-path` (decision tree, rigor L0–L3) | docs/OPERATING-MODEL.md, factory.json, ADR |
| 3. Build | path playbook + subagents | code, workbook, document |
| Milestones | `retro`, `metrics` | LEARNINGS.md, metrics/REPORT.md |
| Every build | `dashboard` (automatic) | dashboard/index.html, offline, no JavaScript: progress, backlog, tech debt, delivery, roadmap, evals, hotspots with the Size block, autonomy |
| What is broken right now | `python3 scripts/issues.py status` (`find`, `sync`; finder agent) | failing acceptance tests become files in `issues/open/`, fixed ones move to `issues/fixed/` (docs/policies/issue-ledger.md) |
| Ready to merge | `python3 scripts/gate.py` (CI) | one verdict with reason codes: structure, build, lint, tests, coverage, acceptance, protected paths, PRD, review trailer, security scan of added lines; size is a warning only |
| On request | `python3 scripts/evals.py run` | behavioural evals: 16 tasks run headless in throwaway copies and are checked on files, git diff and commands, not wording; compared with a stored baseline; capped by a budget; never in CI (docs/policies/evals.md) |
| On request | `security-audit-run`, `ship` | audit report, live deploy |

### Agents (docs/operating-model/AGENT-ROUTING.md)

The 20 agents are routed by moment and rigor (none to five checkers per task, L0 to L3).

| Role | Agents |
|---|---|
| Plan & design | product-manager, software-architect (Opus), spreadsheet-architect |
| Build | developer, code-writer, data-builder |
| Cheap helpers (Haiku) | bulk-reader, test-runner, doc-keeper, deploy-watcher, claude-md-compliance-checker |
| Verify | reviewer, task-completion-validator, code-quality-pragmatist, karen, jenny, ui-comprehensive-tester |
| Autonomy | finder (files failing acceptance tests as issues, sonnet; software-product and library-cli) |
| Debug | ultrathink-debugger (Opus, only after a failed first attempt) |

### Paths (docs/operating-model/paths/)

Eight playbooks, deliberately different so a spreadsheet isn't run like a SaaS app: software-product, library-cli, data-spreadsheet, documents-content, research-analysis, automation-script, infra-ops, prototype-spike (plus adopt-existing for migrations).

## What's inside

| Piece | Where | Idea taken from |
|---|---|---|
| PRD write guard (no approved PRD, no product-code edit; gate check `prd`) | .claude/hooks/guard_prd_write.py, docs/policies/prd-approval.md | own design (GRD-1), closes TD-015 |
| Large-read guard + delegation subagents | .claude/hooks/guard_large_read.py, .claude/agents/ | [spotify shunt](https://github.com/spotify/portal-ai-plugins/tree/main/plugins/shunt), with native Haiku/Sonnet subagents |
| Docs quick-reference + doc knowledge graph | docs/INDEX.md, docs/knowledge-graph.json, scripts/docs_index.py | generated from headings and links; auto-refreshed by a hook |
| Code knowledge graph | `bash scripts/install-codegraph.sh` | [codegraph](https://github.com/colbymchenry/codegraph) (local) |
| Metrics: test time, coverage, deploys, tokens | scripts/metrics.py, metrics/ | budgets in factory.json |
| Short contexts + handoff notes | handoff skill, hooks context_watch.py, pre_compact.py, session_start.py | NVIDIA "You don't need long context": a note at logical boundaries, auto-compaction resets, the note reloads and work continues |
| No waiting on git/CI/Cloudflare | deploy-watcher subagent, scripts/wait-for-url.sh, .githooks/pre-push, docs/policies/async-delivery.md | push and continue, bounded waits, skip docs-only builds |
| Deploy via git to Cloudflare | `ship` skill, templates/deploy-cloudflare.yml | [cloudflare-deploy skill](https://github.com/davila7/claude-code-templates/blob/main/cli-tool/components/skills/development/cloudflare-deploy/SKILL.md), installed on demand |

On-demand skills (`factory.json → integrations.skills`) install with `bash scripts/install-skill.sh <name>`; they are git-ignored.

## Guard rails, in plain words

- **No approved PRD, no product code.** A PRD is a short written spec you approve in chat. A hook (`guard_prd_write.py`) blocks edits to product files, including writes made through shell commands, until `docs/BACKLOG.md` has an in-progress item linked to an approved PRD. The merge gate repeats the check on every commit (`prd`). Only `bugfix` and `chore` claims are honoured without you; a `waiver` must quote your own words (docs/policies/prd-approval.md).
- **Small by budget.** `factory.json` `budgets.size` sets limits and the dashboard Size block flags them as warnings, never failures: code files over 400 lines (warn) or 700 (max), CLAUDE.md plus the start note over 2,500 tokens, more than 20 agents, code growth over 25% in 30 days, docs over 3,000 tokens (policies get split by topic; specs and ADRs are records and stay whole, with indexed sections).
- **Index first.** Every agent starts from `docs/INDEX.md`, which lists each doc and, for docs over 1,500 tokens, its sections with start lines, so agents read one section, not the whole file. A hook blocks whole reads of files over 350 lines.
- **Fast checks.** `bash scripts/check.sh` runs the template's tests in parallel worker processes inside the 120 s budget (`budgets.test_seconds`); CI runs the full set. While working, `python3 scripts/metrics.py test --affected` runs only the tests a change touches (30 s budget).

## Autonomy pack

Autonomy mode lets the factory fix failing acceptance tests on its own, under strict limits; you start every run. It is optional (issue ledger, fixer runner, release train, learning loop, Autonomy tab, `finder` agent); `acceptance.py`, `sandbox.py` and `gate.py` stay in every project. New projects start without it. `choose-path` installs it when you pick autonomy mode (rigor L2+, approved executable spec), or add `--with-autonomy` at bootstrap, or run it yourself:

```bash
python3 scripts/pack.py status          # which packs are in, and the lines each adds
python3 scripts/pack.py add autonomy    # fetch exactly the manifest's files, run the pack's tests, set packs.autonomy true
python3 scripts/pack.py remove autonomy # delete them again
```

`add` fetches exactly the manifest's files with git from `template.source_repo` at `template.ref` in factory.json (a commit SHA bootstrap records or `add` finds itself; if it is wrong, `python3 scripts/pack.py add --ref SHA autonomy`). It verifies the SHA. In the template repo itself the files stay in the tree and `check.sh` tests them.

How it works, in plain words (docs/policies/runner.md):
- **Fix.** `python3 scripts/runner.py run --next` takes the oldest open issue whose PRD is approved. A sandboxed agent tries a fix, a second agent reviews it, and the gate decides. Up to 3 attempts and 5 USD a day by default; `--parallel N` works several issues at once (`autonomy.max_parallel`, default 1, cap 4); `--scheduled` needs your standing go (`autonomy.schedule_ok`). Fixes merge to a `staging` branch only; a failed issue is parked in `issues/blocked/`.
- **Release.** `python3 scripts/release.py verify` runs the full gate on the staging batch, `report` explains it and prints the exact promote commands, and you run them. Nothing reaches main by itself; `smoke-failed <sha>` after a bad deploy makes a `revert/<sha>` branch and an issue (docs/policies/runner-release.md).
- **Learn.** `python3 scripts/learn.py report` (the `retro` skill runs it) turns repeated failure codes (3 times in 14 days) into candidate rules in `metrics/LEARN.md`. They are only suggestions: a rule still needs a PRD.
- Limits and what the sandbox does not cover: docs/policies/runner-safety.md.

**Pilot evidence** (evals/spikes/pilot-semverlite): a library project made from the template, built from a 10-criterion PRD of the Semantic Versioning spec. Acceptance tests were written and admitted, then the runner fixed the one issue on attempt 1 and merged to staging: 11 of 11 tests pass, main untouched. The fix cost 0.22 USD; 2.72 USD went on six runs that failed for template reasons, each since fixed with a test.

## Commands

```bash
bash scripts/check.sh                  # template self-checks (CI runs this)
python3 scripts/docs_index.py          # regenerate docs index + knowledge graph
python3 scripts/metrics.py test        # run tests, record time + coverage
python3 scripts/metrics.py report      # metrics/REPORT.md with alerts + suggestions
python3 scripts/dashboard.py --open    # build + open the project dashboard
python3 scripts/evals.py run --n 3 --model haiku   # behavioural evals (costs tokens; see docs/policies/evals.md)
python3 scripts/evals.py compare       # change vs the stored baseline
python3 scripts/ci_runs.py            # refresh metrics/ci-runs.json (Delivery card; the only script that uses the network)
python3 scripts/archmodel.py --write   # refresh docs/architecture.json
bash scripts/install-skill.sh <name>   # security-audit, cloudflare-deploy
```

Requirements: git and python3 (stdlib only); Node/npm only for codegraph and wrangler.

## Maintaining the template

A checkout whose git `origin` is `template.source_repo` in factory.json is the template itself (session start says "TEMPLATE repo", tests are `.factory/tests`); any other origin is a project. Learnings that apply to every project flow back with `python3 scripts/upstream_learnings.py --template ../danfactory`. Details: docs/policies/template-maintenance.md.

## License

MIT, see [LICENSE](LICENSE). The verifier and debugger agents are adapted from [darcyegb/ClaudeCodeAgents](https://github.com/darcyegb/ClaudeCodeAgents) (MIT, `.claude/agents/LICENSE-ClaudeCodeAgents.txt`). Fetched skills keep their own licenses.

# CLAUDE.md

> Always-loaded instructions. Keep short and stable (it is paid every turn). Details live in docs/ — find them via docs/INDEX.md.

## Workflow (state in factory.json → `phase`)
1. **brainstorm** — no agreed goal yet: run the `brainstorm` skill with the user → docs/GOAL.md.
2. **operating-model** — run `choose-path`: walk docs/operating-model/DECISION-TREE.md → docs/OPERATING-MODEL.md, factory.json paths/commands/budgets.
3. **build** — follow docs/OPERATING-MODEL.md. At milestones run `retro` to enrich the tree and LEARNINGS.md.

Don't skip ahead: no code before GOAL.md is confirmed and an operating model is chosen (except an explicit prototype-spike).

## Token economy (docs/policies/token-economy.md)
- Read docs/INDEX.md first, then targeted reads at `file:line`. Whole reads of files > 350 lines are blocked by a hook.
- Delegate per docs/operating-model/AGENT-ROUTING.md (moment → agent, verification ladder by rigor). Always: big reads → `bulk-reader`, failing/long test output → `test-runner`, deploy watch → `deploy-watcher` (background).
- Use codegraph for code navigation when `integrations.codegraph` is true.

## Definition of done (every task)
- Tests via `python3 scripts/metrics.py test` pass (prints one line when green; hand failures or long output to `test-runner`); nothing skipped to get green.
- Docs updated in the same change (`docs-sync`); decisions → ADR in docs/decisions/.
- Backlog item ticked in docs/BACKLOG.md; deliberate shortcuts logged in docs/TECH-DEBT.md.
- `bash scripts/check.sh` passes.

## Status
`python3 scripts/dashboard.py --print` for a cheap status; `dashboard` skill to show the full page.

## Deploy and security
- Production deploys only via git → Cloudflare (`ship` skill). Direct `wrangler deploy` is denied.
- Never wait on builds: push, launch `deploy-watcher` in the background, keep working (docs/policies/async-delivery.md).
- Security audits only on request or before an L3 release (`security-audit-run`).
- Never commit secrets; `.env*` and `.dev.vars` are off limits.

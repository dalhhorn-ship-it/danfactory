# Path: software-product

> Apps, APIs, services with users. Default rigor L2 (L3 if money/PII/public). Goes live via git → Cloudflare (`ship`).

## Operating model
1. Spec: turn GOAL.md into a short spec (`product-management:write-spec` for larger scopes). Architecture choices with alternatives → ADR (`engineering:architecture`).
2. Walking skeleton first: repo, CI, test runner, one route deployed to a preview URL on day one.
3. Build in **vertical slices** (one user-visible capability per PR), TDD for domain logic, thin tests at the edges.
4. Every slice: tests green → docs-sync → reviewer → merge → Cloudflare deploys from git.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Understand big/unknown code | codegraph explore, bulk-reader |
| Boilerplate (CRUD, tests, fixtures) | code-writer with a reference file |
| Run tests, read logs | test-runner (`metrics.py test --affected` in the inner loop) |
| Independent review | reviewer, `/code-review` |
| Test design | `engineering:testing-strategy` |
| Go live | `ship` (+ cloudflare-deploy reference), `deploy-watcher` in the background |
| Before L3 release | `security-audit-run`, `engineering:deploy-checklist` |

## Defaults
- Stack: whatever GOAL.md constrains; otherwise TypeScript on Cloudflare Workers (+ D1/KV/R2 as needed) keeps deploy-via-git trivial.
- Commands to set in factory.json: test, test_affected, coverage, lint, build.
- Budgets: full tests ≤ 120s, affected ≤ 30s, coverage ≥ 80% on domain code, push-to-live ≤ 180s.
- Deploys are asynchronous: push → background `deploy-watcher` → keep working (docs/policies/async-delivery.md).

## Quality gates
- [ ] tests + lint green in CI; no skipped tests added
- [ ] coverage not below budget / not dropping > 2 pts
- [ ] preview URL smoke-tested before merge
- [ ] docs-sync done; ADR for decisions
- [ ] L3: security audit has no open confirmed High/Critical

## Anti-patterns
- Building all layers before anything is deployable.
- Letting test logs or large files into the main context.
- Deploying from a laptop with `wrangler deploy` (git only).

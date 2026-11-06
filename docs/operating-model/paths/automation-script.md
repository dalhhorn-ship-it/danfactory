# Path: automation-script

> Glue code, integrations, scheduled jobs, bots, one-purpose scripts. Default rigor L1.

## Operating model
1. Write the contract: trigger, inputs, outputs, side effects, failure behaviour.
2. Idempotent by design; `--dry-run` flag for anything with side effects; structured logs.
3. A few focused tests on parsing/transformation; integration check against a sandbox or fixture.
4. Scheduled/hosted? Cloudflare Workers Cron Triggers via `ship`, otherwise document where it runs.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Script scaffolding from an example | code-writer |
| API exploration | bulk-reader on API docs; never paste full specs |
| Hosting a job | `ship` (Cron Triggers / Queues) |

## Quality gates
- [ ] dry-run output reviewed; re-running is safe
- [ ] secrets from env/secret store only; README says how to run

## Anti-patterns
- Over-engineering (frameworks, layers) for a 200-line script. Silent failures.

# Path: infra-ops

> Infrastructure as code, CI/CD pipelines, cloud config, DNS, access. Default rigor L3 (blast radius).

## Operating model
1. Every change is code (Terraform/Pulumi/wrangler config) reviewed as a diff; **plan and apply are separate steps**, apply only after the user approves the plan.
2. Least privilege tokens, scoped per environment; secrets in a secret store.
3. Rollback written down before applying.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Cloudflare resources (DNS, WAF, Workers, R2...) | cloudflare-deploy reference skill (`references/terraform`, `references/api`) |
| Review of plan output | reviewer (bulk-reader for very long plans) |
| Security review | `security-audit-run` (CLOUD-AND-DEPLOYMENT, SUPPLY-CHAIN classes) |
| Release checklist | `engineering:deploy-checklist` |

## Quality gates
- [ ] plan reviewed and approved; no unexpected destroys
- [ ] tokens/IAM least-privilege; no secrets in state or repo
- [ ] rollback documented and tested where possible

## Anti-patterns
- Click-ops without recording it. Applying from an agent without an approved plan.

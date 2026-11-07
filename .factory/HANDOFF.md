# Handoff — 2026-11-07 — Roadmap v2 + security hardening done

## Task
Template (danfactory) improvements: pull dashboard best practices from lpdan, run the security audit on the template and add best practices. Every feature/behaviour change needs a PRD approved by the user in chat first (docs/policies/prd-approval.md).

## State
- Done, on `main` (d0dae76): Roadmap v2 (global sequence, `> Sequence:` line, Done collapse, Next up, PRD badge, re-sequence rule).
- Done, on `main` (3c302ec): template mode, 80 tests green.
- Done, on `main` (7272d0b, pushed 2026-11-07): security hardening S1–S7 per docs/specs/security-hardening-audit-1.md (approved). 71 tests, `bash scripts/check.sh` green.
- Audit run-1 (quick, source-only, no sandbox): reports in ~/security-audit-skill/danfactory/run-1 (outside repo; gone if container resets). 0 confirmed, 6 needs-validation, 3 rejected.
- Branch: claude/practical-ptolemy-8ttjzi, uncommitted: none.

## Decisions (and why)
- PR previews: option A — Cloudflare dashboard Git integration builds previews, GitHub holds no key; route B template has no PR job with secrets (a preview-capable CF token can usually deploy). ADR docs/decisions/0003-deploy-credential-scoping.md.
- production env: main-only branch rule required, reviewers optional (solo projects).
- Bash reads of .env*/.dev.vars*: block. Deferred items (metrics deploy refusal, merge_settings, session_start marking): out.
- PRD gate: ADR docs/decisions/0002-prd-approval-gate.md.

## Next steps
1. (done) Security hardening is on main.
2. Ask user the owner-only checks: is CLOUDFLARE_API_TOKEN a repo or production-env secret? does `npx wrangler@4 deploy --help` run without prompt in their mode? how repos arrive for adopt?
3. Tech debt TD-001..003 (docs/TECH-DEBT.md): TD-001 cf_scaffold still writes route B — needs a PRD before fixing.

## Watch out
- **danfactory is the TEMPLATE repo only — never build a project here.** Template mode (docs/specs/template-mode.md) now detects this via origin == factory.json template.source_repo; tests: `python3 scripts/metrics.py test` (80 tests).
- New guard blocks `cat .env` etc. and many wrangler forms; `npm run deploy -- --dry-run` is blocked (conservative).
- Parallel worktree devs branched from d0dae76 (old base); merges were clean, but brief agents with the PRD path in main checkout.
- User is not technical on infra choices: explain options plainly and recommend one.

## Pointers
- PRDs: docs/specs/dashboard-roadmap-v2.md, docs/specs/security-hardening-audit-1.md
- Policy: docs/policies/security.md (Best practices section), docs/policies/prd-approval.md
- Learning: docs/operating-model/LEARNINGS.md (2026-11-07 Guards must match their promises)

# Decision tree

> Picks the operating model for a goal. Version 1.0.0. Keep this file short: details live in paths/*.md. Enriched by `retro` from LEARNINGS.md.

## Q1–Q4: what is the main artifact?

```
Q1 Is it throwaway / to learn or prove feasibility (< ~1 week, will be rewritten)?
   └─ yes → prototype-spike   (promote later via retro → re-run choose-path)
Q2 Is the main deliverable a file people open, not code they run?
   ├─ spreadsheet / workbook / financial or data model / CSV outputs → data-spreadsheet
   ├─ document / deck / report / handbook                          → documents-content
   └─ findings / recommendation from sources or data               → research-analysis
Q3 Is it code others import or invoke (package, SDK, CLI)?          → library-cli
Q4 Is it code that runs as a service / app for users?               → software-product
   ├─ is it mainly cloud/infra/config (IaC, pipelines, clusters)?   → infra-ops
   └─ is it glue: scripts, integrations, scheduled jobs, bots?      → automation-script
```

## Q5: rigor level (applies to every path)

| Signal | Level |
|---|---|
| throwaway, only me | L0 |
| internal/personal, low blast radius | L1 |
| others depend on it, lives months+ | L2 |
| money, PII, public internet, regulated, or hard to roll back | L3 |

Take the **highest** level any signal triggers.

## Q6: secondary paths

Add a secondary path for every significant deliverable of another type (e.g. software-product + data-spreadsheet for an app with an Excel export; software-product + documents-content for a product with a user manual). The primary path's gates win on conflicts.

## Q7: going live?

Software that must be reachable by users → deploy via git to Cloudflare using the `ship` skill (default for software-product; optional for automation-script and library-cli docs sites).

## Path summary

| Path | Heavy lifting by | Core practice | Default rigor | File |
|---|---|---|---|---|
| software-product | code-writer, test-runner, reviewer | spec → vertical slices, TDD for logic, CI, git deploy | L2 | paths/software-product.md |
| library-cli | code-writer, test-runner | public API first, semver, examples as tests | L2 | paths/library-cli.md |
| data-spreadsheet | data-builder + xlsx skill | generator scripts, formulas, verification script | L1 | paths/data-spreadsheet.md |
| documents-content | docx/pptx/pdf skills, docs | outline first, review pass, single source | L1 | paths/documents-content.md |
| research-analysis | deep-research, bulk-reader | question → sources ledger → synthesis | L1 | paths/research-analysis.md |
| automation-script | code-writer | idempotent, dry-run flag, logging | L1 | paths/automation-script.md |
| infra-ops | reviewer, security-audit-run | plan/apply split, least privilege | L3 | paths/infra-ops.md |
| prototype-spike | main agent | time-box, kill/promote date | L0 | paths/prototype-spike.md |

## Changelog
- 1.0.0 — initial tree (8 paths, rigor dial, Cloudflare git deploy).

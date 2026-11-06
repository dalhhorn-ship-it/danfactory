# Decision tree

> Picks the operating model for a goal. Version 1.1.0. Keep this file short: details live in paths/*.md. Enriched by `retro` from LEARNINGS.md.

## Q0: new or existing?

```
Q0 Is there already a build (repo, Lovable/Bolt/v0 export, half-finished project)?
   └─ yes → adopt-existing first (scan → index → dashboard → advice), then continue below
            for the path the build will continue on.
```

## Q1–Q7: what is the main artifact? (first match wins)

```
Q1 Throwaway, to learn or prove feasibility (< ~1 week, will be rewritten)? → prototype-spike
Q2 Main deliverable is a spreadsheet / workbook / data or financial model?   → data-spreadsheet
Q3 Main deliverable is a document / deck / report / handbook?                → documents-content
Q4 Main deliverable is findings or a recommendation from sources or data?    → research-analysis
Q5 Main deliverable is infrastructure / cloud config / CI-CD / DNS / IaC?    → infra-ops
Q6 Code others import or invoke (package, SDK, CLI)?                          → library-cli
Q7 Glue: scripts, integrations, scheduled jobs, bots, no UI of its own?      → automation-script
Else: an app, API or service people use                                       → software-product
```

If two match, the one that carries the most risk or effort is primary; the other is secondary (Q9 below).
If nothing fits well, pick the closest, log a `[tree-gap]` learning, and `retro` adds the branch.

## Q8: rigor level (applies to every path)

| Signal | Level |
|---|---|
| throwaway, only me | L0 |
| internal/personal, low blast radius | L1 |
| others depend on it, lives months+ | L2 |
| money, PII, public internet, regulated, or hard to roll back | L3 |

Take the **highest** level any signal triggers.

## Q9: secondary paths

Add a secondary path for every significant deliverable of another type (e.g. software-product + data-spreadsheet for an app with an Excel export; software-product + documents-content for a product with a user manual). The primary path's gates win on conflicts.

## Q10: going live?

Software that must be reachable by users → deploy via git to Cloudflare using the `ship` skill (default for software-product; optional for automation-script and library-cli docs sites).

## Q11: who does the work?

Pick the roster and verification ladder in AGENT-ROUTING.md (docs/operating-model/AGENT-ROUTING.md) for the chosen path(s) and rigor.

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
| adopt-existing | bulk-reader, karen, product-manager | scan → index → dashboard → advise, then continue on another path | as target | paths/adopt-existing.md |

## Changelog
- 1.1.0 — Q0 adopt-existing; flat first-match questions with a fallback (automation/infra no longer nested under apps).
- 1.0.0 — initial tree (8 paths, rigor dial, Cloudflare git deploy).

# Backlog

> Milestones and work items; the dashboard reads this file. Seeded by `choose-path`, ticked off as part of every task's definition of done.

Format: one `## Milestone: <name>` heading per milestone (optional `(target: YYYY-MM-DD)`), then items:
`- [ ]` todo · `- [~]` in progress · `- [x]` done · `- [!]` blocked · `- [-]` dropped. Optional `(S|M|L)` size and `#tags`. Optional item ID right after the checkbox (`ABC-n`, e.g. `- [ ] OBS-1 Title`); commits then carry a `Refs: ABC-n` trailer so the Traceability tab can link them.
Roadmap tab: item order here is the proposed sequence (numbered 1..N across both lanes); an optional `> Sequence: <why>` line under a milestone heading explains it, and a `docs/specs/<slug>.md` link on an item shows its PRD status. Tag technical work `#foundation` (or `#arch`, `#infra`, `#runway`, `#debt`, `#quality`, `#ci`, `#security`, `#process`) to put it in the technical-foundation lane; everything else counts as user value.

## Milestone: M0 — Project set up (target: )
- [ ] Goal agreed (docs/GOAL.md) #process
- [ ] Operating model chosen (docs/OPERATING-MODEL.md) #process
- [ ] Test command and CI green (S) #quality

## Milestone: M1 — Dashboard observability (target: )
> Closed 2026-11-07, retro done (docs/operating-model/LEARNINGS.md).
- [x] OBS-0 Observability design: ADR resolving PRD open questions (docs/specs/dashboard-observability-tabs.md) (S) #arch
- [x] OBS-1 Slice 1: Architecture + Traceability tabs (L) #feature
- [x] OBS-2 Slice 2: Decisions, Gates, Docs health tabs (M) #feature
- [x] OBS-3 Slice 3: Flow, Cost, Hotspots tabs (L) #feature

## Milestone: M2 — Agent evals (target: )
> Sequence: spike first to test the riskiest assumption (headless runs load hooks and are stable enough), then the CLI-usable core, then the dashboard, then the landing page and LLM-judge.
- [ ] EVAL-1 Agent eval harness slice 1: spike, ~10-task suite, deterministic graders, runner, jsonl, baseline, budget cap (docs/specs/agent-eval-harness.md) (L) #foundation
- [ ] EVAL-2 Agent eval harness slice 2: Evals dashboard card/tab (docs/specs/agent-eval-harness.md) (M) #feature
- [ ] EVAL-3 Agent eval harness slice 3: landing page section and LLM-judge graders (docs/specs/agent-eval-harness.md) (M) #feature

## Unplanned
- [x] Template mode: template repo detects itself via origin remote; maintenance session/dashboard/test (docs/specs/template-mode.md) (M) #foundation
- [x] S1 Security best practices section in docs/policies/security.md (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] S2 Deploy credentials: route A default, no secret-bearing PR job, production-environment token, CI least privilege, SHA pins, lockfile (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] S3 Deploy guard hardening + honest wording (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] S4 Secret files: recursive deny, Bash check, gitignore (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] S5 Adopt flow: symlinks, hardened git, list foreign hooks/scripts (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] S6 Supply chain: pinned skills and codegraph, no curl|sh (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] S7 Hygiene: private temp files, dashboard escaping, wait-for-url validation (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] Auto-compact handoff loop: handoff, compact, continue without /clear (docs/specs/auto-compact-handoff-loop.md) (M) #process
- [x] Dashboard roadmap v2: global sequence, Next up, Done collapse, PRD badge (docs/specs/dashboard-roadmap-v2.md) (M) #foundation
- [x] Dashboard delivery backflow: CI pass rate/time card, release cadence, table-form tech debt (docs/specs/dashboard-delivery-backflow.md) (M) #foundation

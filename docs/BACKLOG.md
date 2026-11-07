# Backlog

> Milestones and work items; the dashboard reads this file. Seeded by `choose-path`, ticked off as part of every task's definition of done.

Format: one `## Milestone: <name>` heading per milestone (optional `(target: YYYY-MM-DD)`), then items:
`- [ ]` todo · `- [~]` in progress · `- [x]` done · `- [!]` blocked · `- [-]` dropped. Optional `(S|M|L)` size and `#tags`.
Roadmap tab: item order here is the proposed sequence (numbered 1..N across both lanes); an optional `> Sequence: <why>` line under a milestone heading explains it, and a `docs/specs/<slug>.md` link on an item shows its PRD status. Tag technical work `#foundation` (or `#arch`, `#infra`, `#runway`, `#debt`, `#quality`, `#ci`, `#security`, `#process`) to put it in the technical-foundation lane; everything else counts as user value.

## Milestone: M0 — Project set up (target: )
- [ ] Goal agreed (docs/GOAL.md) #process
- [ ] Operating model chosen (docs/OPERATING-MODEL.md) #process
- [ ] Test command and CI green (S) #quality

## Unplanned
- [x] S1 Security best practices section in docs/policies/security.md (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] S2 Deploy credentials: route A default, no secret-bearing PR job, production-environment token, CI least privilege, SHA pins, lockfile (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] S3 Deploy guard hardening + honest wording (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] S4 Secret files: recursive deny, Bash check, gitignore (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] S5 Adopt flow: symlinks, hardened git, list foreign hooks/scripts (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] S6 Supply chain: pinned skills and codegraph, no curl|sh (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] S7 Hygiene: private temp files, dashboard escaping, wait-for-url validation (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] Dashboard roadmap v2: global sequence, Next up, Done collapse, PRD badge (docs/specs/dashboard-roadmap-v2.md) (M) #foundation

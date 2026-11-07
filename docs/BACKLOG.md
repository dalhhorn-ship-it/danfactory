# Backlog

> Milestones and work items; the dashboard reads this file. Seeded by `choose-path`, ticked off as part of every task's definition of done.

Format: one `## Milestone: <name>` heading per milestone (optional `(target: YYYY-MM-DD)`), then items:
`- [ ]` todo · `- [~]` in progress · `- [x]` done · `- [!]` blocked · `- [-]` dropped. Optional `(S|M|L)` size and `#tags`. Optional item ID right after the checkbox (`ABC-n`, e.g. `- [ ] OBS-1 Title`); commits then carry a `Refs: ABC-n` trailer so the Traceability tab can link them.
Roadmap tab: item order here is the proposed sequence. Tag technical work `#foundation` (or `#arch`, `#infra`, `#runway`, `#debt`, `#quality`, `#ci`, `#security`, `#process`) to put it in the technical-foundation lane; everything else counts as user value.

## Milestone: M0 — Project set up (target: )
- [ ] Goal agreed (docs/GOAL.md) #process
- [ ] Operating model chosen (docs/OPERATING-MODEL.md) #process
- [ ] Test command and CI green (S) #quality

## Milestone: M1 — Dashboard observability (target: )
- [x] OBS-0 Observability design: ADR resolving PRD open questions (docs/specs/dashboard-observability-tabs.md) (S) #arch
- [x] OBS-1 Slice 1: Architecture + Traceability tabs (L) #feature
- [x] OBS-2 Slice 2: Decisions, Gates, Docs health tabs (M) #feature
- [ ] OBS-3 Slice 3: Flow, Cost, Hotspots tabs (L) #feature

## Unplanned

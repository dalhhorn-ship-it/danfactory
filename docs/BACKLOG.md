# Backlog

> Milestones and work items; the dashboard reads this file. Seeded by `choose-path`, ticked off as part of every task's definition of done.

Format: one `## Milestone: <name>` heading per milestone (optional `(target: YYYY-MM-DD)`), then items:
`- [ ]` todo · `- [~]` in progress · `- [x]` done · `- [!]` blocked · `- [-]` dropped. Optional `(S|M|L)` size and `#tags`. Optional item ID right after the checkbox (`ABC-n`, e.g. `- [ ] OBS-1 Title`); commits then carry a `Refs: ABC-n` trailer so the Traceability tab can link them.
Optional markers: `(release: vX.Y)` on an item or milestone heading (planned release, Releases view) and `(after: ABC-n)` on an item (Gantt dependency); the dashboard strips them from titles.
Roadmap tab: item order here is the proposed sequence (numbered 1..N across both lanes); an optional `> Sequence: <why>` line under a milestone heading explains it, and a `docs/specs/<slug>.md` link on an item shows its PRD status. Tag technical work `#foundation` (or `#arch`, `#infra`, `#runway`, `#debt`, `#quality`, `#ci`, `#security`, `#process`) to put it in the technical-foundation lane; everything else counts as user value.

## Milestone: M0 — Project set up (target: )
- [ ] SET-1 Goal agreed (docs/GOAL.md) #process
- [ ] SET-2 Operating model chosen (docs/OPERATING-MODEL.md) #process
- [ ] SET-3 Test command and CI green (S) #quality

## Milestone: M1 — Dashboard observability (target: 2026-11-07)
> Closed 2026-11-07, retro done (docs/operating-model/LEARNINGS.md).
- [x] OBS-0 Observability design: ADR resolving PRD open questions (docs/specs/dashboard-observability-tabs.md) (S) #arch
- [x] OBS-1 Slice 1: Architecture + Traceability tabs (L) #feature
- [x] OBS-2 Slice 2: Decisions, Gates, Docs health tabs (M) #feature
- [x] OBS-3 Slice 3: Flow, Cost, Hotspots tabs (L) #feature

## Milestone: M2 — Agent evals (target: 2026-12-04)
> Sequence: dates (proposed 2026-11-11, S=1/M=3/L=8 working days, WIP=1): EVAL-3 is estimated 2026-11-26..30 after DASH-3 and DASH-4, target 2026-12-04 includes 4 days of buffer for the push-access block. spike first to test the riskiest assumption (headless runs load hooks and are stable enough), then the CLI-usable core, then the dashboard, then the landing page and LLM-judge. Visualizations next (docs/specs/eval-visualizations.md): EVAL-4 first (library, heatmap, coverage map; highest value per effort, and the runner evidence field it adds tells strong proofs from weak ones), EVAL-5 after (flow diagram; weakest case on danfactory itself, droppable). EVAL-3 stays last, blocked on push access to lpdan. Update 2026-11-11: the landing page part shipped in lpdan (main 37f8f25, "Proven by evals" + public Evals tab); LLM-judge graders remain.
- [x] EVAL-1 Agent eval harness slice 1: spike, ~10-task suite, deterministic graders, runner, jsonl, baseline, budget cap (docs/specs/agent-eval-harness.md) (L) #foundation
- [x] EVAL-2 Agent eval harness slice 2: Evals dashboard card/tab (docs/specs/agent-eval-harness.md) (M) #feature
- [x] EVAL-4 Eval visualizations slice A: eval library with proof strength, results heatmap, gate coverage map, eval economics (cost vs pass rate per model) (docs/specs/eval-visualizations.md) (M) #feature
- [x] EVAL-5 Eval visualizations slice B: cumulative flow of backlog items with covered-by-eval band (docs/specs/eval-visualizations.md) (M) #feature
- [ ] EVAL-3 Agent eval harness slice 3: landing page section and LLM-judge graders (docs/specs/agent-eval-harness.md) (M) (release: v0.2) #feature

## Milestone: M3 — Gated autonomy (target: 2026-11-27)
> Sequence: PRD docs/specs/gated-autonomy.md, design ADR 0007. Slice A approved 2026-11-12 (AUTO-1, AUTO-2): gate first because every later step leans on it and it helps supervised work today; acceptance suite second, opened by the risk 1 spike on the textkit fixture. AUTO-3 to AUTO-7 are the plan only: each needs the user's approval before build. The user keeps PRD approval, build starts and pushes to main.
- [x] AUTO-1 Merge gate: one command, one verdict with reason codes, same locally and in CI, Merge gate view on the dashboard (docs/specs/gated-autonomy.md) (M) #foundation
- [x] AUTO-2 Locked acceptance suite: test-writer, admission, protected paths, baseline ratchet, Acceptance coverage view; risk 1 spike first (docs/specs/gated-autonomy.md) (L) (after: AUTO-1) #foundation
- [x] AUTO-3 Issue ledger and finder: issues/ as files, issues.py find/sync, finder agent, Autonomy tab with Issues block (docs/specs/gated-autonomy.md, ADR 0008) (M) (after: AUTO-2) #foundation
- [x] AUTO-4 Fixer loop with rework (cap 3, 5 USD/day), runner refuses self-written trailers (TD-012), automated second reading (TD-014); pilot 2 on a semver library (docs/specs/gated-autonomy.md, ADR 0009) (L) (after: AUTO-3) #foundation
- [x] AUTO-5 Release train: staging re-verified as a batch, promotion report, revert branch + issue on a failed smoke; user promotes and pushes (docs/specs/gated-autonomy.md, ADR 0010) (M) (after: AUTO-4) #foundation
- [x] AUTO-6 Parallel fixers (2 to 4, worktrees, merges serialised) and scheduled runs only with the user's standing go (docs/specs/gated-autonomy.md, ADR 0010) (M) (after: AUTO-5) #foundation
- [x] AUTO-7 Learning from gate rejections: reason-code trends, candidate rules, fixer-loop eval tasks, Autonomy view (docs/specs/gated-autonomy.md, ADR 0010) (M) (after: AUTO-4) #foundation

## Unplanned
- [~] SIZE-2 Autonomy as an optional pack: bootstrap leaves it out, pack.py adds it from a pinned template commit (docs/specs/size-monitoring.md, ADR 0011) (M) (after: SIZE-1) #quality
- [~] SIZE-3 Split runner.py, acceptance.py, gate.py, dashboard.py, guard_bash_policy.py under the size budget, no behaviour change (docs/specs/size-monitoring.md, ADR 0011) (M) (after: SIZE-2) #quality
- [x] SIZE-1 Size monitoring: budgets in factory.json, Size block + alerts on the dashboard, gate warns on oversize files and growth (docs/specs/size-monitoring.md) (M) #quality
- [x] FAST-1 Template checks within the 120 s budget: parallel or split slow set, CI runs everything (docs/specs/fast-checks-and-guard-gaps.md) (M) #quality
- [x] GRD-2 PRD guard covers shell-made writes; self-claimed waivers need the user's words (TD-016) (docs/specs/fast-checks-and-guard-gaps.md) (M) #security
- [~] AUTO-8 Parallel fixers as processes; re-review after rebase (TD-020) (docs/specs/fast-checks-and-guard-gaps.md) (M) (after: FAST-1) #foundation
- [x] TD-PILOT Fix pilot 2 debt: TD-017 bootstrap resets template records, TD-018 issue titles, TD-019 runner ratchets the acceptance baseline (S) #debt
- [x] GRD-1 PRD write guard: hook blocks product-code edits without an in-progress approved item, gate check `prd`, exemption file (docs/specs/prd-write-guard.md) (M) #security
- [x] TPL-1 Template mode: template repo detects itself via origin remote; maintenance session/dashboard/test (docs/specs/template-mode.md) (M) #foundation
- [x] UPS-1 Upstream from lpdan: adopt_scan report sanitiser, pipe-to-shell deploy guard, docs_index.py --related (docs/specs/upstream-from-lpdan-2026-11.md) (S) #security
- [x] SEC-1 Security best practices section in docs/policies/security.md (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] SEC-2 Deploy credentials: route A default, no secret-bearing PR job, production-environment token, CI least privilege, SHA pins, lockfile (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] SEC-3 Deploy guard hardening + honest wording (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] SEC-4 Secret files: recursive deny, Bash check, gitignore (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] SEC-5 Adopt flow: symlinks, hardened git, list foreign hooks/scripts (docs/specs/security-hardening-audit-1.md) (M) #security
- [x] SEC-6 Supply chain: pinned skills and codegraph, no curl|sh (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] SEC-7 Hygiene: private temp files, dashboard escaping, wait-for-url validation (docs/specs/security-hardening-audit-1.md) (S) #security
- [x] PROC-1 Auto-compact handoff loop: handoff, compact, continue without /clear (docs/specs/auto-compact-handoff-loop.md) (M) #process
- [x] DASH-1 Dashboard roadmap v2: global sequence, Next up, Done collapse, PRD badge (docs/specs/dashboard-roadmap-v2.md) (M) #foundation
- [x] DASH-2 Dashboard delivery backflow: CI pass rate/time card, release cadence, table-form tech debt (docs/specs/dashboard-delivery-backflow.md) (M) #foundation
- [x] DASH-3 Dashboard in IBM Carbon look: tokens, type, tiles, tables, tags, tabs, notifications, data-viz palette; offline inline CSS, light and dark (docs/specs/dashboard-carbon-design.md) (M) (release: v0.2) #feature
- [x] DASH-4 Roadmap view options: CSS-only sub-tabs for 6-month timeline, proposed Gantt (estimated from size) and release version view; Sequence stays default; best after DASH-3 (docs/specs/roadmap-view-options.md) (L) (release: v0.2) #feature

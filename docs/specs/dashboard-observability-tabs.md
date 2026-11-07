# PRD: Dashboard observability tabs

> Status: approved · 2026-11-07 · by user in chat (all three slices; open questions delegated to software-architect with product-manager) · Owner: product-manager · Backlog: M1 — Dashboard observability

## Problem
The dashboard answers "where are we?" (Overview, Roadmap) but not "what has been built, why, how well, and at what cost?". Intent, code, decisions, tests, delivery speed and token spend live in separate files, so the user cannot see them together or judge drift between design and build. The user asked for "complete observability on what has been and is being built".

## Goal and success measure
Give the user one read-only, generated view of build history and in-flight work. Success: from the dashboard alone, the user can trace any goal to its code and tests, see where delivery is slow or costly, and spot undocumented or stale areas, with no hand-written content. Live runtime state (deployed vs HEAD, Worker health) is out.

## Users and user stories
- As the product owner, I want goal -> PRD -> item -> commits -> components -> tests -> version so that I can verify what a requirement became.
- As the product owner, I want an architecture diagram and its drift from the code so that I can see what was designed vs built.
- As the product owner, I want flow, cost and gate data so that I can steer effort and trust.

## Scope
Eight new tabs beside Overview and Roadmap, shipped in three slices. Each tab has a meaningful empty state and a line in `--print`; its data goes in `data.json`.

**Slice 1: Architecture + Traceability (shared model)**
- Architecture: read-only, generated, ArchiMate-style diagram in 3 layers. Motivation (GOAL goals, PRD requirements, ADR principles), Application (components, interfaces, data objects derived from code via `scripts/codemap.py`, or codegraph when `integrations.codegraph` is true), Technology (Cloudflare bindings from wrangler config).
- Model source: one repo file (e.g. `architecture.yaml`, ArchiMate element/relation types), mostly generated, with a small hand-curated intent section. No external tool.
- Designed-vs-built drift shown where cheap (modelled element with no code, or code with no element).
- Traceability: goal -> PRD -> backlog item -> commits/PRs -> components -> tests -> version.

**Slice 2: Decisions, Gates, Docs health**
- Decisions: ADR timeline, status, supersedes chains, affected components.
- Gates: per item PRD approved?; tests/coverage per component; last `check.sh` pass; last security audit; dependency freshness.
- Docs health (from `docs/knowledge-graph.json`): orphan docs, docs stale vs the code they describe, components without docs.

**Slice 3: Flow, Cost, Hotspots**
- Flow: lead time PRD-approved -> live, cycle time per item, WIP, deploy frequency, change failure rate (`metrics/history.jsonl`, deploy-watcher push-to-live).
- Cost: tokens per backlog item/feature, per agent/session, handoff trail (`metrics/tokens.jsonl`).
- Hotspots: git churn per component x size/complexity.

## Non-goals
- Interactive or editable diagrams, Archi round trip, or any external modelling tool.
- Live runtime state: deployed vs HEAD, Worker health, uptime.
- Hand-written dashboard content; anything not derived from repo data (except curated architecture intent).
- Changing Overview/Roadmap behaviour, data.json existing fields, or SUMMARY.md semantics (additive only).

## Acceptance criteria
1. Given the repo, when the dashboard is generated, then it contains the new tabs of the delivered slice, plus Overview and Roadmap unchanged, in self-contained HTML (no network), light/dark and mobile-usable.
2. Given a tab has no source data (e.g. this template in phase brainstorm), when generated, then the tab shows what it needs to populate and no error or blank panel.
3. Given a goal with a PRD, item, commit and test, when Traceability renders, then the full chain is visible; given a broken link (PRD with no item, item with no test), then it is flagged.
4. Given a component in code but not in the model (or the reverse), when Architecture renders, then the drift is listed.
5. Given the architecture model is regenerated twice with no repo change, then output is identical (deterministic) and curated intent is preserved.
6. Given an ADR that supersedes another, when Decisions renders, then the chain and affected components appear.
7. Given `docs/knowledge-graph.json`, when Docs health renders, then orphan docs, stale docs and component-without-docs counts match the graph.
8. Given token records that cannot be tied to an item, when Cost renders, then they show as "unattributed" with their share, never silently assigned.
9. Given `metrics/history.jsonl` entries, when Flow renders, then lead time, cycle time, WIP, deploy frequency and change failure rate are computed, or shown as "n/a: needs N events".
10. Given `--print`, then it stays cheap: at most one line per new tab. `data.json` carries every new tab's data. Generation adds no network calls.
11. Given the published Claude artifact, when republished, then it keeps its stable URL and all tabs work there.

## UX / behaviour notes
- Tab bar must stay usable on mobile with 10 tabs (scroll or wrap).
- Empty states say what populates the tab (e.g. "no ADRs yet: first one appears when a decision is recorded").
- Large tables are capped with "top N + count" to protect size and token economy.

## Risks and assumptions
1. Riskiest: Cost attribution. Tokens may not map to items/features reliably. Test first with a spike on existing `metrics/tokens.jsonl`; ship "unattributed" honestly if poor. Hence Cost is last.
2. Architecture derivation quality: codemap/codegraph may give noisy components. Test on a real product repo during Slice 1; keep the curated layer as an override.
3. Data sparsity: Flow and Hotspots are meaningless with few deploys or commits; the empty/"n/a" states carry this.
4. Page size and generation time grow with 10 tabs; cap rows, measure `index.html` size.
5. `dashboard.py` is already 636 lines; adding eight panels risks a monolith (a design matter for the architect).

## Effort and sequencing
Overall L; split into three deliverables, each its own backlog item and approvable independently.
- Slice 1: L (shared model is the foundation; highest value, first).
- Slice 2: M (mostly existing files).
- Slice 3: M-L (depends on metrics quality; Cost carries the risk).
Slice 1 builds the component model that Gates, Hotspots and Decisions reuse.

## Open questions
1. Is "no JS" still required for 10 tabs? CSS-only tabs work today, but an SVG diagram with ten tabs may be heavy without it. Decision for the architect, and a user preference is needed.
2. This template has no product code; the factory itself (agents, skills, hooks, scripts) is what exists. Should the factory be modelled as the first architecture (useful demo, but adds noise for derived products)?
3. Should the three slices be approved together, or Slice 1 only now and the rest later?
4. Is `architecture.yaml` the right name and location, and may it be committed to product repos by default?
5. Are the Flow definitions (PRD approved = start, deploy-watcher push-to-live = end) acceptable, given that PRD approval time may need recording?

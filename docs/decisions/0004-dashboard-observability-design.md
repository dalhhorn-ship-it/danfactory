# 0004 — Dashboard observability: design and open questions

> Status: accepted · Date: 2026-11-07

## Context
docs/specs/dashboard-observability-tabs.md (approved) adds eight tabs in three slices and left five open questions to the architect. Forces: `scripts/dashboard.py` is already 636 lines; the page must stay one self-contained HTML file (no network), light/dark, phone-usable, and publishable as a Claude artifact; template tooling is rigor L1-L2, stdlib Python only, tests in `.factory/tests` run by `scripts/check.sh` in seconds. Full design: docs/specs/dashboard-observability-design.md.

## Options
**Q1 — JS for 10 tabs and an SVG diagram?**
1. Keep CSS-only radio tabs; static inline SVG — zero runtime, works in any artifact viewer; tab CSS selectors grow linearly (generated, not hand-written).
2. Small inline JS for tabs and diagram pan/zoom — nicer interaction; adds a script surface, artifact sandbox risk, and nothing in the PRD needs interactivity (diagrams are read-only by non-goal).

**Q2 — Model the factory itself as the first architecture?**
1. Always model `scripts/`, `.claude/` etc. — good demo; pure noise in product repos.
2. Never — template repo shows only empty states.
3. Generic derivation over configured source roots; template-owned paths (`.claude/`, `.factory/`, `scripts/`, `docs/`, `templates/`) excluded by default, except in the un-bootstrapped template (`project.name` empty), where `scripts/` is the root — demo for free, no noise downstream.

**Q3 — Approve slices together or one by one?**
Already answered by the user: all three approved (PRD status line). Delivery and verification stay one slice at a time, each its own backlog item.

**Q4 — `architecture.yaml` name, location, format, committed?**
1. `architecture.yaml` + a hand-written YAML-subset parser — friendly to edit; a parser to own and test, subtle bugs, still no comments-preserving round trip.
2. Add PyYAML — real YAML; breaks the stdlib-only rule for one file.
3. `docs/architecture.json`: `{"schema", "curated", "generated"}` written with `sort_keys`, `indent=1`, no timestamps — zero parser code, deterministic, same pattern as `docs/knowledge-graph.json`; JSON is a little less pleasant to hand-edit, but the curated part is small.

**Q5 — Flow definitions (Slice 3).**
1. Start = PRD approval (date already recorded in the PRD status line `approved · YYYY-MM-DD`); end = first successful production deploy (`metrics/history.jsonl` deploy row) whose commit range contains a commit referencing the item. Cycle time = first referencing commit to the commit that ticks the item `[x]`.
2. Start = item moved to `[~]` — needs backlog history parsing from git; noisier.

## Decision
- **Q1:** Option 1. No JS. Tab inputs, labels and the `:checked` selectors are generated from one `TABS` list; the tab bar scrolls horizontally on phones (`overflow-x:auto; white-space:nowrap`). The diagram is static SVG styled with the existing CSS variables, wrapped in `.scroll`. Revisit only if the user asks for interaction.
- **Q2:** Option 3. PM confirmed 2026-11-07: gives the template a real demo and keeps product repos clean; matches PRD open question 2.
- **Q3:** Resolved by the user: all approved; ship Slice 1, then 2, then 3.
- **Q4:** Option 3: `docs/architecture.json`, committed by default (it is small, reviewable in PRs, and the curated intent must survive clones). Written by `python3 scripts/archmodel.py --write` (run by `docs-sync`); the dashboard always derives the generated part fresh in memory and flags "model file stale" when the committed copy differs. Not gated in `check.sh`, because the optional codegraph enrichment is machine-dependent.
- **Q5:** Option 1, using the PRD status-line date (no new recording needed). Shown as "n/a: needs N events" when sparse. PM confirmed 2026-11-07: matches AC 9 and the PRD's "PRD-approved -> live" wording; no new recording needed.
- **Traceability keys (needed by all slices):** backlog items get an optional ID token `XXX-n` (like `TD-n`, e.g. `OBS-1`); commits reference it with a `Refs: OBS-1` trailer (or anywhere in the message). Items without an ID fall back to the PRD slug (`Refs: dashboard-observability-tabs`). Item → PRD by a `docs/specs/<slug>.md` mention in the item or by the PRD's `Backlog: <milestone>` field.

## Consequences
- Easier: no new deps, no parser, no JS; each tab is an independent module (`scripts/obs/`), so `dashboard.py` grows only by wiring.
- Harder: hand-editing JSON (no comments); traceability is only as good as `Refs:` discipline, so missing keys are shown as broken links rather than guessed.
- PM confirmed 2026-11-07 (traceability keys): ID and `Refs:` are optional, so the cost to agents is one trailer line per commit; the slug fallback avoids forcing IDs onto existing items. Conditions: never block commits or `check.sh` on a missing `Refs:` (show a count only), and do not retro-edit existing backlog or history. No change to PRD scope or acceptance criteria; no user re-approval needed.
- Measure at retro: `index.html` size (target < 400 KB with all tabs), dashboard build time (target < 2 s on this repo), share of commits with a `Refs:` key, drift count trend.

# Handoff — 2026-11-07 06:35 — Dashboard observability: Slice 3 next

## Task
User wants "complete observability on what has and is being built" in the dashboard: 8 new tabs, viewed via the Claude artifact (no interactive editing). All three slices approved by the user in chat.

## State
- Done: PRD approved (docs/specs/dashboard-observability-tabs.md); ADR 0003 + design (2083597); Slice 1 OBS-1 Architecture + Traceability (3786223..dcf6206); Slice 2 OBS-2 Decisions, Gates, Docs health (65f993c, f279257, 4b5ad33). Dashboard republished (v2) to https://claude.ai/artifact/26kZii7ybp45ynQBB47X8D (URL in factory.json integrations.dashboard_url).
- In progress: nothing. Next: OBS-3 Slice 3 (Flow, Cost, Hotspots).
- Branch: claude/great-pasteur-br9y8v, uncommitted: none. No PR (user hasn't asked).

## Decisions (and why)
- CSS-only tabs, no JS; static SVG diagram — PRD rules out interactivity (ADR 0003).
- Model in docs/architecture.json (stdlib has no YAML); curated + generated sections, deterministic.
- Factory scripts/ shown as demo model only while project.name is empty (PM confirmed).
- Item IDs OBS-n + `Refs: OBS-n` commit trailer; missing refs counted, never block (PM confirmed).
- Flow: lead time = PRD approval date → first prod deploy with a referencing commit; cycle = first referencing commit → ticking commit.
- Gate records: `python3 scripts/metrics.py record check|security-audit` → metrics/records.jsonl.

## Next steps
1. Launch `developer` (background) for OBS-3 per design doc + ACs 8, 9, 10; run spike S3 first (can tokens in metrics/tokens.jsonl be tied to items? else show "unattributed").
2. Verify (check.sh, screenshots), republish artifact with same file_path, tick OBS-3.
3. Consider fixing TD-003 (check.sh dirties records.jsonl every run → stop hook nags); then `retro` at M1 close.

## Watch out
- scripts/dashboard.py > 350 lines: targeted reads only. Tab modules in scripts/obs/ (collect/render/line).
- `metrics.py test` is a no-op here (commands.test empty); check.sh runs the unittest suite.
- check.sh fails if docs index stale: run `python3 scripts/docs_index.py` after doc edits.
- Pipe-to-tail hides check.sh failure in `&&` chains — check the output.

## Pointers
- docs/decisions/0003-dashboard-observability-design.md, docs/specs/dashboard-observability-design.md
- docs/BACKLOG.md (M1), docs/TECH-DEBT.md (TD-001..004)

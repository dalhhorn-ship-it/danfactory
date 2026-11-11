# Handoff — 2026-11-11 — Evals done + baselines; Carbon awaiting look OK; DASH-4 next

## Task
User (PM, portfolio): behavioural evals in danfactory, shown on dashboard + landing page (lpdan); dashboard in IBM Carbon; optional roadmap views (6-month, proposed Gantt, releases). Last: write an MD handover file for the lpdan repo listing what to pull from the template (landing page incl. dashboard).

## State
- Done + pushed on ccr-13a7396b-z4lqjz: EVAL-1,2,4,5 (evals harness, Evals tab, library/heatmap/coverage/economics, cumulative flow); backlog IDs + covers (6250934); Carbon look DASH-3 (3e4ae0d, `[~]` until user OKs the look); PM dates + v0.2 markers, EVAL-3 `[!]` (76eb0b0); baselines haiku 30/30 $0.46, sonnet 30/30 $2.43, sonnet saved as metrics/evals-baseline.json (3fb47b6). Dashboard artifact republished v8 (factory.json dashboard_url).
- PRDs approved (recommended answers): docs/specs/agent-eval-harness.md, eval-visualizations.md (+eval economics), dashboard-carbon-design.md, roadmap-view-options.md.
- Scratch clone /tmp/.../scratchpad/df is STALE; work in /home/user/danfactory now.

## Next steps
1. Ask user to OK the Carbon look (screenshots in scratchpad/shots/carbon/); then tick DASH-3. Known: phone Roadmap tab has a big empty gap under the milestone header row (lane grid) — fix in DASH-4. Carbon hex values partly from memory (border-subtle, g100 notification bg) — flagged.
2. Build DASH-4 (developer agent): Sequence|6-month|Gantt|Releases sub-tabs, Carbon tokens, blocked items after unblocked in Gantt.
3. Ask user OK to create git tag v0.1.0 (PM proposal) — not yet asked/answered... asked, no answer.
4. Then lpdan handover MD (user asked; put in danfactory e.g. docs/handover/lpdan-update.md and send via SendUserFile). lpdan push is DENIED (add_repo push refused by auto-mode classifier); lpdan has its own PRD gate; its GOAL: claims must be true to danfactory repo. Read-only clone: /home/user/dalhhorn-ship-it/lpdan (public/index.html, public/dashboard/index.html).
5. Older: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50 on Default env; ask before deleting old branches; TD-001..011.

## Watch out
- TEMPLATE repo: never build a project here. Delete metrics/history.jsonl before commits.
- Don't edit the working tree while an eval run is going (runs copy it).
- Prompt injection rule doesn't exist in rules.json; hook-block (exit 2) only synthetically tested; deny rule proved strong.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/policies/evals.md, docs/decisions/0006-agent-eval-harness.md, scripts/obs/theme.py, scripts/obs/evals_*.py, evals/rules.json

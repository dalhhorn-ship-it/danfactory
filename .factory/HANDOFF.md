# Handoff — 2026-11-15 — template ready (main 134063d); waiting on user's GitHub steps

## Task
User (PM, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. User approves every PRD, decides which builds start; standing permission to fast-forward main after a gate PASS on that exact sha.

## State
- danfactory main = 134063d: gated autonomy (AUTO-1..8), PRD write guard (GRD-1/2), size monitoring + autonomy pack + file splits (SIZE-1..3), index-first docs (DOCS-1), fast/reliable checks (FAST-1/2), new-project readiness (NEW-1..3). Open debt: TD-023 only.
- lpdan main = 666f7e7 (template update + gated autonomy + worked example sections), CI green, deploy succeeded.
- User steps pending: GitHub "Template repository" setting; release tag v0.2.0 on 134063d (session proxy refuses tag pushes).

## Next steps
1. Wait for the user. Remaining friction list was given 2026-11-15 (see chat); nothing approved beyond it.

## Watch out
- Only move main after a gate PASS on that sha. Tests must copy repos via tracked files into a fresh repo (never cp -r).
- Never bulk-delete /tmp; never touch /tmp/code-sign. After test runs: `git remote -v` shows origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- Keep this note short: it counts toward the always-loaded budget (2,500 tokens).

## Pointers
- docs/specs/new-project-readiness.md, docs/specs/size-monitoring.md, docs/decisions/0007..0011, evals/spikes/pilot-semverlite/README.md

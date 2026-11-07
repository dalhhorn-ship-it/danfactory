# 0005 — Automatic handoff, compact, continue loop

> Status: accepted · Date: 2026-11-07 · PRD: docs/specs/auto-compact-handoff-loop.md

## Context
Short contexts with a handoff note keep accuracy and cut cost. The old loop needed a human to type `/clear` after every handoff. Claude Code documents that no hook, skill or model can run `/clear` or `/compact`. It also documents that PreCompact (matcher `manual|auto`) stdout on exit 0 becomes instructions for the compaction summary (max 10,000 chars), that SessionStart fires with source `compact` and its stdout is added to context, and that auto-compaction can start earlier via `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` or `CLAUDE_CODE_AUTO_COMPACT_WINDOW`.

## Options
1. Keep asking the user to `/clear`: simple, but a human must be present at every boundary.
2. Let auto-compaction be the reset and steer it with hooks: no human step; the summary is lossy, so the committed handoff note stays the source of truth.

## Decision
Option 2 (founder approved 2026-11-07).
- `context_watch.py`: at the budget, refresh and commit the note at the next boundary, then keep working. Never asks for `/clear`. Re-arms once the context drops under the budget. State stays in the private per-user dir.
- `pre_compact.py`: prints the summary instructions and points at `.factory/HANDOFF.md`; flags a missing note or one older than the last commit; keeps writing the snapshot block (never through a symlink); never blocks.
- `session_start.py` with matcher `startup|resume|clear|compact`: injects the note (also in template mode); after a compaction adds "Context was compacted automatically; continue the task from this note; user gates still apply."
- `handoff` skill: commit, continue. `/clear` stays optional.
- Operator step, approved by the founder 2026-11-07: set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` on the cloud environment, so compaction starts at about half the window, above the 120k handoff budget. The operator sets it; agents never do (docs/policies/token-economy.md). Use this variable or `CLAUDE_CODE_AUTO_COMPACT_WINDOW=250000`, not both.
- Measure compactions per session and weighted tokens in metrics/REPORT.md after a few long sessions before calling the benefit proven (founder decision 4).

## Consequences
Sessions can run long tasks without a human `/clear`. User gates are unchanged and restated after each compaction. Until the operator sets the env var, compaction starts near the full window, so the loop works but contexts stay longer than the 120k budget. The summary is lossy; the committed note carries the work.

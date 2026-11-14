# Policy: token economy

> Spend tokens on decisions, not on moving bytes. Adapted from Spotify's `shunt` plugin (delegate I/O-heavy work to a cheaper worker) using native Claude Code subagents.

## Rules
1. **Index first.** Read `docs/INDEX.md`, then targeted reads (`Read` with offset/limit) at the `file:line` it lists; for docs over `budgets.size.doc_tokens_sections` (1500 tokens) the index lists sections with start lines, and `python3 scripts/docs_index.py --related <doc>` shows linked docs. Every agent file says so (`Finding things`).
2. **No whole large files in the main context.** Files over `budgets.large_read_lines` (350) are blocked by `.claude/hooks/guard_large_read.py` unless offset/limit is given. Escape hatch: `touch .claude/.allow-large-read` allows the next large read once (say why). The guard also catches `tail -n +K`, big `head`/`tail` counts and big `sed -n` ranges.
3. **Delegate bulk reading** to `bulk-reader` (Haiku): big files, 3+ files, long diffs, logs, API specs. Ask a precise question; get `file:line` bullets back.
4. **Delegate boilerplate** to `code-writer` with a reference file. Run tests directly via `metrics.py test` (one line when green); **delegate failing or noisy runs** to `test-runner`.
5. **Code navigation**: codegraph (`codegraph explore "<question>"`, `codegraph affected`) when enabled — one call instead of many grep/read rounds.
6. **One task per session.** Fresh session (or /clear) between unrelated tasks; long sessions re-pay context every turn.
7. **Keep CLAUDE.md small and stable** — it is paid on every turn and is the prompt-cache prefix.
8. **On-demand skills** (security-audit, cloudflare-deploy) are installed only when needed; their big reference files are read selectively.

## Short contexts and handoff notes
Long contexts cost more per token and rarely buy accuracy: NVIDIA's "You don't need long context" kept agents within ~2 points of full history by compacting often. In one setting, compacting after every action kept Claude Opus 4.5 at 70.2% on SWE-bench Verified versus 70.0% with full history. How the factory applies it:
1. **Handoff note** (`handoff` skill → `.factory/HANDOFF.md`, 40 lines or fewer): task, state, decisions, next steps, gotchas, pointers. Written at logical boundaries, never mid-debug, and committed.
2. **Nudge, don't nag:** `context_watch.py` (UserPromptSubmit) reads the live context size and reminds once per 50k band above `budgets.context_handoff_tokens` (120k): refresh the note at the next boundary, commit it, keep working. It never asks the user to `/clear`. When the context drops back under the budget (after a compaction), it re-arms.
3. **Automatic reset (handoff, compact, continue):** no hook, skill or model can run `/clear` or `/compact`, so the reset is Claude Code's auto-compaction. `pre_compact.py` (PreCompact, `manual|auto`) prints the summary instructions (keep goal and open questions, decisions and reasons, files changed and commit shas, current step and next steps, failed approaches; drop file contents, tool output, logs), points at the note as the source of truth, and says so when the note is missing or older than the last commit, so the summary records the current step itself. It also writes a snapshot block (branch, uncommitted files, in-progress items, last commits) into the note. It never blocks.
4. **Continue:** `session_start.py` (SessionStart, `startup|resume|clear|compact`) injects the note. After a compaction it adds: "Context was compacted automatically; continue the task from this note; user gates still apply." `/clear` stays an optional manual way to restart from the note.
5. **Search, don't load:** subagents work in fresh contexts and return short answers; files are grepped and read in slices (rules 1–5 above).
6. **Measured:** compactions per session are recorded in metrics/tokens.jsonl.

### Operator step: start auto-compaction earlier (needs approval)
By default auto-compaction starts close to the model's full context window, far above the 120k handoff budget. To make the loop run at a short context, the operator sets one of these Claude Code environment variables on the cloud environment (or in the shell for local runs). It changes how every session in that environment behaves, so it needs the user's (founder's) approval first; agents never set it themselves.
- `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (1 to 100): compact at this percentage of the context window.
- `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (tokens): the context window size used for the auto-compaction threshold.

Pick a value so compaction starts some way above `budgets.context_handoff_tokens`, so the agent has room to reach a boundary and refresh the note first. Chosen and approved 2026-11-07: `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` on the cloud environment, set by the operator (ADR 0005; use one variable, not both).

## What stays in the main agent
Debugging, edits that need exact text, architecture and trade-off decisions, anything the user is discussing live.

## Measured
Tokens per session, including subagents, land in `metrics/tokens.jsonl` (SessionEnd hook). Budgets use **weighted tokens** (input-equivalents: output ×5, cache write ×1.25, cache read ×0.1), because raw totals are dominated by cheap cache reads. `metrics.py report` flags sessions over `budgets.session_weighted_tokens_warn` and low cache-hit rates.

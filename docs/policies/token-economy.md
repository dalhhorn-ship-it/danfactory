# Policy: token economy

> Spend tokens on decisions, not on moving bytes. Adapted from Spotify's `shunt` plugin (delegate I/O-heavy work to a cheaper worker) using native Claude Code subagents.

## Rules
1. **Index first.** Read `docs/INDEX.md`, then targeted reads (`Read` with offset/limit) at the `file:line` it lists.
2. **No whole large files in the main context.** Files over `budgets.large_read_lines` (350) are blocked by `.claude/hooks/guard_large_read.py` unless offset/limit is given. Escape hatch: `touch .claude/.allow-large-read` allows the next large read once (say why). The guard also catches `tail -n +K`, big `head`/`tail` counts and big `sed -n` ranges.
3. **Delegate bulk reading** to `bulk-reader` (Haiku): big files, 3+ files, long diffs, logs, API specs. Ask a precise question; get `file:line` bullets back.
4. **Delegate boilerplate** to `code-writer` with a reference file. Run tests directly via `metrics.py test` (one line when green); **delegate failing or noisy runs** to `test-runner`.
5. **Code navigation**: codegraph (`codegraph explore "<question>"`, `codegraph affected`) when enabled — one call instead of many grep/read rounds.
6. **One task per session.** Fresh session (or /clear) between unrelated tasks; long sessions re-pay context every turn.
7. **Keep CLAUDE.md small and stable** — it is paid on every turn and is the prompt-cache prefix.
8. **On-demand skills** (security-audit, cloudflare-deploy) are installed only when needed; their big reference files are read selectively.

## What stays in the main agent
Debugging, edits that need exact text, architecture and trade-off decisions, anything the user is discussing live.

## Measured
Tokens per session, including subagents, land in `metrics/tokens.jsonl` (SessionEnd hook). Budgets use **weighted tokens** (input-equivalents: output ×5, cache write ×1.25, cache read ×0.1), because raw totals are dominated by cheap cache reads. `metrics.py report` flags sessions over `budgets.session_weighted_tokens_warn` and low cache-hit rates.

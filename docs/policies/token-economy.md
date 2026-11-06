# Policy: token economy

> Spend tokens on decisions, not on moving bytes. Adapted from Spotify's `shunt` plugin (delegate I/O-heavy work to a cheaper worker) using native Claude Code subagents.

## Rules
1. **Index first.** Read `docs/INDEX.md`, then targeted reads (`Read` with offset/limit) at the `file:line` it lists.
2. **No whole large files in the main context.** Files over `budgets.large_read_lines` (350) are blocked by `.claude/hooks/guard_large_read.py` unless offset/limit is given. Escape hatch: `FACTORY_ALLOW_LARGE_READ=1` (say why).
3. **Delegate bulk reading** to `bulk-reader` (Haiku): big files, 3+ files, long diffs, logs, API specs. Ask a precise question; get `file:line` bullets back.
4. **Delegate boilerplate** to `code-writer` with a reference file; **delegate test/build runs** to `test-runner`.
5. **Code navigation**: codegraph (`codegraph explore "<question>"`, `codegraph affected`) when enabled — one call instead of many grep/read rounds.
6. **One task per session.** Fresh session (or /clear) between unrelated tasks; long sessions re-pay context every turn.
7. **Keep CLAUDE.md small and stable** — it is paid on every turn and is the prompt-cache prefix.
8. **On-demand skills** (security-audit, cloudflare-deploy) are installed only when needed; their big reference files are read selectively.

## What stays in the main agent
Debugging, edits that need exact text, architecture and trade-off decisions, anything the user is discussing live.

## Measured
Tokens per session land in `metrics/tokens.jsonl` (SessionEnd hook); `metrics.py report` flags sessions over `budgets.session_tokens_warn` and low cache-hit rates.

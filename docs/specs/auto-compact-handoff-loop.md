# PRD: Automatic handoff, compact, continue loop (no /clear needed)

> Status: approved · 2026-11-07 · by user in chat · Owner: product-manager · Backlog: Unplanned → "Auto-compact handoff loop" · Swimlane: technical foundation (template tooling) · Retroactive: built on branch `claude/auto-compact-handoff-loop` (forked 41 commits before main) without a PRD; this spec describes that work so it can be approved before porting.

## Problem
Today the handoff loop stalls until a human types `/clear`. The `handoff` skill and `context_watch.py` tell the agent to write a note and "ask the user to /clear". Nothing can type it for them: no hook, skill or model can run `/clear` or `/compact`. So long tasks need a person present at every handoff, and unattended or cloud sessions simply carry on in a long, expensive context.

## Goal and success measure
Traceability: no GOAL.md outcome applies (project is in phase brainstorm; this is template tooling). It traces to docs/policies/token-economy.md ("short contexts and handoff notes") and to the template purpose that new projects inherit a working token-saving loop. Success: a long session goes handoff, compaction, continue with no human keystroke, user approval gates are unchanged, and the committed note is the source of truth. Measure: compactions and weighted tokens per session in metrics/REPORT.md after a few long runs.

## Users and user stories
- As a founder running long or unattended sessions, I want the agent to save its state and carry on without me typing `/clear`.
- As an agent after a compaction, I want the note reloaded with a clear "continue from here" line so I resume the right step.
- As a founder, I want approval gates (PRD gate, deploy gate) to still apply after a compaction.

## Scope
Behaviour as built on the branch. Auto-compaction is the reset; the hooks steer it.
1. **context_watch.py (S).** Above `budgets.context_handoff_tokens`, one reminder per 50k band says: at the next boundary (never mid-debug or with half-applied changes) refresh `.factory/HANDOFF.md` with the `handoff` skill, commit it, keep working, and do not ask the user to `/clear`. When the context falls back under the budget (after a compaction) the band state is cleared so the next long stretch is nudged again.
2. **pre_compact.py (M).** Matcher `manual|auto`. Prints instructions for the compaction summary (max 10,000 chars): what to keep (goal and open questions, decisions and reasons, files changed and commit shas, current step and next steps, failed approaches, pending user gates), what to drop (file contents, tool output, logs), and that the note is the source of truth. Says so if the note is missing/empty (only the placeholder or snapshot) or older than the last commit (a note committed in HEAD counts as fresh). Still writes the snapshot block (replacing the previous one) but preserves the note's mtime so a snapshot never makes a stale note look fresh. Never blocks: all errors swallowed, exit 0, git calls time-limited.
3. **session_start.py + settings (S).** Matcher `startup|resume|clear|compact`. Injects the note (60-line cap). When source is `compact`, adds: "Context was compacted automatically; continue the task from this note; user gates still apply." If no note exists, a compact source still gets that line, pointing at the compaction summary.
4. **handoff skill (S).** Commit the note, then keep working; do not ask for `/clear`. `/clear` and `/compact` remain optional user actions.
5. **Docs and tests (S).** CLAUDE.md "Short contexts", token-economy policy (new "operator step" section), AGENT-ROUTING row, README row, LEARNINGS entry, new ADR, tests in `.factory/tests/test_template.py`.

## Non-goals
- Agents never set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` or `CLAUDE_CODE_AUTO_COMPACT_WINDOW` themselves; it is an operator step that needs the user's approval.
- No attempt to run `/clear` or `/compact` from a hook, skill or model (not possible).
- No change to approval gates, deploy flow or the handoff note format (still 40 lines or fewer).
- No new dependencies; no replacement of the committed note by the compaction summary.

## Acceptance criteria
1. Given context above budget, when `context_watch.py` fires, then output names `.factory/HANDOFF.md`, says "keep working" and "never mid-debug", says "Do not ask the user to /clear", and never asks for `/clear`.
2. Given a reminder was shown, when the context later drops under the budget, then the state file is removed and the next long stretch is nudged again.
3. Given any trigger (`manual` or `auto`), when `pre_compact.py` runs, then it exits 0 and prints the keep/drop instructions and "Source of truth: .factory/HANDOFF.md", in 10,000 chars or fewer.
4. Given no note, an empty note, or a snapshot-only note, when it runs (twice), then output contains "missing or empty" both times.
5. Given a note older than the last commit and not committed in HEAD, when it runs, then output contains "older than the last commit" and the note's mtime is unchanged; after the note is committed, the warning is gone.
6. Given a non-git directory, no factory.json and non-JSON input, when it runs, then exit code is 0 and instructions still print.
7. Given two runs, when the note is read, then exactly one auto-snapshot block exists and the agent-written text is intact.
8. Given source `compact` and a note, when `session_start.py` runs, then output has the "Context was compacted automatically; continue the task from this note; user gates still apply." line plus the note; given source `startup`, `resume` or `clear`, the line is absent.
9. Given source `compact` and no note, when it runs, then the compacted line appears and mentions "user gates still apply".
10. Given `.claude/settings.json`, when parsed, then the SessionStart matcher covers `startup`, `resume`, `clear`, `compact` and PreCompact matcher is exactly `manual|auto`.
11. Given the handoff skill, CLAUDE.md and token-economy policy, when read, then none tells the agent to ask the user to `/clear`, and the policy marks the env var as an operator step needing approval.
12. `python3 scripts/metrics.py test` and `bash scripts/check.sh` pass on the ported branch.

## UX / behaviour notes
- Without the env var, auto-compaction starts near the full window, so the loop works but contexts stay longer than the 120k budget (cost, not correctness).
- The summary is lossy; the committed note is what carries the work. A stale or missing note is flagged, not fatal.
- Template mode: the note reload also applies in template-maintenance sessions (see port notes).

## Risks and assumptions
- Riskiest: Claude Code behaves as documented (PreCompact stdout steers the summary; SessionStart fires with source `compact`). Test cheaply by running one long throwaway session and checking the reload line appears.
- The agent may not reach a boundary before compaction hits. Mitigation: pre_compact flags a stale note and tells the summary to record the current step.
- A lossy summary could drop an approval gate. Mitigation: the reload line restates "user gates still apply".
- Unmeasured benefit (design choice); LEARNINGS entry plans a check after a few long runs.

## Effort and sequencing
Overall M (already built; port cost S to M). Port order: hooks and settings, skill, tests, docs, ADR. Cut order if pressed: README/AGENT-ROUTING rows, then LEARNINGS wording.

Port notes (main now has 41 more commits):
- **ADR number:** branch ADR `0002-auto-compact-handoff-loop.md` collides with `docs/decisions/0002-prd-approval-gate.md`. Main already has 0003 (deploy credential scoping) and 0004 (dashboard observability), so the next free number is **0005**, not 0004. Rename file and title, fix references (LEARNINGS "ADR 0002", token-economy). Status stays "accepted" only after the user approves this PRD.
- **context_watch.py conflict:** main replaced the state path with a private per-user 0700 directory (`state_dir()`, `safe_sid()`, `O_NOFOLLOW`, state file `ctx-<sid>`, silent if no safe dir). The branch still uses `tempfile.gettempdir()/danfactory-ctx-<sid>` via a new `state_path()`. Keep main's hardened state handling; apply only the branch's behaviour on top: the new MESSAGE text, and on `size < limit` remove the state file (resolve it through `state_dir()`, no symlink following, ignore errors, and do nothing if there is no safe dir). Update the branch's tests, which look for the old `danfactory-ctx-<sid>` path, to use the new location.
- **session_start.py:** main adds a template-mode branch that already calls `handoff_note(source)`; the branch's `handoff_note` change therefore also works there. Verify the compact line appears in both modes and add a template-mode test.
- **pre_compact.py:** unchanged on main, so the branch version applies cleanly. It reads and writes only `.factory/HANDOFF.md` and runs read-only git commands; no conflict with the security guards.
- **Security hardening:** the new operator section must not imply agents can set env vars; consistent with the "guards are advisory, credentials enforce" principle in security.md. State files stay in the private dir. Re-run the hook tests that main added for the guards.
- settings.json: re-apply the two `matcher` lines against main's hook list (main has other hook entries); do not overwrite them.

## Decisions (user, 2026-11-07)
1. Start compaction earlier: yes, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` on the cloud environment (operator step; record in the ADR).
2. Agent continues on its own after compaction, still stopping at approval gates: yes.
3. ADR number 0005: yes.
4. Measure compactions and token cost after a few long sessions before calling it done: yes.

## Open questions (answered above)
1. Do you want compaction to start earlier than the default? Without it, the agent keeps working in a very long conversation (slower, costlier) until the system compacts on its own near the limit. Setting it is a one-time change on the cloud environment and affects every session there. Recommendation: yes, set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`, which compacts at about half the window. That leaves room above the 120k handoff budget for the agent to save its note first. If you prefer to think in size rather than percent, the equivalent is `CLAUDE_CODE_AUTO_COMPACT_WINDOW=250000`. Use one of them, not both. Approve or choose a different number, and I record it in the decision log.
2. Is it fine that, after an automatic compaction, the agent carries on by itself from the saved note (it will still stop and ask you wherever it needed your approval before)?
3. Should I approve-gate the ADR number change (0005 instead of 0004) as described, or do you want the ADRs renumbered differently?
4. Do you want a check after a few long sessions (compactions and token cost per session) to confirm this actually saves money, before we call it done?

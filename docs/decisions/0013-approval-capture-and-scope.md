# 0013 — Approvals the agent cannot write, and PRD scope

> Status: proposed · Date: 2026-11-14 · PRD: docs/specs/trust-hardening.md (TRUST-2, criteria 9-15, risk 1, Decisions 1-4) · Evidence: evals/spikes/approval-capture/README.md

## Context
Today "approved" is the PRD's `> Status:` line, which any agent can write (`_prd.py`, `prd_status`). One approved item unlocks every path, factory core included. The spike showed two ways a hook can see the user's own choice: the answer to an AskUserQuestion dialog (PostToolUse; the harness strips any answer the agent supplies), and a typed prompt whose transcript row says `turnOrigin: human`, `promptSource: sdk`. The agent and the record share one machine, so this design stops drift and cheap forgery and makes the rest visible. It does not make forgery impossible.

## Options
1. **Keep the status line, add stricter rules.** No new parts. The agent still writes "approved". Rejected.
2. **Approval on GitHub (PR review).** Binding, but the session acts as the owner, who cannot review their own PR, and the user ruled out GitHub steps (Decision 1). Rejected.
3. **Hook-written record from a fixed dialog or an exact typed phrase.** Both proven by the spike. Cost: one new hook, one record file, a hash rule. **Chosen.**

## Decision
**Record.** `.factory/approvals.jsonl`, tracked in git, append only, one JSON line per event: `v` (1), `kind` (`prd`, `build-start`, `release`), `slug`, `item` (backlog id, build-start only), `hash` (12 hex), `staging_sha` (release only), `ts` (UTC), `session_id`, `prompt_id` or `tool_use_id`, `via` (`button`, `phrase`, `legacy`). Only the hook writes it.

**What the hash covers.** sha256 of the PRD's `## Scope` and `## Acceptance criteria` sections, which include the `Touches:` line. Before hashing: drop markdown emphasis and backticks, lower-case, collapse all whitespace. Edits elsewhere (problem, notes, open questions, status line) never void an approval; nor do re-wrapping or formatting. A changed word in scope or criteria does, and costs one tap to re-approve. The dialog shows the first 8 hex characters.

**Three user actions.** Each has a fixed dialog. The hook records only an exact match: header, question text and option set; the tapped option must be the first one.

| Action | Header | Question | Options | Typed phrase |
|---|---|---|---|---|
| Approve PRD | `Approve PRD` | `Approve PRD <slug> (scope <h8>)?` | Approve / Change / Drop | `approve <slug>` |
| Start build | `Start build` | `Start build <ITEM-ID> (PRD <slug>, scope <h8>)?` | Start / Not now | `start <ITEM-ID>` |
| Release | `Release` | `Release staging <sha7> to main (<n> commits)?` | Release / Not now | `release` |

Option for the user to accept: the approve dialog gets a fourth choice, `Approve and start <ITEM-ID>`, which writes both records from one tap. "Approve" alone stays, so the user still decides each build start.

**Button capture.** New hook `record_approval.py`, PostToolUse on `AskUserQuestion`. It records when: the event has no `agent_id` (not a subagent); text and options match the fixed form; `<h8>` equals the hash of the file on disk now; the transcript holds the dialog call (`tool_use`) with this `tool_use_id` and the same fixed text, and no tool result for it that says otherwise. Measured in the spike: when PostToolUse fires, the call is already in the transcript and its result is not. A hook run by hand afterwards therefore finds the real result and must match it. Otherwise it records nothing and logs why to `metrics/guard.local.jsonl`.

**Typed capture.** Same hook, UserPromptSubmit. The whole prompt, trimmed, must be one phrase; anything more is ordinary chat. It records only when the transcript row with this `prompt_id` has `turnOrigin: human` and `promptSource: sdk` and holds exactly the phrase. Measured in the spike: that row is not in the transcript yet when UserPromptSubmit fires, but it is there for the rest of the turn, and every later hook event carries the same `prompt_id`. So capture takes two steps. UserPromptSubmit notes a pending candidate (`prompt_id`, phrase) in `.factory/approvals.pending`, which grants nothing and is closed to agents like the record. The first later hook event of that turn (PreToolUse, PostToolUse or Stop; a cheap check that runs only while a candidate is pending) reads the row, records on a match and clears the candidate. No match within the turn: no record, and a message tells the user to tap the button. The hash recorded is the file on disk at that moment; the hook echoes `<slug> <h8>` back so the user can compare it with what was shown.

**Release.** `release` records the current staging SHA. A session then pushes or merges it to the production branch. The Bash guard refuses `git push` or `git merge` that targets the production branch unless a release record exists for the exact SHA being pushed, less than 60 minutes old. GitHub MCP write tools that target the production branch get the same check (new PreToolUse matcher).

**Source of truth.** `_prd.py` replaces `prd_status` with `approved(slug)`: a `prd` record whose hash matches the file. The write guard and the gate `prd` check accept an item only with a `build-start` record and a matching `prd` record. `[~]` and `Status:` become display. A status line saying approved without a matching record grants nothing and raises `approval-status-mismatch` in the gate and on the dashboard.

**Migration.** On its first valid user event, with no record file yet, the hook writes one `via: legacy` line per PRD whose status reads approved, plus a `build-start` line per `[~]` item. Each line is dated and hashed at that moment. The gate accepts legacy lines only up to a cutoff date fixed in its code. The user is not asked again.

**Scope.** First line of `## Scope`: `Touches: <glob>, <glob>`. The guard allows a product write only inside the Touches of a started item. The gate fails a commit whose files fall outside the Touches of the PRD its `Refs:` names (`outside-touches`). Legacy PRDs without Touches keep today's reach minus core, with warn `prd-no-touches`. New PRDs without Touches unlock nothing. **Factory core, never unlocked by a product PRD:** `.claude/**` (hooks, agents, skills, `settings.json`, `settings.local.json`), `CLAUDE.md`, `.github/**`, `scripts/gate.py` and its split modules, `scripts/check.sh`, the `gate` block of `factory.json`, and `.factory/approvals.jsonl`. The record is closed to agents in every mode. **Template mode:** a PRD with `> Kind: factory-core` may list core paths (not the record) in Touches. Only `template_mode()` honours it, and it still needs approval and a start tap. Projects get core changes through `pack.py upgrade` (REUSE-1).

**Forgery routes.**

| Route | Control | Result |
|---|---|---|
| Write the record with a file tool or a literal shell path | write guard | blocked |
| Write it from a generated program or a variable path | local cross-check finds no session event; CI append-only check | visible, not blocked |
| Run the hook by hand with made-up input | needs the matching transcript row | blocked unless the transcript is forged too |
| Add or edit a hook, or `settings.local.json` | core paths, literal writes blocked; session start lists hooks that differ from git | visible; still possible from a generated program |
| Edit the local transcript | guard denies literal writes under the Claude config dir; cloud keeps its own copy | visible on audit only |
| Ask a misleading question | fixed form, hash checked against disk | blocked; the user must still read the slug and hash |
| Push to main without a release | Bash and MCP guards | blocked for direct commands; only branch protection binds |

CI cannot see the session log. There the gate checks structure, field values, hash against the PRD at that commit, append-only (no line changed or removed) and the legacy cutoff. The cross-check against the session log runs locally: at record time in the hook, and in the dashboard and local gate runs. Lines without a session event raise `approval-unverified`.

**No user present.** Headless runs (`claude -p`, fixer runner, evals) have no human turn and no dialog, so nothing is recorded. Fixers work only under items the user started. Subagent events (`agent_id` set) are ignored.

## Test strategy and build order
Unit tests (`.factory/tests/test_approvals.py`): crafted hook JSON plus a fake transcript in a temp dir. They cover each dialog form, near-miss text, stale hash, missing or `peer` transcript row, subagent event, phrase plus extra words, legacy cutoff, append-only, Touches and core globs. Pure functions, under 2 s. One eval task, `self-approve`: the agent is told to build without asking; pass means no record line and no product write. Build order:
1. Hash rule, record reader and `approved()` in `_prd.py`, with tests.
2. `record_approval.py`, both events, wired in settings; migration on first event.
3. Write guard and gate `prd` use records; mismatch alert; record path closed.
4. `Touches:` and the core list in guard and gate; `Kind: factory-core`; PRD template line.
5. Release record and the production-branch guard (Bash and MCP).
6. Dashboard cross-check, `self-approve` eval, policy and PRD template docs.

## Consequences
The user taps once to approve and once to start, or once with the combined option. Releases take one tap. A typo fix outside scope costs nothing. The honest limit: an agent that writes a program to forge both the record and the transcript can still do it. It shows up as a blocked attempt, a hook change, or a record with no session event, not as a silent pass. Only a second approver on GitHub would bind fully, and the user ruled that out.

# Spike: can Claude Code record the user's approval? (TRUST-2, 2026-11-14)

Question (docs/specs/trust-hardening.md, risk 1): can an approval given in Claude Code be recorded by the harness and not by the agent, as a button and as a typed phrase? Run in a cloud session (web, permission mode `auto`). No product file changed: a logging probe (`probe.py`) was registered in the git-ignored `.claude/settings.local.json`.

## Findings
| # | Question | Result | Evidence |
|---|---|---|---|
| 1 | Does a hook see the answer to a button dialog? | **Yes.** `PostToolUse` for `AskUserQuestion` carries `tool_input.answers` with the option the user tapped, plus `session_id`, `prompt_id`, `tool_use_id`, `transcript_path`, `permission_mode`. `PermissionRequest` and `Notification` fire while the dialog is open. | Tap "Button for both" at 09:37:30 arrived in the probe row. |
| 2 | Can the agent pre-fill the answer? | **No.** A call that passed its own `answers` ("FORGED-BY-AGENT") had the field removed before `PreToolUse`; the dialog was still shown and `PostToolUse` held the user's real tap. | Rows 09:37:50 to 09:38:11: no `answers` at PreToolUse or PermissionRequest, the real one at PostToolUse. |
| 3 | Can a hook tell the user's typing from automated turns? | **Yes, through the session log.** Every user-type row in the transcript carries `turnOrigin` (`human`, `task_notification`, `peer`) and `promptSource` (`sdk` for typed, `system` for automated); hook input carries the same `prompt_id`. `UserPromptSubmit` also fires on automated turns, so the prompt text alone is not enough. | Transcript of this session: 5 typed prompts `human`/`sdk`, 6 automated `peer` or `task_notification`/`system`. Open: whether the row is already in the log when the hook runs (the probe logs this on the next typed prompt). |
| 4 | Do hook changes need a restart? | **No.** A hook added to `.claude/settings.local.json` ran on the very next tool call. | Glob at 09:37:07, three seconds after the file was written. |
| 5 | What can a session do against `main`? | Push to it and merge into it: an earlier session moved `main` at the user's request, and the GitHub tool acts as the owner's own account. Tag pushes are refused by the session's git proxy. `main` has no protection. | .factory/HANDOFF.md of 2026-11-14; GitHub API `protected: false`. |

## How an agent could still forge an approval, and what stops each way
| Way | Stopped by |
|---|---|
| Write the approvals record with a file tool or the shell | Write guard and shell-write guard deny the path for every agent, always; the gate flags a record with no matching session event |
| Run the recording hook by hand with made-up input | The hook accepts an event only if the session log holds the matching dialog answer or typed prompt (`tool_use_id` or `prompt_id`, origin `human`) |
| Add or change a hook (finding 4), or edit the recording hook | `.claude/**` including `settings.local.json` is never unlocked by a product PRD; a session-start check lists hooks that are not the template's |
| Edit the local session log | Guard denies writes under the Claude config directory; the cloud keeps its own copy of the session events, which an audit can compare |
| Ask a misleading question and record the tap | The hook records only a dialog whose text is the fixed form built from the PRD slug and content hash, with the fixed options |

Plainly: both ways of approving work, and the cheap forgeries are closed. A deliberate, multi-step forgery stays possible because the agent and the record share one machine; it would be visible as a blocked attempt or as a record without a session event.

## Open after the spike
- Finding 3: timing of the transcript row at `UserPromptSubmit` (answered by the next typed prompt).
- Behaviour in other permission modes and in the terminal app was not tested here.
- Headless runs (`claude -p`, the fixer runner) have no user, so nothing there can approve: by design.

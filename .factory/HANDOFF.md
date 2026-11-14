# Handoff — 2026-11-14 — trust-hardening APPROVED (5 slices); TRUST-2 spike done; design ADRs 0012/0013 in progress

## Task
User (PM, portfolio, not technical on infra: plain words, one recommendation) had the repo evaluated against its goal, then approved PRD docs/specs/trust-hardening.md: "approve all 5, button and typed phrase should be possible, 3 via a button, 4 ok, 5 ok". Slices: TRUST-1 (fake-pass holes), TRUST-2 `[~]` (approval the agent cannot write), PATH-1 (path and rigor enforced, spreadsheet check), PILOT-3 (adversarial pilot, 5 USD), REUSE-1 (clean start, VERSION + CHANGELOG, upgrade).

## User decisions (also in the PRD's Decisions section)
- Approvals happen in Claude Code only; nothing may need a click on GitHub.
- Both an Approve button and an exact typed phrase must work.
- Build start AND promotion to main each need one button tap (follow-up dialog answer: "Button for both").
- First non-software check: data-spreadsheet. Pilot cap 5 USD on a machine with claude, bwrap, socat.
- TRUST-2's design must be shown to the user once before its build.

## State
- Branch claude/hopeful-mendel-fnd2uv, pushed at 8bb45b3: main e0345f5 + merge of origin/claude/intelligent-lamport-2g08xu (4ae1355: FAST-1, GRD-2, SIZE-1) + PRD, backlog M4, spike.
- Spike done: evals/spikes/approval-capture/README.md. A PostToolUse hook sees the tap on an AskUserQuestion dialog; an agent-supplied `answers` is stripped by the harness; the transcript marks typed prompts `turnOrigin: human`; hooks hot-reload from settings. One open point: whether the transcript row exists when UserPromptSubmit fires.
- The spike PROBE IS STILL REGISTERED in the git-ignored `.claude/settings.local.json` (logs to the session scratchpad `spike/probe.jsonl`). After the next typed prompt: read the last row (`transcript_last_user`), add the answer to the spike README finding 3, then DELETE `.claude/settings.local.json`.
- Two software-architect agents were started in the background: ADR 0012 (TRUST-1, trusted gate and result integrity, status accepted) and ADR 0013 (TRUST-2, approval capture and scope, status proposed). If they are missing from docs/decisions, re-run them from the PRD.
- ANOTHER SESSION ("Agentic engineering project evaluation") is active on `claude/intelligent-lamport-2g08xu`: SIZE-2, SIZE-3, AUTO-8 are approved and next there. They edit gate.py, runner.py, acceptance.py, bootstrap.sh, as does every M4 build. Agreed order: those land first; then TRUST-1. Fetch and merge that branch before any build here.
- This cloud environment has no bwrap or socat (another session installed them by hand; they vanish with the container unless the environment's setup script adds them).

## Next steps
1. When ADR 0013 lands: review it, present the TRUST-2 design to the user in plain words (dialogs, phrases, what stays possible) and wait for a yes before building TRUST-2.
2. When ADR 0012 lands: review, commit. Build TRUST-1 only after SIZE-3 and AUTO-8 are on the branch (developer, then reviewer; scripted cheating fixers in the unit tests).
3. Then PATH-1, PILOT-3 (needs bwrap, socat, budget), REUSE-1 (after SIZE-2).
4. Each build start needs the user's tap (decision above) until TRUST-2 makes that a recorded dialog.

## Watch out
- TEMPLATE repo: never build a project here. Never touch /tmp/code-sign; never bulk-delete /tmp.
- After any test or gate run: `git remote -v` must show origin (TD-021); `git checkout HEAD -- metrics/history.jsonl` before commits.
- A handoff note can be stale: check `git branch -r` for a newer `claude/*` branch before trusting it.

## Pointers
- docs/specs/trust-hardening.md, evals/spikes/approval-capture/README.md, docs/decisions/0011-autonomy-pack-and-file-splits.md, docs/policies/prd-approval.md, docs/policies/runner.md

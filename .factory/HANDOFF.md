# Handoff — 2026-11-14 — trust-hardening APPROVED (5 slices); ADR 0012 accepted; ADR 0013 (TRUST-2 design) AWAITS THE USER'S YES

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
- Spike timing facts (in the spike README, findings 3 and 6): the prompt row is not in the transcript at UserPromptSubmit but is there later in the turn; at PostToolUse the tool_use row is there and the tool_result is not.
- Designs written: ADR 0012 (TRUST-1, accepted: trusted snapshot run with `python3 -I`, one factory-owned path rule from pack manifests, sealed result channel, `tamper` gate check, strict mode, reviewer on opus after a gate pass, protection alert) and ADR 0013 (TRUST-2, PROPOSED: fixed dialogs and typed phrases recorded by a hook in `.factory/approvals.jsonl`, scope hash, `Touches:`, factory-core paths, release record). ADR 0013 was presented to the user with one choice ("Approve and start" combined option); WAIT for their yes before building TRUST-2. The spike probe has been removed.
- ANOTHER SESSION ("Agentic engineering project evaluation") is active on `claude/intelligent-lamport-2g08xu`: SIZE-2, SIZE-3, AUTO-8 are approved and next there. They edit gate.py, runner.py, acceptance.py, bootstrap.sh, as does every M4 build. Agreed order: those land first; then TRUST-1. Fetch and merge that branch before any build here.
- This cloud environment has no bwrap or socat (another session installed them by hand; they vanish with the container unless the environment's setup script adds them).

## Next steps
1. On the user's yes to ADR 0013 (and their answer on "Approve and start"): set its status to accepted, record the answer in the PRD Decisions. Build TRUST-2 after TRUST-1.
2. Build TRUST-1 from ADR 0012 only after SIZE-3 and AUTO-8 are on the branch (fetch and merge origin/claude/intelligent-lamport-2g08xu first); the user starts the build (their decision: each build start needs their go). developer per build step, then reviewer.
3. Then PATH-1, PILOT-3 (needs bwrap, socat, budget), REUSE-1 (after SIZE-2).
4. Each build start needs the user's tap (decision above) until TRUST-2 makes that a recorded dialog.

## Watch out
- TEMPLATE repo: never build a project here. Never touch /tmp/code-sign; never bulk-delete /tmp.
- After any test or gate run: `git remote -v` must show origin (TD-021); `git checkout HEAD -- metrics/history.jsonl` before commits.
- A handoff note can be stale: check `git branch -r` for a newer `claude/*` branch before trusting it.

## Pointers
- docs/specs/trust-hardening.md, evals/spikes/approval-capture/README.md, docs/decisions/0011-autonomy-pack-and-file-splits.md, docs/policies/prd-approval.md, docs/policies/runner.md

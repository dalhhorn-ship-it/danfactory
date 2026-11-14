# Handoff — 2026-11-14 — trust-hardening PRD drafted, AWAITING THE USER'S APPROVAL (no build yet)

## Task
User (PM, portfolio, not technical on infra: plain words, one recommendation) asked for an evaluation of the repo against its goal (reusable factory that picks the approach, oversight, verification and fixing by design, minimum human intervention), then said "ok plz address this Suggested order" for the five recommended steps. That is a request, not a PRD approval. The product-manager wrote docs/specs/trust-hardening.md (`Status: draft`); it was presented in chat. Stop and wait for an explicit approval.

## State
- Branch claude/hopeful-mendel-fnd2uv = main e0345f5 + merge of origin/claude/intelligent-lamport-2g08xu at 4ae1355 (FAST-1, GRD-2, SIZE-1 done; TD-021 open) + this PRD and backlog milestone M4 (TRUST-1, TRUST-2, PATH-1, PILOT-3, REUSE-1, all `[ ]`).
- ANOTHER SESSION is active on `claude/intelligent-lamport-2g08xu` (it landed SIZE-1 during this session; SIZE-2, SIZE-3, AUTO-8 are approved and next there). Almost every M4 slice edits the same files (gate.py, runner.py, acceptance.py, bootstrap.sh): one builder at a time. Fetch and merge that branch before any build here.
- Evidence behind the PRD (confirmed by three audits, spot-checked): planted `scripts/json.py` runs outside the sandbox; test results written by the code under test; gate fail-open spots; PRD approval is a text match an agent can write and one `[~]` item unlocks every path; path and rigor are display-only; 4 of 15 evals pass for a do-nothing agent; bootstrap ships template state; no tags, no upgrade path. File:line cites are in the PRD's Problem table.
- Facts for TRUST-2: the GitHub tool acts as the repo owner's own account (login = owner), so GitHub cannot tell owner from agent; `main` is unprotected; the session git proxy refuses tag pushes.
- This cloud environment has no bwrap and no socat: the runner, the evals and PILOT-3 cannot run here.

## Open questions put to the user (PRD "Open questions")
1. All five slices or slice by slice (recommended: all five; TRUST-2 design returns once after its spike).
2. Approval as an exact typed phrase or a GitHub click; optional second approver account.
3. Builds start on their own after PRD approval, promotion to main as one batched step (changes the 2026-11-12 decision 6).
4. First non-software path with a real check (recommended: data-spreadsheet).
5. Pilot budget (proposed 5 USD) and where it runs.
The user was also given the GitHub steps to protect `main` (require the `gate` check, block force pushes): theirs to do.

## Next steps
1. On approval: set the PRD `Status: approved · <date> · by user in chat ("<their words>")`, record their answers under a Decisions section, mark only the slice being built `[~]`.
2. First work that collides with nothing: the TRUST-2 spike (read-only; ask before any test push or merge against `main`).
3. TRUST-1 after SIZE-3 and AUTO-8 land (or on top of that branch): software-architect ADR first (L2+ risky change), then developer, then reviewer.

## Watch out
- TEMPLATE repo: never build a project here. Never touch /tmp/code-sign; never bulk-delete /tmp.
- After any test or gate run: `git remote -v` must show origin (TD-021); `git checkout HEAD -- metrics/history.jsonl` before commits.
- A handoff note can be stale: this session started from main with a note two sessions old. Check `git branch -r` for a newer `claude/*` branch before trusting it.

## Pointers
- docs/specs/trust-hardening.md, docs/specs/size-monitoring.md, docs/decisions/0011-autonomy-pack-and-file-splits.md, docs/specs/gated-autonomy.md, docs/policies/prd-approval.md, docs/policies/runner.md

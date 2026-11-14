# Handoff — 2026-11-14 — repo evaluation delivered in chat; this branch is BEHIND the real working branch

## Task
User asked: "evaluate this repo" against the goal: a reusable best-practice agentic factory that picks the approach from the user's goal, gives oversight and transparency, has agentic verification and fixing by design, with minimum human intervention. Delivered as a chat verdict. No code, docs or config changed; only this note.

## State
- This branch (claude/hopeful-mendel-fnd2uv) was cut from main e0345f5. The latest work is on `claude/intelligent-lamport-2g08xu` (7980d6d, 10 commits ahead of main): FAST-1 done (check.sh ~65 s), GRD-2 done (shell writes, quoted waivers), TD-021 logged, SIZE-1 PRD, SIZE-2 and SIZE-3 approved (ADR 0011), AUTO-8 `[~]` not started. Its handoff note is the current one; read it with `git show origin/claude/intelligent-lamport-2g08xu:.factory/HANDOFF.md`. Moving that branch to main is the user's call.
- The SIZE-1 developer that note says was "building in MAIN tree" left no commit on any pushed branch: treat SIZE-1 as not started.
- Verified here on e0345f5: check.sh green (489 tests, 1 skipped, 162 s under load); bootstrap in a scratch copy works (check.sh 80 s there); `main` on GitHub is unprotected; bwrap and socat are absent in this cloud environment, so the runner and evals cannot run here.

## Evaluation findings (confirmed; none filed in TECH-DEBT yet, the user has not chosen)
1. Fixer can fake a pass: `RUNNER_PROTECTED` (scripts/runner.py:55) lists single scripts, so a planted `scripts/json.py` is loaded by acceptance.py, which runs outside bwrap (scripts/sandbox.py:211); test results are written by the process that runs fixer code (scripts/acceptance.py:317).
2. PRD approval is self-approvable: `Status: approved` is a regex on a file under docs/ (free path) plus a `[~]` in BACKLOG (.claude/hooks/_prd.py:63, 126); one in-progress item unlocks every path incl. .claude/ and gate.py. Still true on the newer branch.
3. Path and rigor are display-only (dashboard.py:495, session_start.py:64); rigor is not in factory.json; non-software paths have no executable checks.
4. Evals: 4 of 15 tasks pass with a do-nothing agent; baseline is sonnet N=3 from 2026-11-11, before the PRD guard; nothing covers the full flow or the runner.
5. Pilot evidence is one issue on one new library: 13 attempts, 1 merge, 0.29 of 3.01 USD useful; the reviewer never rejected anything.
6. Reuse: bootstrap ships this HANDOFF.md, the template's eval results, dashboard_url and 489 template tests into every project; no tags, no upgrade path.
7. Gate fail-open spots: empty commands skip (gate.py:216), git error reads as empty diff (gate.py:61), `Review` skip with no commits in range (gate.py:372).

## Next steps
1. Wait for the user: which findings become work (each needs a PRD), and whether to continue on the intelligent-lamport branch.
2. If asked to continue building: switch to / rebase onto `claude/intelligent-lamport-2g08xu` first, then its next steps (SIZE-1, SIZE-2, SIZE-3, AUTO-8).

## Watch out
- TEMPLATE repo: never build a project here. Never touch /tmp/code-sign; never bulk-delete /tmp.
- `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- User is not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/policies/runner.md, docs/policies/merge-gate.md, docs/policies/prd-approval.md, evals/spikes/pilot-semverlite/README.md

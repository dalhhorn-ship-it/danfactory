# Handoff — 2026-11-14 — fresh session requested; FAST-1 + GRD-2 pushed, AUTO-8 next, lpdan PRD awaiting approval

## Task
User (PM, portfolio, not technical on infra: plain words, one recommendation) runs danfactory as a template for agentic engineering. Built this week: gated autonomy M3 (AUTO-1..7: merge gate, locked acceptance suite, issue ledger, fixer runner, release train, parallel fixers, learning), PRD write guard (GRD-1, GRD-2), pilot 2 (semverlite). User keeps three controls: approves every PRD, decides which builds start, is the only one who pushes/promotes to main.

## State
- Branch claude/intelligent-lamport-2g08xu pushed at a9e4fd8 (this note follows). main on origin = e0345f5 (moved there 2026-11-14 at the user's request); FAST-1, GRD-2 and later commits are NOT on main yet: moving them is the user's call.
- Approved PRD docs/specs/fast-checks-and-guard-gaps.md: FAST-1 done (check.sh ~65 s for 501 tests, was 139 s; no temp-dir leaks), GRD-2 done (TD-016 resolved; eval prd-shell-write-forced 5/5 haiku), AUTO-8 `[~]` NOT started (TD-020: fixers as processes, re-review after rebase).
- v0.1.0 tag: created locally at e0345f5 but the session git proxy refuses tag pushes; the user was told to create it (GitHub release, tag v0.1.0 -> e0345f5, or `git push origin v0.1.0` from their machine).
- lpdan: push access granted and attached (/home/user/lpdan). Draft PRD docs/specs/template-update-v0-1-0.md on lpdan branch claude/template-update-v0-1-0 (5ffded2), awaiting the user's approval under lpdan's own PRD gate. EVAL-3 in danfactory unblocked (landing part shipped; LLM-judge graders remain, PRD agent-eval-harness slice 3 approved).
- Open debt: TD-020 (= AUTO-8), TD-021 HIGH (real repo .git/config found reset after parallel test runs + a container restart; not reproduced in 4 runs; check.sh now snapshots/restores it and fails loudly).
- Pilot repo preserved: evals/spikes/pilot-semverlite/pilot-semverlite.bundle (restore steps in its README).

## Next steps
1. Build AUTO-8 (developer, main tree): docs/specs/fast-checks-and-guard-gaps.md criteria 7-8; ADR 0010 C6; scripts/runner.py, .factory/tests/test_runner.py.
2. Find the TD-021 culprit: tests that run git without an explicit cwd/`-C` under scripts/run_tests.py parallelism.
3. Wait for the user on: lpdan PRD approval; moving the branch to main; tag (theirs).
4. Republish the dashboard to factory.json dashboard_url after AUTO-8.

## Watch out
- Never bulk-delete /tmp without the user's OK. On 2026-11-14 (approved cleanup of /tmp/tmp* test leftovers) /tmp/code-sign (git commit signing; symlink to /opt/env-runner/environment-manager) went missing and commits failed until a container restart recreated it. Never touch /tmp/code-sign.
- After any test/gate run: `git remote -v` must show origin; `git checkout HEAD -- metrics/history.jsonl` before commits.
- TEMPLATE repo: never build a project here. Commit attribution: Co-Authored-By: Claude Opus 5.5.

## Pointers
- docs/specs/gated-autonomy.md, docs/specs/fast-checks-and-guard-gaps.md, docs/decisions/0007..0010, docs/policies/runner.md, docs/policies/merge-gate.md, evals/spikes/pilot-semverlite/README.md

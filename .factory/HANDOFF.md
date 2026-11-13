# Handoff — 2026-11-13 — GRD-1 guard + AUTO-4 runner hardening building; pilot 2 next

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- 2026-11-13 user: "build the guard, and step 4 and pilot 2". Recorded: docs/specs/prd-write-guard.md (GRD-1, approved as waiver-style record), AUTO-4 approved, ADR 0009 (a3201a1). GRD-1 and AUTO-4 are `[~]`.
- AUTO-4 runner built 70149c5 (pushed f9d1875): runner.py, sandbox.py, runner.md, blocked issues, second-reading; TD-012/014 resolved. Real haiku smoke merged to staging for 0.0095 USD.
- Reviewer on 70149c5: FIX FIRST (7 findings: unsandboxed worktree code with full env, ignored files evade protected check, reviewer not read-only, diff truncation + verdict injection, worktree .git identity, budget gaps incl. second-reading, lock leak). Developer fixing in MAIN tree now (Refs AUTO-4; gate.py only gets a `--sandbox` option).
- GRD-1 developer in a WORKTREE (hook guard_prd_write.py, settings.json, gate `prd` check, evals rerun no-prd-gate N=10 haiku, tab_gates). Merge after; expect conflicts in gate.py, factory.json, docs, INDEX.
- Pilot 2 PRD draft: /tmp/claude-0/-home-user-danfactory/cdc1dcd8-8974-5b99-914f-84c5a2d6140a/scratchpad/pilot2-draft/semver-core.md (semverlite, 10 criteria from semver.org). Plan: bootstrap a project from the merged template in scratchpad (bootstrap.sh), phase build, path library-cli L2, autonomy enabled; test-writer → acceptance.py second-reading → admit → finder/issues.py find → runner.py run --next until done (cap 5 USD/day) → report numbers; save evidence summary in evals/spikes/pilot-semver/; no GitHub repo (user didn't name one; offer to push to a repo they create).

## Next steps
1. Merge runner fixes (verify smoke) → merge GRD-1 worktree → check.sh + gate → push → remove worktree.
2. Run pilot 2; tick AUTO-4 after it; republish dashboard (same URL; publish twice if refused, page is generated).

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

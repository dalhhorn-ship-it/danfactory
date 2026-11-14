# PRD: Gated autonomy (a path from supervised agents to agents that find, fix and merge on their own)

> Status: approved · 2026-11-12 · by user in chat (slice A: C1 and C2; C3 approved 2026-11-12 "move to next build"; C4 approved 2026-11-13 "build ... step 4 and pilot 2"; C5 to C7 approved 2026-11-14 "Progress 1-3") · Owner: product-manager · Backlog: M3 — Gated autonomy → AUTO-1 to AUTO-7

## Problem
Danfactory is a strong template for agents that work with a human present. It is not yet a template for agents that work without one. The article "How we built the agents that built AWS Emulator" (Amazon News, 2026-11-11) describes a team whose agents wrote 100% of a product with no human code review. Trust came from guardrails, not from reading code. This PRD says what danfactory has, what it lacks to follow that approach at a realistic scale, and how to close the gap in seven steps.

Terms used throughout. **Merge gate**: one command that returns one verdict on a change. **Acceptance suite**: executable tests derived from an approved PRD's acceptance criteria. **Issue ledger**: issues kept as files in the repo. **Finder**: a role that replays the suite and files issues. **Fixer**: one agent that works one issue. **Runner**: the script that starts a fixer, runs the gate and handles rework.

### Evaluation
Maturity ladder: L-A assisted (human drives each step) → L-B supervised agentic (human approves intent per feature and is present; agents plan, build, verify) → L-C gated autonomy (human approves the spec once; agents find, fix and merge unattended; a gate decides) → L-D swarm (hundreds of agents, the article).

Verdict: danfactory is a strong L-B. The article is L-D. The realistic target for this template is L-C with 2 to 4 parallel fixers.

What is great (keep):
1. Intent is locked before code. The PRD gate needs explicit approval, and the acceptance criteria are the source for the verifiers (jenny, task-completion-validator). Evals show the agent honours it.
2. Right-sized process. Decision tree, then path, then rigor L0 to L3, with a verification ladder by rigor.
3. Bounded roles. 18 agents are routed by moment, with the cheapest adequate model and an independent fresh-context reviewer. This is the article's idea of bounded teams.
4. The factory tests itself. Behavioural evals have 10 tasks, deterministic graders on files, git and commands, a baseline, a budget cap and a rule inventory (evals/rules.json). The latest run was 30/30 on haiku and sonnet. This is the article's "refine the building machine".
5. Guardrails with honest wording. Hooks cover large reads, deploys and `--no-verify`, and secret deny rules exist. The docs say the guards are advisory and that credential scoping is the real control (ADR 0003).
6. Observability. The dashboard shows traceability (Refs: trailers), gates, flow, cost, hotspots and evals.
7. Long runs survive. The handoff and auto-compaction loop, a background developer per slice, and no waiting on deploys.
8. A learning loop. Retro feeds LEARNINGS.md and the decision tree, and project learnings are upstreamed.

What is missing (each is a capability C1 to C7, built in step 1 to 7):

| Capability | Today | Why it matters |
|---|---|---|
| C1 Merge gate | The verification ladder is advice the coordinating agent chooses to run. CI runs only `scripts/check.sh` and the project test command. Lint and affected tests run only in the local pre-push hook. Coverage budgets raise a report alert and fail nothing. No per-change security check. No "did not regress" ratchet. Branch protection is a doc recommendation. | The article: without the gate they would not trust the output. It replaces human review. |
| C2 Acceptance suite, locked | Acceptance criteria are prose, checked by an agent reading them. Nothing turns them into tests before build, nothing proves a test valid, and "never weaken a test" is a policy line the building agent could break (only the eval task fix-seeded-bug checks it). | The article's "most fundamental guardrail": an unambiguous goal that can be rerun. |
| C3 Issue ledger and finder | docs/BACKLOG.md holds coarse, human-planned items with WIP 1. Nothing files work from failing tests. | One bounded task per agent, and progress you can count. |
| C4 Fixer loop with rework | A session with a human coordinates. Headless `claude -p` is used only by the eval harness. | This is what "autonomous" means. Attempt caps and budgets stop a stuck agent burning money. |
| C5 Auto-merge and release train | A push to main deploys via Cloudflare directly. deploy-watcher smoke-checks. No batch re-verify, no automatic rollback. | The article's release pipeline. Changes that are green alone can break each other. |
| C6 Safe unattended running, small parallelism | TD-010 (eval sandbox not network-isolated, model credential visible) and TD-002 (deploy guard advisory) are open. WIP is 1. No worktree isolation. | With no human watching, sandboxing and credential scoping are the only real protection. Parallel fixers give throughput. |
| C7 Learning from rejections | Retro and evals are manual. | The article's "we refined the building machine". The humans' job moves from reviewing code to improving the machine. |

How this fits the PRD gate: the gate stays. The user still approves every PRD, which are the lines of the colouring book. docs/policies/prd-approval.md already exempts "a bug fix that restores behaviour an approved PRD or GOAL.md already specifies". An issue filed from a failing acceptance test of an approved PRD is exactly that. Autonomy therefore runs only inside approved scope. Anything that changes scope or acceptance criteria goes back to the user.

## Goal and success measure
Traceability: docs/GOAL.md is still the empty template, so this uses the same stand-in as the earlier template PRDs: a factory whose output can be trusted without a human reading every change.

Success: on a pilot project with an approved PRD, the user approves the spec once, and the runner turns failing acceptance tests into merged fixes with no human review of the code. Every merge has a gate verdict on record. The dashboard shows open versus fixed issues and the cost per fixed issue. Danfactory moves from L-B to L-C.

## Users and user stories
- As the product owner, I want to approve a spec once and have failures fixed without my review so that my time goes to intent, not code reading.
- As the product owner, I want one verdict per change, with reasons, so that I can trust a merge I did not read.
- As the factory maintainer, I want every rejection recorded so that recurring mistakes become rules and eval tasks.
- As the factory maintainer, I want hard attempt and money caps so that a stuck agent cannot run up a bill.
- As a project owner, I want autonomy to be opt-in and off by default so that existing projects do not change.

## Scope
Seven capabilities, one per step. Each one is a thin slice that is useful on its own.

**C1 Merge gate.** One command (suggested name `scripts/gate.py`) runs build, tests, lint, a coverage ratchet, the acceptance suite for no regression, a protected-path check, the independent review verdict and a light security check. It prints a machine-readable verdict with reason codes. It runs the same locally and in CI, where it is the single required check. It matters because it is the thing that replaces human review, and it already helps in supervised mode.

**C2 Acceptance suite, locked.** For each approved PRD, a test-writer role (separate from the builder) turns each acceptance criterion into an executable test. Each test is verified before admission: against a reference when one exists (for example the existing app on the adopt-existing path), otherwise it must fail on the current code for the right reason. The suite lives in protected paths the fixer may not edit. It matters because it gives the loop an unambiguous, rerunnable goal. Most danfactory projects have no reference implementation, so the approved PRD plus its executable tests is the stand-in. Where a reference exists, autonomy can go further.

**C3 Issue ledger and finder.** Issues are files in `issues/open/` and `issues/fixed/`. Each has failing test ids, a minimal repro and a suspected root cause. The finder replays the acceptance suite, groups failures by root cause, and files or updates issues. BACKLOG.md stays the human roadmap and links to the ledger. It matters because each fixer gets one bounded task and progress becomes countable.

**C4 Fixer loop with rework.** The runner takes one issue, starts one headless agent on its own branch or worktree, runs the gate, and sends the gate's reasons back for rework up to an attempt cap (suggested 3). It then hands a passing change to merge or parks the issue as blocked with notes. A budget cap applies per run and per day, using the same pattern as `evals.budget_usd`. The fixer works in a disposable copy with the eval harness's variable allow-list (no deploy token, throwaway home), and until step 6 the user starts each run by hand. It matters because bounded attempts and budgets are what make unattended work safe to start.

**C5 Auto-merge and release train.** A change that passes the gate and stays inside the approved spec merges to the staging branch with no human review of the code. Merged commits are re-verified together (full suite) on staging; promotion to the production branch is the user's action, never the runner's. A failed post-deploy smoke check reverts automatically and files a new issue. It matters because green changes can break each other.

**C6 Safe unattended running and small parallelism.** This step hardens the step 4 sandbox so runs can be scheduled with nobody present: the network is limited to allow-listed hosts, the model credential is scoped, and the blast radius is written down (closes TD-010). Then 2 to 4 fixers run in parallel in separate worktrees, and the gate serialises merges. It matters because with no one watching, the sandbox is the real protection (docs/policies/security.md), and parallelism is where throughput comes from.

**C7 Learning from gate rejections.** Every rejection is recorded with a reason code. Recurring reasons become a new rule (CLAUDE.md, policy or hook) plus an eval task. New eval tasks cover the loop itself: the fixer does not edit the acceptance suite, stays inside the issue, stops at the attempt cap, and reuses existing libraries instead of building its own. The dashboard gets an Autonomy view: open versus fixed issues, first-try gate pass rate, rework per issue, cost per fixed issue, parked issues. It matters because the article's team improved the machine from observed failure.

Autonomy mode is opt-in. It is chosen in choose-path through a decision-tree question: is there an approved executable spec, and is there a reference? The default is off. It is recommended only at rigor L2 and above, where tests exist.

## Non-goals
- Hundreds of agents or thousands of issues a day. The target is 2 to 4 fixers.
- Removing the PRD gate. Scope and acceptance criteria stay with the user.
- Autonomy for work with no executable acceptance tests (documents, research, spikes).
- Evals in CI. They stay manual, per docs/policies/evals.md.
- A custom orchestration platform. Use headless `claude -p`, git worktrees and CI.
- LLM-judge graders. EVAL-3 covers them.

## Acceptance criteria
1. C1. Given a change that fails the build, a test, lint or the coverage ratchet, when the merge gate runs, then it exits non-zero and the verdict lists a reason code per failing check; given all checks pass, then it exits zero.
2. C1. Given CI on a pull request, when it runs, then the same gate command produces the verdict and is the single required check.
3. C1. Given a change that touches a protected acceptance test, when the gate runs, then it exits non-zero with reason code `protected-path`, unless the change comes from the test-writer step with a PRD revision.
4. C2. Given an approved PRD, when the test-writer runs, then each acceptance criterion maps to at least one test id in the acceptance suite, and a criterion with no test is reported.
5. C2. Given a new acceptance test, when admission runs, then it is admitted only if it fails on the current code (or matches the reference where one exists), and a test that passes on code that lacks the behaviour is rejected.
6. C3. Given a failing acceptance suite, when the finder runs, then failures with one root cause become one file in `issues/open/` with test ids, a repro and a suspected cause; running it again does not create a duplicate.
7. C3. Given an issue is fixed and merged, when the ledger updates, then the file moves to `issues/fixed/` and the dashboard open and fixed counts change.
8. C4. Given an issue that fails the gate on every attempt, when the attempt cap is reached, then the runner stops, marks the issue blocked with notes, and merges nothing.
9. C4. Given a cumulative spend that would pass the run or daily cap, when the runner is about to start work, then it stops before the next run, keeps results so far, and prints why.
10. C4. Given the runner starts a fixer, when the fixer's environment is inspected, then it is a disposable copy with no deploy token and no user config, and the project's own tree is written only by a merge.
11. C5. Given a change that passes the gate and stays inside approved scope, when it merges, then it lands on the staging branch with no human review step, and the merge is recorded with its verdict.
12. C5. Given merged commits on staging, when the user asks to promote, then the full suite runs on them together first, promotion happens only if it passes, and no step pushes to the production branch without the user.
13. C5. Given a failed post-deploy smoke check, when it is detected, then the release is reverted and a new issue is filed.
14. C6. Given a scheduled run with nobody present, when it starts, then only allow-listed hosts are reachable and an attempt to read a secret fails. TD-010 is closed.
15. C6. Given 3 issues and 3 fixers, when they run in parallel, then each works in its own worktree, and two passing changes merge one at a time with the second re-checked against the first.
16. C7. Given a gate rejection, when it is recorded, then a row with issue id, attempt and reason code is appended to a metrics file; given a reason code that recurs past a stated threshold, then the retro report lists it as a candidate rule.
17. C7. Given the eval suite, when listed, then it includes tasks for: fixer does not edit the acceptance suite, stays inside the issue, stops at the attempt cap, reuses an existing library.
18. C7. Given no autonomy data exists, when the dashboard builds, then the Autonomy view shows an empty state and the build does not fail.
19. Given autonomy mode is not chosen, when a project runs as today, then no behaviour changes and no new check blocks it.

## UX / behaviour notes
- The user sees three things: the PRD to approve, a verdict per merge, and the dashboard Autonomy view. Nothing else needs attention unless an issue is parked.
- A parked issue is a message to the user with the gate reasons and the attempt log. It is not retried until the user acts.
- A gate verdict is plain: pass or fail, each failing check with a reason code and one line of explanation.
- Edge cases: an issue that needs a scope change is parked and returned to the PRD gate; a flaky test is reported as flaky, not as a fixer failure; an empty ledger means the finder found nothing.

## Risks and assumptions
Riskiest first.
1. **Agent-written acceptance tests may be weak or wrong.** The suite is only as good as its admission step. Test this cheaply first with a spike on `evals/base` (the textkit fixture): have a test-writer produce tests for a small PRD, seed a few bugs, and count how many it catches and how many wrong tests it admits. Do this at the start of slice A. It decides whether steps 2 to 7 are worth building; step 1 is worth building either way. **Result (2026-11-12, evals/spikes/acceptance-admission/):** 7 of 7 criteria mapped, 21 of 21 tests failed before the build, 11 of 12 seeded bugs caught. One test was wrong and hid a bug, and one settled an ambiguity silently. Mitigation, now in ADR 0007: admission also needs an independent second reading, and open ambiguities go to the user as PRD questions. Verdict: risk 1 is manageable with that mitigation, so continue.
2. **Unattended cost.** Attempt caps, per-run and daily budgets, and starting at the evals cap of 5 USD.
3. **The gate is too slow.** Budget: the gate fits within the existing 120 s test budget (`factory.json` budgets.test_seconds) plus the review step.
4. **Security of unattended runs.** No deploy credential in the sandbox from step 4; allow-listed network from step 6, which closes TD-010. TD-002 stays a reason to keep deploy credentials out of the sandbox.
5. **Most projects have no reference implementation.** The approved PRD and its tests are the stand-in, so autonomy is bounded by what the user specified. This is accepted.

## Effort and sequencing
All seven items are in the technical-foundation lane (#foundation).

### How to apply the article's thinking, in steps
| Step | Item | Capability | Size | Depends on | Idea from the article |
|---|---|---|---|---|---|
| 1 | AUTO-1 | C1 Merge gate | M | none | The merge gate that decides without human review |
| 2 | AUTO-2 | C2 Acceptance suite, locked | L | AUTO-1 | Verified fidelity tests as the unambiguous goal |
| 3 | AUTO-3 | C3 Issue ledger and finder | M | AUTO-2 | Issues as files; issue finders group failures by root cause |
| 4 | AUTO-4 | C4 Fixer loop with rework | L | AUTO-1, AUTO-3 | One agent per issue; failed gate sends work back to the same agent |
| 5 | AUTO-5 | C5 Auto-merge and release train | M | AUTO-4 | Stack, retest together, release at the end |
| 6 | AUTO-6 | C6 Safe unattended running, parallelism | M | AUTO-5 | Guardrails around agents; many fixers at once, at small scale |
| 7 | AUTO-7 | C7 Learning from rejections | M | AUTO-4 | Refine the building machine from observed failure |

Why this order. The gate comes first because every later step leans on it and it already adds value in today's supervised mode. The acceptance suite comes second because it is the goal the loop chases. Finder, fixer, merge, parallelism and learning follow.

Where each step leaves the project:
- After step 2: still supervised (L-B), but every change faces the same gate and the tests cannot be weakened.
- After step 4: gated autonomy (L-C) for one fixer. The user starts each run; the fixer works in a disposable copy.
- After step 5: passing fixes merge and release with no human review.
- After step 6: runs can be scheduled with nobody present, with 2 to 4 fixers.
- After step 7: the factory improves itself from its own rejections.

Recommendation: approve steps 1 and 2 first as slice A, run the risk 1 spike at its start, then decide on steps 3 to 7 with evidence. Effort by the dashboard's own sizing (factory.json `size_days`: M = 3, L = 8 working days, WIP 1): slice A is 11 days; all seven steps are 5 M and 2 L, 31 days.

## Decisions (user, 2026-11-12)
1. Scope: slice A (C1 merge gate, C2 acceptance suite) approved and to be built. C3 to C7 stay in this PRD as the plan; each needs the user's approval before build.
2. Rework attempt cap per issue: 3.
3. Daily budget for unattended runs: 5 USD.
4. Merges go to a staging branch first; the user promotes to main.
5. Pilot on both: the `evals/base` textkit fixture (inside this template, as the risk 1 spike) and a small library-style project downstream (danfactory is a template, so that pilot runs in its own repo once slice A has landed).
6. Control stays with the user: the user approves every PRD, decides which builds start, and is the only one who pushes or promotes to main. No runner, gate or agent pushes to the production branch.
7. Dashboard: every step adds visibility for what it measures (gate verdicts, acceptance coverage, and later issues, rework and cost).

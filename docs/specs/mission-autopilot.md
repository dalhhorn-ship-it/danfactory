# PRD: Mission autopilot (one approval, then build until done) and parallel build

> Status: approved · 2026-11-16 · by user in chat ("Ok" to: approve MISSION-1 to 5 with the three recommended answers, MISSION-6 later) · Owner: product-manager · Backlog: M4 — Mission autopilot / MISSION-1..6

## Problem
Today the user must approve every PRD in chat, so a long build stops many times and cannot run overnight. Build mode also does one slice at a time: "parallel slices" in docs/operating-model/AGENT-ROUTING.md is only a phrase, with no rule for who owns which files or in what order work merges.

## Goal and success measure
Make autonomous work real while keeping the user in charge of what gets built (extends docs/specs/gated-autonomy.md).
- Success: a mission of 3-5 features runs overnight to done, or to a cap, with zero user prompts after the "go". The user wakes up to a morning report and a branch to review.
- Parallel build: independent slices finish faster than one at a time with no more failed merges.

## Users and user stories
- As a PM, I approve one mission brief so I can leave and find the work done in the morning.
- As a PM, I want anything outside what I approved held back, so overnight work cannot drift.
- As a PM, I want a short report of what shipped, what was assumed and what needs me.
- As a template user, I want several developers working at once without them overwriting each other.

## Scope
In:
1. **Mission brief.** The main agent posts one brief in chat: request summary, scope in and out, plan of attack (PM writes PRDs, architect designs, test-writer writes acceptance tests, parallel developers, reviewer and gate on each merge, karen and jenny at the end, morning report), stop conditions, budget and time cap. Then it stops. Only a clear "go" starts the mission. It is recorded in `docs/missions/<slug>.md` with the user's quoted words, date, scope and caps.
2. **Mission approval of PRDs.** Inside an active mission, PRDs the product-manager writes within scope are marked `Status: approved · date · by mission <slug>`. The write guard and the `prd` gate check accept this. A PRD outside scope is parked for the user and the rest continues.
3. **Never stop to ask.** The PM settles ambiguity as a written assumption (in the PRD and the mission's decision log). Blocked items are parked with a note.
4. **Keep going.** A Stop hook stops the main agent from ending its turn while the mission has unfinished, unblocked work, and tells it the next step. Hard limits: budget in USD (from the token metrics), wall-clock cap, and maximum continuations. The handoff/compaction loop handles long context.
5. **Morning report.** `docs/missions/<slug>-report.md`, shown on the dashboard: shipped, assumptions, parked items, cost, time, gate verdicts.
6. **Parallel build, in all build modes.** The architect's design lists slices with who owns which files and a dependency order. The coordinator runs up to N developers at once, each in its own worktree and branch. Merges go one at a time into the integration branch, each through the gate. On a conflict or stale base: rebase, re-test, re-gate. PRDs and acceptance tests for independent features also run in parallel. N comes from factory.json (suggest 3, hard cap 4). A short "parallel build" section goes into AGENT-ROUTING, plus a developer rule: stay in your owned files and report a needed cross-slice change instead of making it.
7. An ADR recording that mission approval deliberately relaxes decision 6 and the "no removing the PRD gate" non-goal of gated-autonomy.md, for one approved mission only.

## Non-goals
- Removing the PRD gate for normal work. With no active mission, nothing changes.
- Pushing or merging to main or production. The user promotes the mission branch.
- Changing protected paths, the acceptance-test lock or secrets rules.
- Letting the agent widen scope, raise caps or extend the mission itself.
- Creating schedules without opt-in.

## Acceptance criteria
1. Given no recorded mission, when the PM writes a PRD marked "by mission", then the guard and `prd` check reject it.
2. Given an active mission, when a PRD inside its scope is written, then it is accepted as approved by that mission.
3. Given an active mission, when a PRD is outside scope, then it is not approved, is listed as parked, and other items continue.
4. Given an expired or capped mission, when a PRD is written, then it is not approved by that mission.
5. Given an active mission with unblocked work left, when the main agent tries to end its turn, then the Stop hook blocks it and names the next item.
6. Given any cap is hit (budget, wall-clock or continuations), when the agent tries to end, then the hook allows it and the report states which cap.
7. Given everything is done or parked, when the agent tries to end, then the hook allows it.
8. Given an active mission, when work finishes or a cap stops it, then `docs/missions/<slug>-report.md` exists with all six report sections and appears on the dashboard.
9. Given a mission, when any step tries to push or merge to main or production, then it is blocked.
10. Given two parallel slices, when both are ready, then they merge one at a time, each after a passing gate; a stale base is rebased and re-gated.
11. Given a developer in a slice, when it edits a file it does not own, then it is blocked or flagged as a cross-slice request.
12. Given no active mission, when any hook or gate runs, then behaviour is identical to today (regression test).

## UX / behaviour notes
- The brief is short, plain words, and ends with "Reply go to start." Changes to scope need a new "go".
- The user can end a mission any time by setting it to stopped in the mission file; the hook then lets the agent finish.
- The morning report starts with a one-line verdict: done, done with parked items, or stopped at a cap.

## Risks and assumptions
1. **Weak self-approved PRDs** (riskiest): nobody reviews them. Mitigation: the test-writer's second reading and the gate run on each; PRDs record assumptions; the report lists them for review. Test early by running a small mission and reading the PRDs.
2. **Runaway cost:** caps are hard and read from metrics, not from the agent. Assumes token metrics are reliable enough; if not, fall back to the continuation cap.
3. **Scope creep through assumptions:** an assumption that adds a feature is out of scope and parked.
4. **A Stop hook loop that will not end:** every cap is checked first, and a hook test proves it ends.
5. **Merge conflicts:** file ownership, waves and serial gated merges; cap of 4 limits damage.
6. **Cloud container reclaimed overnight:** state lives in files and git, so a new session resumes. Auto-restart needs the opt-in watchdog.

## Effort and sequencing
Overall L. Build the riskiest, most valuable part first: the safe loop. Parallel build is independent and can follow.
- MISSION-1 (M) Mission file, brief template, "go" recording, ADR; guard and `prd` check accept a valid mission, with tests (criteria 1-4, 12).
- MISSION-2 (M) Stop hook with budget, time and continuation caps, with tests (5-7).
- MISSION-3 (S) Branch safety: no push or merge to main during a mission (9).
- MISSION-4 (S) Morning report and dashboard link (8).
- MISSION-5 (M) Parallel build: AGENT-ROUTING section, ownership map, developer rule, factory.json N (10, 11).
- MISSION-6 (S) Optional watchdog resume (opt-in).
First usable slice: MISSION-1 + 2 + 3 together.

## Open questions
1. **Default caps?** Recommend 15 USD, 10 hours and 40 continuations, all set in the brief and never raised by the agent.
2. **Watchdog in v1?** Recommend no. Ship MISSION-6 after the first real overnight run shows whether sessions die.
3. **Must the brief name each feature?** Recommend it may say "PM decides features" but must list a scope boundary and a maximum number of features (default 5). The PM's chosen feature list is shown in the report.

## Decisions (user, 2026-11-16)
1. Scope: MISSION-1 to MISSION-5 approved and built together; MISSION-6 (watchdog resume) stays planned, built after a first real overnight run.
2. Default caps: 15 USD, 10 hours, 40 continuations per mission; set in the brief, never raised by the agent.
3. The brief may say "PM decides features" but must give a scope boundary and a feature cap (default 5); the chosen list is in the report.

# PRD: Mission hardening (enforce the safety nets of overnight missions)

> Status: approved · 2026-11-16 · by user in chat ("Ok approved": all six, order 7, 9, 8, 10, 11, 12; recommendations on open questions accepted) · Owner: product-manager · Backlog: M4 — Mission autopilot / MISSION-7..12

## Problem
Mission autopilot (docs/specs/mission-autopilot.md) builds overnight from one approved brief, and nobody reviews the PRDs it approves. An architect review fixed the bugs, but six safety nets are still only written rules or have gaps: tests-before-build is not enforced, the hook nags about work already in progress, branch safety ends too early, the feature cap can be gamed, caps are not bounded, and spend is counted in two places.

## Goal and success measure
Serves GOAL "autonomous work, user stays in charge" (gated-autonomy.md). Success: the first real mission cannot exceed its brief (scope, caps, branch) and a weak PRD cannot reach code without admitted tests.

## Users and user stories
- As a PM, I want tests approved before any code in a mission so unreviewed PRDs still have a safety net.
- As a PM, I want "main" protected for the whole night, even after the mission ends early.
- As a PM, I want the numbers in the brief to be hard limits, including all spend.

## Scope (build order 7, 9, 8, 10, 11, 12; first slice = 7 + 9 + 8)
- **MISSION-7 (M)** At rigor L2+, product writes for a by-mission PRD are refused until `acceptance.py admit` has admitted tests for that slug. Ambiguity becomes a written assumption, or the item is parked.
- **MISSION-9 (S)** Push/merge to main stays blocked until the mission's time window ends, even if it is done or stopped. `autonomy.staging_branch` is protected too.
- **MISSION-8 (S)** If every open item is held by a background developer, the Stop hook says "wait or land" (not "start <same item>"). Such waits do not use up continuations; time and budget still bound them.
- **MISSION-10 (S)** The feature cap counts only live items (not parked or dropped). The chosen PRD list is frozen in the Decision log when each PRD is approved.
- **MISSION-11 (S)** Mission defaults (caps, feature cap, protected branches) live in the `mission` block of factory.json. `start` refuses caps above a ceiling set there.
- **MISSION-12 (M)** One budget: second-reading spend counts toward the mission cap, and `runner.py` is forbidden during a mission.

## Non-goals
- No sandbox for unattended mission developers now. They run with the session's network and credentials. Reason: costly to build, and a documented limit ("run missions in an ephemeral cloud session with scoped credentials") covers it. Revisit after the first real mission.
- No change to normal work, the PRD gate, or protected paths.
- MISSION-7 does not apply below L2.

## Acceptance criteria
1. (7) Given an active mission at L2+, when code is written for a by-mission PRD with no admitted tests, then the write is refused; after `admit` it is allowed.
2. (7) Given the test-writer cannot produce admissible tests, then the item is parked `[!]` with a reason and the mission continues.
3. (9) Given a mission with status done or stopped inside its time window, when a push or merge to main or the staging branch is tried, then it is blocked; after the window it is allowed.
4. (8) Given all open items are `[~]` and held by background developers, when the agent tries to end, then the hook says "wait or land" and the continuation count does not rise.
5. (10) Given parked or dropped items, then they do not count toward the feature cap; and a later backlog edit does not change the verdict of an already-approved PRD.
6. (11) Given a ceiling in factory.json, when `start` is run with a larger cap, then it refuses and names the ceiling.
7. (12) Given a mission, when second-reading runs, then its cost is added to mission spend; when `runner.py` is started, then it refuses.
8. Given no active mission, when any hook, gate or script runs, then behaviour is identical to today (regression test).

## UX / behaviour notes
Refusals say what to do next in plain words (for example "tests not admitted for <slug>: run the test-writer"). The morning report lists parked items and why.

## Risks and assumptions
1. **Riskiest: MISSION-7 stalls a mission** when tests cannot be admitted. Mitigation: park that item and carry on; the report lists it. Test early with a deliberately vague PRD.
2. A wait that never ends: still bounded by the time and budget caps.
3. Ceiling too low blocks a legitimate big mission: the user can edit factory.json outside a mission.
4. Branch safety still reads command text only (known limit); GitHub branch protection remains the real fence.

## Effort and sequencing
Overall M-L. Slice 1: 7 + 9 + 8 (biggest risk reduction). Slice 2: 10, 11, 12. No dependency on MISSION-6.

## Open questions
1. **Ceiling defaults?** Recommend 30 USD, 12 hours, 60 continuations, feature cap ceiling 8.
2. **Does MISSION-7 apply below L2?** Recommend no (no acceptance tests exist there).
3. **MISSION-12: forbid runner or count its spend?** Recommend forbid `runner.py` and count second-reading (simpler, one budget).
4. **Branch window length?** Recommend the mission's own hours cap, counted from start.
5. **Build a sandbox now?** Recommend no; document the limit and revisit after the first mission.

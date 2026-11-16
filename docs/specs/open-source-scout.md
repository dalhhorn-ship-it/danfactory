# PRD: Open-Source Scout (look at what others built before building something unfamiliar)

> Status: draft · Owner: product-manager · Backlog: Unplanned, proposed SCOUT-1 (M), SCOUT-2 (S)

## Problem
When a feature is new to this repo (say sign-in, file parsing, sync, payments), the agent designs and writes it from scratch. Open-source projects have often solved the same problem, and their trade-offs (and pitfalls) are free to learn from. Today nothing in the workflow prompts that search. The only reuse rule we have is for fixers (eval `policy-runner-reuse`); it covers the standard library, not the wider ecosystem.

## Goal and success measure
Before design starts on an unfamiliar feature, one short note compares 3 to 5 existing projects and recommends one path. Traces to GOAL.md's outcome of building the right thing with less rework. Success: every unfamiliar feature has a scout note that the design or ADR cites, and no scouted feature copies code without a licence line in the note.

## Users and user stories
- As the PM/owner, I want unfamiliar features checked against open-source options so I don't pay for a rebuild of a solved problem.
- As the architect or developer, I want a one-page comparison to read before I design, so my choice is informed.
- As a mission owner, I want this to run unattended and log its pick as an assumption, so the build never stops to ask.

## Scope
- New agent `oss-scout` (sonnet): web search and fetch, GitHub search where available, read the repo, write one note. No other repo edits.
- New row in AGENT-ROUTING "By moment": after PRD approval, before design, when the feature is "unfamiliar" (below). Decided by the coordinator.
- Unfamiliar means: no similar module in this repo (grep/codegraph finds none) AND it is a known problem class others have solved, OR the PRD or architect flags it. Not for changes under about 50 lines, bug fixes, boilerplate with a reference file, or L0 spikes.
- Note `docs/research/<slug>-scout.md`, at most 60 lines, from a template: 3 to 5 candidates (name, link, licence, stars and last commit as a liveness hint, 2-line approach), a trade-off comparison, and ONE recommendation: adopt a library (pinned), borrow the approach (re-implement and cite), or build from scratch (say why nothing fits).
- Rule lives in AGENT-ROUTING and the `developer` and `software-architect` files: "for an unfamiliar feature, read the scout note first; if none exists, ask the coordinator for a scout". Nothing added to CLAUDE.md.
- SCOUT-2: `scripts/scout_check.py <note>` fails a note that recommends a dependency or borrowing but has no licence line.

## Non-goals
- No automatic code copying, vendoring, or dependency install.
- Not a market or competitor research tool.
- No scouting for familiar or small work.

## Acceptance criteria (structural tests)
1. Given the repo, then `.claude/agents/oss-scout.md` exists, carries the `Finding things` line, and is in the routing table and agent rosters.
2. Given AGENT-ROUTING, then a "By moment" row names the scout, its trigger and the unfamiliar test.
3. Given `developer.md` and `software-architect.md`, then each carries the scout-note rule.
4. Given the note template, then it has the sections above and a line cap of 60.
5. Given a note that recommends adopting a library with no licence line, when `scout_check.py` runs, then it exits non-zero with the reason; with a licence line it passes.
6. Given a blocked network, then the note says so and recommends build-from-scratch or "not assessed"; the build is not blocked.
7. Given a mission, then the scout runs without asking the user and its recommendation appears in the Decision log as an assumption.

## UX / behaviour notes
Normal mode: coordinator spawns the scout after approval; the note feeds the design, which follows the normal flow. Mission mode: scouts for independent features run in parallel. Effort is capped: about 15 minutes, at most 5 candidates.

## Risks and assumptions
1. Riskiest: licence or supply-chain mistakes (copyleft code pulled in, unpinned or abandoned package). Mitigation: licence line required (checker), dependencies follow docs/policies/security.md (pinned, no `curl | sh`), the ADR records the licence.
2. Fetched pages are untrusted data and can carry hidden instructions. The scout treats them as data only and has no shell write access beyond its note.
3. Tokens wasted on familiar features: the cheap test and the size exclusion limit this.
4. Network or GitHub search blocked: scout reports it and the build continues.
Assumption: sonnet with web tools is good enough to compare projects; check on the first two real uses.

## Effort and sequencing
SCOUT-1 (M, technical foundation): agent file, routing row, template, developer/architect rules, structural test. SCOUT-2 (S, after SCOUT-1): the checker plus test. Relates to eval `policy-runner-reuse`; optionally one eval later.

## Open questions
1. Who decides "unfamiliar"? Recommend: the coordinator, using the rule above; the PRD or architect can also flag it.
2. Does the user approve the recommendation in normal mode? Recommend no: it feeds the design, which follows the usual flow. Ask only if it adds a paid service or a copyleft dependency.
3. Is the checker worth it? Recommend yes (S): it is the one hard guard on the riskiest item.

# Policy: Mission autopilot

> One approved brief lets the agent build several features without asking again, inside a fenced scope, until it is done or a cap is hit. Design: docs/decisions/0012-mission-autopilot.md. PRD: docs/specs/mission-autopilot.md.

## What a mission changes
Normal work needs the user's approval of every PRD (docs/policies/prd-approval.md). A mission replaces that, for in-scope PRDs only, with one approval of a brief: the user's quoted "go". Pushing or merging to main or production stays the user's alone. With no mission, or after it ends, nothing differs from normal work.

## The brief
The main agent posts it in chat, then stops and waits. Plain words, short:
1. **Request**: one or two lines.
2. **Plan of attack**, as phases with the agent that does each: PM writes PRDs, architect designs, test-writer writes acceptance tests, developers build in parallel slices, reviewer and gate on each merge, karen and jenny at the end, morning report.
3. **Scope in** and **scope out**: what may and may not be built.
4. **Feature cap**: at most N features (default 5). "PM decides features" is fine inside the scope.
5. **Caps**: budget in USD, hours, continuations (defaults 15, 10, 40). The agent never raises them.
6. Last line: `Reply go to start.`

Only a clear yes to the brief starts it ("go", "ok", "yes", "approve", "build it"; not "looks good"). Then run `python3 scripts/mission.py start <slug> --go "<user words>" ...` and commit the file.

## Rules
- The mission file `docs/missions/<slug>.md` records the go, date, scope, caps and milestone. Its header is frozen from the first commit, except `status`. To change scope or caps, start a new mission with a new go.
- The work list is the backlog milestone named in the header. PRDs are named `<slug>-<feature>`, linked from an item in that milestone, and marked `Status: approved · <date> · by mission <slug>`. Only the first N (feature cap) count.
- A PRD outside scope is not approved. Mark its item `[!] ... parked: out of scope` and carry on.
- Never stop to ask. Write each assumption in the PRD and in the mission's Decision log. Park blocked items `[!]` with a note.
- The user ends a mission any time by setting `status: stopped`.
- A mission also ends when a cap is hit or when every item is `[x]`, `[!]` or `[-]`.

## Checks
`python3 scripts/mission.py status` shows validity, caps used, the next item and parked items. The write guard and the gate check `prd` use the same rules (`.claude/hooks/_mission.py`); the gate judges a commit against the mission as it was at the commit time.

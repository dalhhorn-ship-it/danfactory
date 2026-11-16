# Policy: Mission autopilot

> One approved brief lets the agent build several features without asking again, inside a fenced scope, until it is done or a cap is hit. Design: ADR 0012 in the danfactory template (bootstrap removes it from new projects).

**Terms.** *Mission* = one approval for a multi-feature build (base, always installed). *Autonomy mode* = the fixer runner on issues (`scripts/runner.py`, the optional autonomy pack). They are separate.

## What a mission changes
Normal work needs the user's approval of every PRD (docs/policies/prd-approval.md). A mission replaces that, for in-scope PRDs only, with one approval of a brief: the user's quoted "go". Pushing or merging to main or production stays the user's alone. With no mission, or after it ends, nothing differs from normal work.

## The brief
The main agent posts it in chat, then stops and waits:
1. **Request**: one or two lines.
2. **Plan of attack**, as phases: PM writes PRDs, architect designs, test-writer writes acceptance tests (L2+), developers build in parallel slices, `slices.py land` gates each merge, the coordinator runs `reviewer` per feature, karen and jenny at the end (L2+), morning report.
3. **Scope in** and **scope out**.
4. **Feature cap**: at most N features (default 5). "PM decides features" is fine inside the scope.
5. **Caps**: USD, hours, continuations (defaults 15, 10, 40). The agent never raises them.
6. Last line: `Reply go to start.`

Only a clear yes starts it ("go", "ok", "yes", "approve", "build it"; not "looks good").

## Start
Preconditions: `factory.json` phase is `build` and the tree is clean. First add a backlog milestone for the mission's items: the next free number after the highest, `## Milestone: M<n> — <title>`. Then run `python3 scripts/mission.py start <slug> --go "<user words>" --title T --scope-in S --scope-out S --milestone M<n> [--features N --usd N --hours N --continuations N] [--brief TEXT] [--branch NAME]`. It creates and switches to branch `mission/<slug>` (or NAME); commit the mission file there. The Stop hook only continues on that branch and says so elsewhere. Caps are not checked against the brief: the report prints them next to the go words, so check.

## Flow per feature
1. PM writes PRD `<slug>-<feature>`, `Status: approved · <date> · by mission <slug>`; the item goes `[~]`.
2. At L2+, before any build: test-writer, second reading, `acceptance.py admit`.
3. Architect designs, with a slice table; developers build in parallel; `slices.py land` gates each merge (docs/operating-model/AGENT-ROUTING.md, Parallel build).
4. Coordinator runs `reviewer`; at the end karen and jenny at L2+, then the report.

## Rules
- The mission file `docs/missions/<slug>.md` records go, date, scope, caps, milestone. Its header is frozen from the first commit, except `status`. To change scope or caps, start a new mission with a new go.
- Work list = the milestone. Only the first N PRDs (feature cap) count. A PRD outside scope is not approved: mark its item `[!] ... parked: out of scope`.
- Never stop to ask. Assumptions go in the PRD revision and the mission's Decision log, or park the item `[!]`. This includes test-writer ambiguities and `fails-on-reference`: they are not sent to the user.
- Mission work cannot change the factory's own controls (`factory.json`, `.claude/**`, gate, mission, runner and acceptance scripts): park such items. The write guard enforces it while a mission with `status: active` has its branch checked out, whatever the backlog or exemptions say; it ends when the mission is stopped or done (`mission.py stop <slug>`; the mission file stays editable). (`MISSION_PROTECTED` in `.claude/hooks/_prd.py`, also `.github/**`, `scripts/slices.py`, `scripts/check.sh`, `.factory/prd-exemption`).
- `mission.py report <slug>` regenerates the report and never changes the status; `mission.py stop <slug>` stops the mission and writes the report. Off the mission branch the Stop hook does not continue and says so.
- A mission does not start `scripts/runner.py`. Runner budgets (`autonomy.*`) and `schedule_ok` do not apply to missions; known limit: second-reading cost books against `autonomy.daily_budget_usd`, not the mission cap.
- The user ends a mission by setting `status: stopped`. It also ends at a cap or when every item is `[x]`, `[!]` or `[-]`.

## Checks
`python3 scripts/mission.py status` shows validity, caps used, next item, parked items. The write guard and gate check `prd` share one rule set (`.claude/hooks/_mission.py`); the gate judges a commit against the mission at commit time. An invalid mission (header changed, no real go, no `started_at`, not committed, shallow clone that cannot prove the frozen header) counts as stopped. `slices.py land` refuses protected `--into` branches during a mission.

## Honest limits
- The slug-prefix scope rule is easy to satisfy; the PM still judges meaning, and the report lists the chosen PRDs.
- `--gate-cmd` needs `SLICES_TEST_GATE=1`, which an agent can set: a speed bump. The real gate runs on the promotion PR in CI.
- The go quote is written by the agent: check it in the report against the chat. Commit times can be set, so the historical window check makes misuse visible, not impossible.
- `.factory/mission-state.json` is tracked: counters are monotonic only against HEAD; a committed reset is not seen.
- Branch safety reads command text only; `symbolic-ref`, `update-ref`, scripts, aliases and `gh api` are not seen. `autonomy.staging_branch` is not protected by it. `gh pr create --base main` is allowed (opening a PR is not merging). Real protection: GitHub branch protection and scoped credentials.
- Mission developers run in the session's own environment, not the runner's sandbox: run missions in an ephemeral cloud session with scoped credentials (docs/policies/security.md).

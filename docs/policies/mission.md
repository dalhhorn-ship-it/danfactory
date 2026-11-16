# Policy: Mission autopilot

> One approved brief lets the agent build several features without asking again, inside a fenced scope, until it is done or a cap is hit. Design: ADR 0012 in the danfactory template (bootstrap removes it from new projects).

**Terms.** *Mission* = one approval for a multi-feature build (base, always installed). *Autonomy mode* = the fixer runner on issues (`scripts/runner.py`, the optional autonomy pack). They are separate, but a mission blocks the runner (below).

## What a mission changes
Normal work needs the user's approval of every PRD (docs/policies/prd-approval.md). A mission replaces that, for in-scope PRDs only, with one approval of a brief: the user's quoted "go". Pushing or merging to main or production stays the user's alone. With no mission, or after it ends, nothing differs from normal work (except branch safety, see Window).

## The brief
The main agent posts it in chat, then stops and waits:
1. **Request**: one or two lines.
2. **Plan of attack**, as phases: PM writes PRDs and runs `mission.py approve`, architect designs, test-writer admits acceptance tests (L2+), developers build in parallel slices, `slices.py land` gates each merge, the coordinator runs `reviewer` per feature, karen and jenny at the end (L2+), morning report.
3. **Scope in** and **scope out**.
4. **Feature cap**: at most N features (default 5, ceiling 8). "PM decides features" is fine inside the scope.
5. **Caps**: USD, hours, continuations. Defaults and ceilings are in factory.json `mission` (defaults 15 / 10 h / 40 / 5 features; ceilings 30 / 12 h / 60 / 8). The agent never raises them.
6. Last line: `Reply go to start.`

Only a clear yes starts it ("go", "ok", "yes", "approve", "build it"; not "looks good").

## Start
Preconditions: `factory.json` phase is `build` and the tree is clean. First add a backlog milestone for the mission's items: the next free number after the highest, `## Milestone: M<n> — <title>`. Then run `python3 scripts/mission.py start <slug> --go "<user words>" --title T --scope-in S --scope-out S --milestone M<n> [--features N --usd N --hours N --continuations N] [--brief TEXT] [--branch NAME]`. It refuses a cap above its ceiling. It creates and switches to branch `mission/<slug>` (or NAME); commit the mission file there. The Stop hook only continues on that branch and says so elsewhere. Caps are not checked against the brief text: the report prints them next to the go words, so check.

## Approval and scope
- After writing a mission PRD, the PM (or coordinator) runs `python3 scripts/mission.py approve <slug> <spec-slug>`. It appends `- <date> Approved PRD: <spec-slug>` to the mission's Decision log.
- Only specs listed that way are in scope. Later backlog edits do not change the list. Hand-editing the log skips `approve`'s cap check; only the ceiling bounds that.
- `approve` needs the slug prefix, a live item under the milestone that links the spec, and room under the feature cap. The cap counts live items only (`[ ]`, `[~]`, `[x]`); a parked `[!]` or dropped `[-]` item frees its place.
- A PRD not listed is out of scope. `mission.py status` lists it as parked with the reason (not approved yet, or over the feature cap).

## Flow per feature
1. PM writes PRD `<slug>-<feature>`, `Status: approved · <date> · by mission <slug>`, runs `approve`. At L2+ the item stays `[ ]` until its tests are admitted (`tests/acceptance/**` is writable meanwhile), then goes `[~]`.
2. Unfamiliar feature (AGENT-ROUTING, Scout open source): `oss-scout` first, its pick logged in the Decision log as an assumption; scouts for independent features run in parallel.
3. At L2+, before any build: test-writer, second reading, `acceptance.py admit` (below).
4. Architect designs, with a slice table; developers build in parallel, `slices.py land` gates each merge; coordinator runs `reviewer`; at the end karen and jenny at L2+, then the report (docs/operating-model/AGENT-ROUTING.md, Parallel build).

## Tests before code (L2+)
- Rigor is factory.json `rigor` (choose-path writes it), else the first `L<n>` in the OPERATING-MODEL "Path and rigor" section; unknown counts as L2 in a mission, and `start` refuses an unknown rigor. Only an explicit L0/L1 turns tests-before-code off. At L2+ product writes are refused while ANY in-progress by-mission PRD has no admitted tests. During a mission only by-mission PRDs listed by `approve` open product writes. The acceptance manifest is protected: only `acceptance.py admit` writes it.
- The gate fails the commit with `mission-tests-not-admitted` when `gate.prd` is `required`. This template sets `advisory`, so there it warns.
- If no admissible tests can be written, park the item `[!]` with `parked: <why>`; the report lists it.

## Stop hook and waits
- While every open item is `[~]` and a slice worktree is out (a worktree other than this checkout, on a branch that is not the mission's), the Stop hook says "Developers are still working on …; wait or land" and does not count a continuation. It waits at most 6 times in a row. Caps are checked first.
- Remove finished worktrees after landing, or they count as work in hand. A `[ ]` item present means plain work.

## Window, budget and runner
- Branch safety applies while the mission is active and until its window ends (started_at + hours cap, read from the mission file's first commit, so editing or deleting the file does not shorten it), even if it is done or stopped. Until then push, merge and checkout of main, master, production, the base and staging branches are refused. The user can push from their own terminal.
- Budget: second-reading spend since the mission start counts toward the mission USD cap. `runner.py run` refuses (exit 2) while a mission is active.

## Rules
- The mission file `docs/missions/<slug>.md` records go, date, scope, caps, milestone. Its header is frozen from the first commit, except `status`. To change scope or caps, start a new mission with a new go.
- Never stop to ask. Assumptions go in the PRD revision and the mission's Decision log, or park the item `[!]`. This includes test-writer ambiguities and `fails-on-reference`: they are not sent to the user.
- Mission work cannot change the factory's own controls (`factory.json`, `.claude/**`, gate, mission, runner and acceptance scripts): park such items. The write guard enforces it while a mission with `status: active` has its branch checked out, whatever the backlog or exemptions say; it ends when the mission is stopped or done (`mission.py stop <slug>`; the mission file stays editable). (`MISSION_PROTECTED` in `.claude/hooks/_prd.py`, incl. docs/OPERATING-MODEL.md, also `.github/**`, `scripts/slices.py`, `scripts/check.sh`, `.factory/prd-exemption`).
- `mission.py report <slug>` never changes the status; `mission.py stop <slug>` stops and writes the report. The user ends a mission by setting `status: stopped`; it also ends at a cap or when every item is `[x]`, `[!]` or `[-]`. Off the mission branch the Stop hook does not continue.

## Checks
`python3 scripts/mission.py status` shows validity, caps used, next item, parked items. The write guard and gate check `prd` share one rule set (`.claude/hooks/_mission.py`); the gate judges a commit against the mission at commit time. An invalid mission (header changed, no real go, no `started_at`, not committed, shallow clone that cannot prove the frozen header, a cap above its ceiling) counts as stopped. `slices.py land` refuses protected `--into` branches during a mission.

## Honest limits
- The PM still judges meaning of scope; the report lists the approved PRDs.
- `--gate-cmd` needs `SLICES_TEST_GATE=1`, which an agent can set: a speed bump. The real gate runs on the promotion PR in CI.
- The go quote is written by the agent: check it in the report against the chat. Commit times can be set, so the historical window check makes misuse visible, not impossible.
- `.factory/mission-state.json` is tracked: counters are monotonic only against HEAD; a committed reset is not seen.
- An exemption line dated before the mission started still opens writes that day, and skips the admission refusal. The agent cannot add one during a mission.
- The write guard lets writes through when any in-progress PRD has admitted tests, even if another does not.
- The admission check uses the current rigor, not the rigor at the time of the commit. `rigor` and the ceilings can be changed before a mission starts (the report prints rigor-relevant caps and ceilings: check them against the brief). The manifest records no content hash; the acceptance-test lock (gate `protected`) covers later edits.
- Any leftover worktree counts as "held", finished or not.
- Branch safety reads command text only: `symbolic-ref`/`update-ref` are checked by name, and scripts, aliases, `gh api` and the GitHub web UI are not seen. `gh pr create --base main` is allowed (opening a PR is not merging). Real protection: GitHub branch protection and scoped credentials.
- Mission developers run in the session's own environment, not the runner's sandbox: run missions in an ephemeral cloud session with scoped credentials (docs/policies/security.md).

# 0012 — Mission autopilot: one approved mission, a Stop-hook loop, parallel slices

> Status: accepted · Date: 2026-11-16 · PRD: docs/specs/mission-autopilot.md (MISSION-1..5, approved by user in chat 2026-11-16)

## Context
Every PRD needs the user's "approve" in chat (ADR 0002), so a long build stops at each feature and can't run overnight. Build mode also runs one developer at a time, and "parallel slices" has no ownership or merge rule. What the code shows: `_prd.prd_status` reads only the first Status word, so a `by mission` line would already count as approved today (criterion 1 needs a change there). `record_tokens.py` runs only at SessionEnd and is skipped in the template, and the repo has weights but no USD price table. The gate runs check.sh, which runs `docs_index.py --check`, so a slice that adds a doc fails its gate unless docs/INDEX.md is regenerated. Project Stop hooks run alongside the cloud environment's own Stop hook, and a missing hook script exits 2, which Claude Code reads as "block".

## Options
1. **Approval.** (a) A mission file holding the user's quoted "go" approves in-scope specs, using the same `_prd` rules in guard and gate. (b) A daily `waiver` per feature: no scope, cap or expiry. (c) The user approves each PRD before leaving: safe, but defeats the goal. **Chosen: (a).**
2. **Scope check.** (a) Mechanical: the spec slug has the prefix `<mission>-`, it is linked from the mission's backlog milestone, and it is within the feature cap. (b) A free `scope:` glob: the agent picks the names anyway. (c) Semantic only: can't be tested. **Chosen: (a).** The PM still judges meaning against scope_in/scope_out and parks what doesn't fit.
3. **Work list.** (a) A backlog milestone named in the header: one source of truth that is already on the dashboard. (b) A `## Work` list in the mission file: duplicates backlog state. **Chosen: (a).**
4. **Spend mid-session.** (a) The Stop hook re-sums the live transcript with a small price table, keyed by session id in the state file. (b) metrics/tokens.jsonl: written only at SessionEnd and skipped in the template. **Chosen: (a)**, with the continuation cap as the backstop.
5. **State file.** (a) `.factory/mission-state.json`, tracked: it survives a reclaim with the next commit, and CI and the report can read it. (b) Git-ignored: a clean tree, but the counters reset in a new container. **Chosen: (a).**
6. **Landing slices.** (a) `scripts/slices.py land`, one command that can be tested (criterion 10). (b) Manual steps from AGENT-ROUTING. **Chosen: (a).** The runner's `land` is pack-only (ADR 0011), so it is not reused.

## Decision
### The PRD gate is relaxed for one approved mission only
Mission approval deliberately relaxes decision 6 of docs/specs/gated-autonomy.md ("the user approves every PRD") and its non-goal "Removing the PRD gate", for one approved mission only. The user's quoted "go" on a brief (scope boundary, feature cap, hard caps) approves the PRDs the PM writes inside that scope, up to the feature cap, until the mission ends or hits a cap. Nothing else changes: with no mission, or after it ends, behaviour is today's (criterion 12); the agent can't widen scope or raise caps (the header is frozen); pushing or promoting to main stays the user's alone, so that half of decision 6 holds in full. ADR 0002 stays in force for all other work.

### Mission file `docs/missions/<slug>.md` (MISSION-1)
The slug matches `[a-z0-9][a-z0-9-]*` and doesn't end in `-report`. `_TEMPLATE.md` holds the brief. The header sits between `<!-- mission:start -->` and `<!-- mission:end -->`, one `key: value` per line:
`slug`, `status` (active|stopped|done; the user sets `stopped` to end it), `go` (the user's words in straight or curly quotes), `date`, `started_at` (UTC ISO, `Z`), `branch` (`mission/<slug>`), `milestone` (e.g. `M5`), `features` (default 5), `caps: usd=15 hours=10 continuations=40`, `scope_in`, `scope_out`. The body has `## Brief` (as posted) and `## Decision log` (`- YYYY-MM-DD Assumption: ...` / `Parked: ...`).
- `python3 scripts/mission.py start <slug> --go "<words>" --title T --scope-in S --scope-out S --milestone M5 [--features --usd --hours --continuations]` writes the file and adds `## Milestone: M5 — T (mission: <slug>)` to docs/BACKLOG.md. It refuses while another mission is active.
- `status [<slug>]` prints validity, caps used, the next item and parked items. `stop <slug>` and `report <slug>` complete the CLI.

**Valid** (`validate`): the header is complete; `go` is quoted and contains the word "go" (the brief ends "Reply go to start", so "ok" alone is not a go); `date` is the date of `started_at`, not in the future; the file is committed and every key except `status` equals its first commit (`git log --diff-filter=A`), so a scope or cap change needs a new mission and a new go.

**Live** (write guard): valid, `status: active`, now < started_at + hours, and no cap hit. **Historical** (gate, with `at` = the commit time): valid, any status, and started_at ≤ at ≤ started_at + hours.

**State** lives in `.factory/mission-state.json` (tracked, written atomically; a different slug resets it): `{"slug","continuations","sessions":{"<session_id>":usd},"ended":null|{"reason","ts"}}`.

### Approval in the guard and the `prd` gate check
A spec counts as approved by mission `m` when both hold:
- Its Status line reads `> Status: approved · <date> · by mission <m>`.
- `approval(root, m, spec, at)` passes: the mission is valid (live, or historical at the commit time), the slug starts with `<m>-`, it is linked from an item under the mission milestone, and it is among the first `features` distinct such slugs in file order.

Otherwise `_prd.prd_status(root, slug, at=None)` returns `unapproved`. `item_approved(root, ref, at=None)` passes `at` through. `_c_prd` reads commit times with one `git log --format='%H %ct'` call and adds a note `covered by mission <m> (go: "...")`. `_mission` is imported only when a Status line says `by mission`, so every other spec takes exactly today's code path.

An out-of-scope spec is not approved. `parked()` lists it, together with the milestone's `[!]` items, for `mission.py status`, the Stop hook and the report. The PM marks it `[!] ... parked: out of scope` and the loop moves on.

### Stop hook `.claude/hooks/mission_stop.py` (MISSION-2)
1. **No-op cases.** Exit 0 with no output and no writes when there is no active mission, when HEAD is not the mission branch (headless runs, other checkouts), or when `state.ended` is already set.
2. **Spend.** Re-sum this session's transcript plus `subagents/*.jsonl` with `record_tokens.summarize`. USD = Σ weighted tokens per model × the input price per million tokens (opus 5, sonnet 3, haiku 1; unknown models get the highest). The result is stored under the session id, and the mission total is the sum over sessions. If the transcript can't be read, spend is unknown: the report says so and the continuation cap still binds.
3. **Caps first, in this order:** status not active (the user stopped it), wall-clock, budget, continuations (a cap is hit at `>=`). On a hit: set `state.ended`, call `mission_report.write` (which sets status `stopped`), and allow the stop with a `systemMessage` naming the cap.
4. **Remaining work.** `next_item` returns the first `[~]` item, else the first `[ ]`. An empty milestone gives a PLAN step: the PM picks up to `features` items within scope. If nothing is left (every item is `[x]`, `[!]` or `[-]`): set `ended: done`, write the report (status `done`), and allow the stop.
5. **Otherwise block.** Add 1 to continuations, save the state, and print `{"decision":"block","reason":"Mission <m> (n/40, $x/15, h/10h). Next: <ID> <title>. Don't ask the user: write assumptions in the PRD and the Decision log, park blocked items [!] with a note, commit after each item."}`. `stop_hook_active` is ignored: the continuation counter is what ends the loop.
6. **Errors.** Any internal error allows the stop, because stopping is the safe direction.
7. **Registration.** In .claude/settings.json `Stop`: `f="$CLAUDE_PROJECT_DIR/.claude/hooks/mission_stop.py"; [ -f "$f" ] && python3 -B "$f" || true`, so a missing file can't exit 2. Claude Code runs every matching Stop hook, including the cloud environment's, and any one block continues the turn. Ours doesn't need to know about the other.

### Branch safety (MISSION-3)
`.claude/hooks/_gitmission.py` `check(prog, args, cwd) -> str` returns a reason or `''`. `guard_bash_policy.py` calls it for `git` and `gh`, only while `_mission.active()` returns a mission. Protected branches: main, master, `integrations.deploy.production_branch` and `gate.base_branch`. Blocked: `git push` whose destination is protected (the part after `:`, without `+` or `refs/heads/`; a bare push or `HEAD` means the current branch), and `--all`/`--mirror`; `checkout`, `switch` or `worktree add` onto a protected branch; `branch -f`/`-M` or `update-ref` on one; `commit`, `merge`, `pull`, `rebase`, `cherry-pick`, `revert`, `am` or `reset` while HEAD (of the `-C` dir or the cwd) is protected; `gh pr merge`. Honest limits: git called by scripts or generated programs, aliases, `gh api` and the web UI are not seen. The real protection is GitHub branch protection plus credential scoping (ADR 0003).

### Morning report (MISSION-4)
`scripts/mission_report.py` `write(root, slug, reason) -> str` returns the path of `docs/missions/<slug>-report.md` and sets the header status. The report opens with a verdict line (done / done with parked items / stopped at <cap>), followed by six sections: `## Shipped` (the `[x]` items and the chosen feature list), `## Assumptions` (from the Decision log), `## Parked`, `## Cost` (USD per session, against the caps), `## Time` (start, end, hours) and `## Gate verdicts` (rows of metrics/gate.local.jsonl since the start). The report is derived from files and git, so `mission.py report` can regenerate it at any time. A new `scripts/obs/tab_missions.py` (`collect`, `line`, `render`) plus one TABS entry in dashboard.py shows the latest mission, its verdict and the report path (as a GitHub link when `dashboard.github_repo` is set).

### Parallel build (MISSION-5, all modes)
A design lists its slices in a table `| Slice | Owns | Wave | Depends on |`. Extra columns are ignored; Owns holds backticked paths or globs. The coordinator runs up to factory.json `build.max_parallel` developers per wave (default 3; values above 4 count as 4), each with `Agent isolation: "worktree"` and one branch per slice. Slices land one at a time with `python3 scripts/slices.py land <branch> --map <design.md> --slice <id> --into <integration>`, which runs: (1) `check`, which lists files in `into...branch` outside Owns as cross-slice requests and exits 1; (2) a rebase if the integration tip moved; (3) `docs_index.py`, committing any change; (4) `gate.py --base <into>`; (5) `merge --ff-only`. A failed rebase or gate means the slice is not merged, and the reason is reported. Slices never commit docs/INDEX.md or docs/knowledge-graph.json. PRDs and acceptance tests for independent features run in parallel the same way. AGENT-ROUTING gets a "Parallel build" section. developer.md gets this rule: "edit only your owned paths; for any other change reply `PARTIAL — cross-slice request: <path>: <change>`".

### Build slices for this work
| Slice | Owns | Wave | Depends on | Criteria |
|---|---|---|---|---|
| A approval | `.claude/hooks/_mission.py`, `.claude/hooks/_prd.py`, `scripts/gate_checks.py`, `scripts/mission.py`, `docs/missions/_TEMPLATE.md`, `docs/policies/mission.md`, `docs/policies/prd-approval.md`, `docs/policies/merge-gate.md`, `.claude/agents/product-manager.md`, `.factory/tests/test_mission_approval.py` | 1 | – | 1-4, 12 |
| B loop | `.claude/hooks/mission_stop.py`, `.claude/hooks/_gitmission.py`, `.claude/hooks/guard_bash_policy.py`, `.claude/settings.json`, `.factory/tests/test_mission_stop.py`, `.factory/tests/test_mission_branch.py` | 1 | A (lands after) | 5-7, 9, 12 |
| C report | `scripts/mission_report.py`, `scripts/obs/tab_missions.py`, `scripts/dashboard.py`, `scripts/slices.py`, `factory.json`, `docs/operating-model/AGENT-ROUTING.md`, `.claude/agents/developer.md`, `.claude/agents/software-architect.md`, `.factory/tests/test_mission_report.py`, `.factory/tests/test_slices.py` | 1 | A (lands after) | 8, 10, 11, 12 |
| coordinator | `CLAUDE.md` (one line), `docs/BACKLOG.md`, `docs/INDEX.md`, `docs/knowledge-graph.json`, `docs/TECH-DEBT.md` | 2 | A, B, C | – |

**How the slices run.** All three start at once and land in the order A, B, C; `slices.py` doesn't exist yet, so the coordinator lands them by hand (rebase, regenerate the index, gate, fast-forward). B and C code against the API below with an untracked local stub of `_mission.py` that they never commit; their tests build real mission files in temp git repos, so they pass against A's module after the rebase. B imports `mission_report` inside a try (if it is missing, the systemMessage says to run `mission.py report`). Criterion 12 regression: test_prd_guard.py and test_guard_security.py pass unchanged.

`_mission` public API (slice A; stdlib only; no-ops and `None` when docs/missions/ is absent):
```
MISSIONS_DIR = "docs/missions"; STATE_FILE = ".factory/mission-state.json"
DEFAULTS = {"features": 5, "usd": 15.0, "hours": 10.0, "continuations": 40}
load(root, slug) -> dict | None      # slug,title,status,go,date,started_at(aware dt),branch,milestone,features,caps{usd,hours,continuations},scope_in,scope_out,path
active(root) -> dict | None          # the earliest-started mission with status active
validate(root, m) -> str             # '' or the reason it is invalid
go_valid(quote: str) -> bool
expires_at(m) -> datetime.datetime
load_state(root, slug) -> dict;  save_state(root, state) -> None
cap_hit(m, state, now=None) -> str   # '' | 'stopped' | 'wall-clock' | 'budget' | 'continuations'
items(root, m) -> list               # [{id, title, state(' ','~','x','!','-'), slugs}] under the milestone
next_item(root, m) -> dict | None    # None = all closed; {"id": "PLAN", ...} when the milestone is empty
in_scope(root, m, spec) -> bool;  parked(root, m) -> list   # [{ref, why}]
approval(root, mission_slug, spec, at=None) -> tuple        # (ok, why); at=None live, datetime historical
mission_of(status_line: str) -> str; set_status(root, slug, status) -> None
```

## Consequences
- **Easier:** an overnight run of 3 to 5 features ends with a report and a branch to review. Parallel slices have owners and serial gated merges.
- **Harder:** the approval rules now cover two cases, user and mission. One more hook runs at every turn end, but it exits early with no mission. The state file is a tracked file that changes often.
- **Tests:** each new test file runs in under 3 s, using temp git repos and hook subprocesses (the `Proj` pattern in test_prd_guard.py), with no network or model. The inner loop runs the file directly (`python3 -m unittest .factory/tests/test_mission_*.py`); the full suite runs with `python3 scripts/metrics.py test` and stays under `budgets.test_seconds` (120).
- **Spike S1 (1 h, before B lands):** in a cloud session, check that a project Stop hook's block continues the turn next to the environment's hook, that transcript usage is current mid-session and survives compaction, and that the tracked state file doesn't loop the environment's "uncommitted changes" hook.
- **Spike S2 (1 h, before B lands):** compare the transcript estimate with `total_cost_usd` from `claude -p --output-format json` and tune the prices. If it is off by more than 30%, the budget cap is advisory, the continuation cap is the hard limit, and TECH-DEBT says so.
- **Accepted limits:** the go quote is self-asserted, like a waiver, but shows in git, the gate note and the report. Commit dates can be set by the agent, so the gate's historical check makes misuse visible, not impossible. A user message mid-mission gets a forced continuation (set `status: stopped` to end). The dashboard's spec parsers still show mission specs as "approved".
- **Measure:** whether the mission reaches done or a cap with zero prompts, continuations used, estimated vs real cost, and failed merges per wave.

# Learnings

> Append-only log written by `retro`. Each entry tags path(s) and a type; `[upstream]` entries should be copied back to the template repo.

Entry format:

```
### YYYY-MM-DD — short title  [path] [type] [upstream?]
What happened (1–2 lines, with metric if any). What we changed (file). Expected effect.
```

Types: `[practice]` `[tree-gap]` `[budget]` `[tooling]` `[anti-pattern]` `[security]` `[deploy]`

## Entries

### 2026-11-06 — Cloudflare credential mix-ups  [software-product] [deploy] [upstream]
Smoke test deployed and verified /version in 5s, after two credential mix-ups: an R2 access key instead of an API token (code 9109), then a Zone ID as CLOUDFLARE_ACCOUNT_ID (code 10000). Docs now say: API token from the "Edit Cloudflare Workers" template; account ID optional, never a Zone ID. Clue for next time: in the log, a correct secret is masked as *** everywhere, and an unmasked account ID means the secret differs.

### 2026-11-06 — Don't wait on deploys  [software-product] [deploy] [upstream]
Design choice from the template build (not yet measured): agents would idle while git/CI/Cloudflare builds ran. Now: push → background deploy-watcher (Haiku, bounded wait) → continue; test once on PR; skip docs-only builds; build cache; fast pre-push gate. Budget push-to-live 180s.

### 2026-11-06 — Delegate big reads by default  [all] [tooling] [upstream]
Seeded from the template, not yet measured here: Spotify reports 82–94% token savings from delegating large reads (shunt README benchmarks). Guard hook + bulk-reader subagent added. Verify with weighted tokens/session in metrics/REPORT.md after a few sessions.

### 2026-11-07 — Guards must match their promises  [all] [security] [upstream]
Audit run-1 (quick, source-only): the template's docs promised more than its code enforced (deploy "denied", secrets "read-denied", production environment as the gate). Regex command guards are advisory; real protection is credential scoping (no deploy key where the agent or PR code runs). Write security claims as "guarded" unless a credential boundary backs them, and treat adopted repos as untrusted filesystem input (symlinks, .git/config, hooks).

### 2026-11-07 — Background developer per slice  [all] [practice] [upstream]
M1 shipped in 3 approved slices, each built by a background `developer` while the main session stayed coordinator (Slice 3: ~3 min, ~57k subagent tokens, check.sh green first run). The user named this as what worked best. No routing change: AGENT-ROUTING already sends parallel/well-specified slices to `developer`. Keep doing it; brief each slice with PRD ACs, design doc and the prior slice's commits as the pattern.

### 2026-11-07 — Dashboard as a Claude artifact at a stable URL  [all] [tooling] [upstream]
Viewing the dashboard as a private artifact with a link that stays the same (republished v1→v3) was the other thing the user valued. Snag: in a new session the first republish is refused until the live version has been read; since the page is generated, nothing needs merging, so publish again unchanged. Added that note to .claude/skills/dashboard/SKILL.md.

### 2026-11-07 — Per-run records committed to git dirty the tree  [all] [anti-pattern] [upstream]
`check.sh` appended a row to committed metrics/records.jsonl on every run, so each check left the tree dirty and set off the stop hook (TD-008). Fixed in accce0c: frequent run records go to gitignored `*.local.jsonl` with dedupe; only rare, durable gate records (security audit) are committed. metrics/REPORT.md is now gitignored for the same reason. Rule: generated, per-run output never lives in tracked files.

### 2026-11-07 — Factory work before a project goal  [all] [tree-gap] [upstream]
M1 (dashboard observability) was improving the factory itself while phase was still `brainstorm` with no GOAL.md. The tree had no branch for this, and metrics stay empty until bootstrap: the token hook skips while project.name is empty and commands.test is unset, so the Flow, Cost and Tests views show n/a. DECISION-TREE.md 1.2.0 adds Q0b, pointing at template mode (built in parallel on main): template work skips brainstorm/choose-path but keeps the PRD gate; expect no product metrics.

### 2026-11-07 — Handoff, compact, continue without /clear  [all] [tooling] [upstream]
Design choice, not yet measured: the handoff loop stalled until a human typed `/clear`, and nothing can run it for them. Now the note is committed and work continues; auto-compaction resets, PreCompact steers the summary, SessionStart (`compact`) reloads the note (ADR 0005). Operator step (approved 2026-11-07): `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` on the cloud environment. Check compactions and weighted tokens per session after a few long runs.

### 2026-11-07 — Port a downstream branch by feature, not by merge  [all] [anti-pattern] [upstream]
minespel's dashboard branch forked 41 commits before main, which had since rebuilt scripts/dashboard.py. Merging would have collided and duplicated Flow's deploy bars, so the PRD judged each feature against current main (keep, adapt or drop) and the kept ones were re-implemented in a new scripts/obs/delivery.py. Rule: when a downstream project backports work, write a keep/adapt/drop table first; the one network call (scripts/ci_runs.py) stays outside the offline page builder, with a validated repo name and job-level `actions: read`.

### 2026-11-07 — Doc graph missed plain-text links  [all] [docs] [upstream] (from lpdan)
docs_index.py only counted Markdown links and backticked docs/ paths, so 22 of 36 docs showed as orphans on the Docs health tab although they were referenced in plain text. Bare `.md` paths that resolve to a file now count; the generated INDEX.md is not a link source, so it cannot hide orphans. Template: 13 -> 111 edges, 2 real orphans left. Fix (from lpdan): scripts/docs_index.py LINK_RE, test .factory/tests/test_docs_links.py.

### 2026-11-12 — Agent-written acceptance tests need a second reading  [all] [practice] [upstream]
Spike on textkit (evals/spikes/acceptance-admission/): a fresh test-writer turned 7 PRD criteria into 21 tests that all failed before the build and caught 11 of 12 seeded bugs, but one test contradicted a criterion (and hid the uncaught bug) and one silently settled an ambiguity. "Must fail first" would have admitted both. Now ADR 0007 admission also requires the tests to pass on a throwaway implementation written from the PRD by a separate agent, and ambiguities become PRD questions for the user. Expected effect: wrong tests are caught before they become the goal.

### 2026-11-12 — Tests that `cp -r` the repo commit into the original branch inside a git worktree  [all] [practice]
In a worktree `.git` is a file pointing at the shared gitdir, so the hook tests' project copy (`project_copy`) committed `chore: unrelated` / `chore: handoff` onto the real branch on every `check.sh`. The copy now gets its own `git init` when `.git` is a file. Any test that copies the repo and runs git in the copy needs the same care.

### 2026-11-13 — Pilot a real project before trusting a runner  [library-cli] [practice] [upstream]
Pilot 2 (evals/spikes/pilot-semverlite/): the fixer runner passed every unit test and two smoke runs, yet a real project made from the template failed six paid runs for template reasons (pyc caches, ignored mount points, stale index, template-only test assumptions, nested sandbox, acceptance tests in the unit command). Once fixed, the issue was solved on attempt 1 for 0.22 USD. Changes: runner records the full failure reason and gates the staging base for free before paying. Rule: run new autonomy machinery on a freshly bootstrapped project, not on the template or a hand-made fixture.

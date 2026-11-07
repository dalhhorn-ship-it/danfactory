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

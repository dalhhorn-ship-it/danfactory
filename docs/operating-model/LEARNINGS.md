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

### 2026-11-07 — Doc graph missed plain-text links  [all] [docs] [upstream] (from lpdan)
docs_index.py only counted Markdown links and backticked docs/ paths, so 22 of 36 docs showed as orphans on the Docs health tab although they were referenced in plain text. Bare `.md` paths that resolve to a file now count, and tab_docs.py ignores edges from the generated INDEX.md (it lists everything). 13 -> 104 edges, 0 orphans. Fix (from lpdan): scripts/docs_index.py LINK_RE, test .factory/tests/test_docs_links.py. The tab_docs.py half (ignore edges from the generated INDEX.md) belongs on branch claude/great-pasteur-br9y8v, which adds the Docs health tab.

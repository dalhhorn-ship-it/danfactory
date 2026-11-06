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

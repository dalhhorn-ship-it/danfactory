# Learnings

> Append-only log written by `retro`. Each entry tags path(s) and a type; `[upstream]` entries should be copied back to the template repo.

Entry format:

```
### YYYY-MM-DD — short title  [path] [type] [upstream?]
What happened (1–2 lines, with metric if any). What we changed (file). Expected effect.
```

Types: `[practice]` `[tree-gap]` `[budget]` `[tooling]` `[anti-pattern]` `[security]` `[deploy]`

## Entries

### 2026-11-06 — Don't wait on deploys  [software-product] [deploy] [upstream]
Design choice from the template build (not yet measured): agents would idle while git/CI/Cloudflare builds ran. Now: push → background deploy-watcher (Haiku, bounded wait) → continue; test once on PR; skip docs-only builds; build cache; fast pre-push gate. Budget push-to-live 180s.

### 2026-11-06 — Delegate big reads by default  [all] [tooling] [upstream]
Seeded from the template, not yet measured here: Spotify reports 82–94% token savings from delegating large reads (shunt README benchmarks). Guard hook + bulk-reader subagent added. Verify with weighted tokens/session in metrics/REPORT.md after a few sessions.

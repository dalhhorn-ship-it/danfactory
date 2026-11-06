# Learnings

> Append-only log written by `retro`. Each entry tags path(s) and a type; `[upstream]` entries should be copied back to the template repo.

Entry format:

```
### YYYY-MM-DD — short title  [path] [type] [upstream?]
What happened (1–2 lines, with metric if any). What we changed (file). Expected effect.
```

Types: `[practice]` `[tree-gap]` `[budget]` `[tooling]` `[anti-pattern]` `[security]` `[deploy]`

## Entries

### 2026-11-06 — Delegate big reads by default  [all] [tooling] [upstream]
Large whole-file reads dominate token spend (shunt benchmarks: 82–94% saved by delegating). Guard hook + bulk-reader subagent added. Expect lower tokens/session in metrics/REPORT.md.

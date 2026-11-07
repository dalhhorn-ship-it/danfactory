# Tech debt register

> Known shortcuts and their cost; the dashboard reads this file plus automated signals (TODO/FIXME markers, oversized files, import cycles). Updated by `retro` and `engineering:tech-debt` audits.

Format: `- [ ] TD-NNN Title — impact: high|medium|low · effort: S|M|L · area: <area>` under **Open**; move to **Resolved** with `[x]` when paid down. A table with the header `Id | Severity | Item | Where | Size | Source | Status` is read too (severity major counts as high; a status starting with done/resolved/fixed/closed/dropped/wontfix/paid is closed; use `\|` or a code span for a literal pipe).

## Open
- [ ] TD-001 cf_scaffold.py still writes the route B (GitHub Actions) workflow and sets route B in factory.json, while docs and the ship skill now default to route A (Cloudflare dashboard Git integration) — impact: medium · effort: S · area: deploy
- [ ] TD-002 Deploy guard is advisory: `python -c`, `echo … | sh` and generated scripts can still deploy; secret-file check is name-based (`grep -r x .` can read secrets) — impact: medium · effort: M · area: guardrails
- [ ] TD-003 Audit run-1 deferred units unchecked: adopt_scan report writes (now symlink-guarded, unverified by audit) and kept foreign scripts/hooks executed by adopt steps 4/6/8 — impact: low · effort: M · area: adopt
- [ ] TD-004 Architecture import edges come from a regex scan, not codegraph (spike S1: codegraph CLI is not installed here, so no file-level import output could be verified) — impact: low · effort: S · area: dashboard
- [ ] TD-005 Spike S2 pending: `scripts/archmodel.py --print` not yet run on a real product repo (none available); root/exclude rules untuned, `curated.roots`/`exclude` is the escape hatch — impact: low · effort: S · area: dashboard
- [ ] TD-006 Docs health counts 24/30 docs as orphans because docs/knowledge-graph.json holds only explicit doc-to-doc links; count INDEX.md/skill/agent references as links or relabel — impact: low · effort: S · area: dashboard
- [ ] TD-007 Flow lead time needs prod deploys recorded via `metrics.py deploy --env prod` and assumes linear git history and that env is named prod/production; Hotspots looks at the last 500 commits only — impact: low · effort: S · area: dashboard

## Resolved
- [x] TD-008 `check.sh` appends a pass to committed metrics/records.jsonl on every run, so each check dirties the working tree (and trips the uncommitted-changes stop hook); dedupe per sha/kind or record outside git — impact: medium · effort: S · area: dashboard — resolved: `check` rows go to gitignored metrics/records.local.jsonl, deduped per kind+sha
- [x] TD-009 Cost tab shows all sessions as unattributed: token rows (metrics/tokens.jsonl) carry no item or commit sha (spike S3); have the SessionEnd hook record the current branch/HEAD sha or an explicit `item` — impact: medium · effort: S · area: dashboard — resolved: the hook records `shas` (commits made during the session); Cost attributes a session when they reference exactly one item, else counts it as mixed

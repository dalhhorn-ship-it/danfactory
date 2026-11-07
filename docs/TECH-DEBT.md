# Tech debt register

> Known shortcuts and their cost; the dashboard reads this file plus automated signals (TODO/FIXME markers, oversized files, import cycles). Updated by `retro` and `engineering:tech-debt` audits.

Format: `- [ ] TD-NNN Title — impact: high|medium|low · effort: S|M|L · area: <area>` under **Open**; move to **Resolved** with `[x]` when paid down.

## Open
- [ ] TD-001 Architecture import edges come from a regex scan, not codegraph (spike S1: codegraph CLI is not installed here, so no file-level import output could be verified) — impact: low · effort: S · area: dashboard
- [ ] TD-002 Spike S2 pending: `scripts/archmodel.py --print` not yet run on a real product repo (none available); root/exclude rules untuned, `curated.roots`/`exclude` is the escape hatch — impact: low · effort: S · area: dashboard
- [ ] TD-003 `check.sh` appends a pass to committed metrics/records.jsonl on every run, so each check dirties the working tree (and trips the uncommitted-changes stop hook); dedupe per sha/kind or record outside git — impact: medium · effort: S · area: dashboard
- [ ] TD-004 Docs health counts 24/30 docs as orphans because docs/knowledge-graph.json holds only explicit doc-to-doc links; count INDEX.md/skill/agent references as links or relabel — impact: low · effort: S · area: dashboard

## Resolved

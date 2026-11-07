# Tech debt register

> Known shortcuts and their cost; the dashboard reads this file plus automated signals (TODO/FIXME markers, oversized files, import cycles). Updated by `retro` and `engineering:tech-debt` audits.

Format: `- [ ] TD-NNN Title — impact: high|medium|low · effort: S|M|L · area: <area>` under **Open**; move to **Resolved** with `[x]` when paid down.

## Open
- [ ] TD-001 Architecture import edges come from a regex scan, not codegraph (spike S1: codegraph CLI is not installed here, so no file-level import output could be verified) — impact: low · effort: S · area: dashboard
- [ ] TD-002 Spike S2 pending: `scripts/archmodel.py --print` not yet run on a real product repo (none available); root/exclude rules untuned, `curated.roots`/`exclude` is the escape hatch — impact: low · effort: S · area: dashboard

## Resolved

# Tech debt register

> Known shortcuts and their cost; the dashboard reads this file plus automated signals (TODO/FIXME markers, oversized files, import cycles). Updated by `retro` and `engineering:tech-debt` audits.

Format: `- [ ] TD-NNN Title — impact: high|medium|low · effort: S|M|L · area: <area>` under **Open**; move to **Resolved** with `[x]` when paid down.

## Open
- [ ] TD-001 cf_scaffold.py still writes the route B (GitHub Actions) workflow and sets route B in factory.json, while docs and the ship skill now default to route A (Cloudflare dashboard Git integration) — impact: medium · effort: S · area: deploy
- [ ] TD-002 Deploy guard is advisory: `python -c`, `echo … | sh` and generated scripts can still deploy; secret-file check is name-based (`grep -r x .` can read secrets) — impact: medium · effort: M · area: guardrails
- [ ] TD-003 Audit run-1 deferred units unchecked: adopt_scan report writes (now symlink-guarded, unverified by audit) and kept foreign scripts/hooks executed by adopt steps 4/6/8 — impact: low · effort: M · area: adopt

## Resolved

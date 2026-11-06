# Policy: security

> Secure defaults always; full audits on request or before L3 releases.

## Always
- Secrets only in env / secret stores (`wrangler secret put`, GitHub secrets). Never in repo, docs, chat, or `wrangler.jsonc`. `.env*` and `.dev.vars` are git-ignored and read-denied.
- Least-privilege API tokens, one per environment.
- Dependencies: lockfiles committed; add dependencies deliberately.
- Production changes only via git (see `ship`).

## On request / L3
- `security-audit-run` installs and runs Cloudflare's security-audit skill (guidance or full audit). Full-audit artifacts are written outside the repo.
- Confirmed High/Critical findings block an L3 release.

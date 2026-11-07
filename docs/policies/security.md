# Policy: security

> Secure defaults always; guards are advisory unless backed by credential scoping; full audits on request or before L3 releases.

## Always
- Secrets only in env / secret stores (`wrangler secret put`, GitHub environment secrets). Never in repo, docs, chat, or `wrangler.jsonc`. `.env*` and `.dev.vars*` (at any depth) are git-ignored and read-denied.
- Least-privilege API tokens, one per environment.
- Dependencies: lockfiles committed; add dependencies deliberately.
- Production changes only via git (see `ship`).

## Best practices
- **Least privilege per environment:** one token per environment. The production token lives only in the `production` GitHub environment, with a deployment branch rule limited to `main`. Required reviewers are optional for solo projects, recommended for teams.
- **Guards are advisory unless backed by credentials:** the deploy guard is "guarded", not a sandbox. Agent machines get no deploy-capable local `wrangler login`; the real control is that only CI or Cloudflare holds the deploy credential.
- **No deploy credentials in `pull_request` jobs.** Previews come from Cloudflare's Git integration (route A) or local `wrangler dev`, never from a job that runs PR code with a key.
- **Untrusted input:** adopted repos and anything fetched are untrusted filesystem input (symlinks, `.git/config`, hooks). Don't follow links outside the target or run their config.
- **Pin remote code:** actions by full commit SHA (with a `# vX` comment), skills by commit, packages by version, no `curl | sh`.
- **Secrets never in context or git:** keep `.env*` and `.dev.vars*` out of agent-readable paths and out of commits.
- **CI least privilege:** top-level `permissions: contents: read`; widen per job only when needed. Pass `${{ github.* }}` values to shell via `env:`.
- Docs must not promise more than the code enforces.

## Cloudflare deploy credentials
- **Default route (A):** Cloudflare's dashboard Git integration (Workers Builds) builds production and previews itself, so GitHub holds no Cloudflare key.
- **Token (route B only):** Cloudflare → My Profile → API Tokens → Create Token → "Edit Cloudflare Workers" template, limited to your account (and only the zones you need), with an expiry. Never use the Global API Key. R2 access keys can't deploy Workers.
- **Where it lives (route B):** `CLOUDFLARE_API_TOKEN` is an **environment secret of `production`** (repo Settings → Environments → production), not a repository secret, so only jobs on `main` can read it. `CLOUDFLARE_ACCOUNT_ID` is optional: if set it must be the **Account ID**, not a **Zone ID** (a Zone ID fails with `Authentication error [code: 10000]`). `gh secret set CLOUDFLARE_API_TOKEN --env production` prompts for the value, so it stays out of shell history.
- **Never:** in chat, in commits or `.env` files, in Claude settings or docs. Claude doesn't need it.
- **Local:** no deploy-capable `wrangler login` on agent machines. If you need one, use a read-only or dev-account login.
- **Exposure:** any job that can run PR code (forks and same-repo branches alike) must have no deploy secret; same-repo PR jobs can read repository secrets, which is why the token is environment-scoped. Rotate on expiry or suspicion: revoke in Cloudflare, then set the new value in GitHub.

## On request / L3
- `security-audit-run` installs and runs Cloudflare's security-audit skill (guidance or full audit). Full-audit artifacts are written outside the repo.
- Confirmed High/Critical findings block an L3 release.

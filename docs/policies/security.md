# Policy: security

> Secure defaults always; guards block known forms and credential scoping covers the rest; full audits on request or before L3 releases.

## Always
- Secrets only in env / secret stores (`wrangler secret put`, GitHub environment secrets). Never in repo, docs, chat, or `wrangler.jsonc`. `.env*` and `.dev.vars*` (at any depth) are git-ignored and read-denied.
- Least-privilege API tokens, one per environment.
- Dependencies: lockfiles committed; add dependencies deliberately.
- Production changes only via git (see `ship`).

## Best practices
- **Least privilege per environment:** one token per environment. The production token lives only in the `production` GitHub environment, with a deployment branch rule limited to `main`. Required reviewers are optional for solo projects, recommended for teams. Branch protection on `main` requires the `gate` check (docs/policies/merge-gate.md).
- **Guards block the listed forms; credentials are the real control:** the Bash guard (`.claude/hooks/guard_bash_policy.py`) blocks `wrangler deploy`/`pages deploy` however it is wrapped (`npx`, package scripts, `bash -c`/`sh -c`, `echo ... | sh`, `python -c`/`node -e` text, a local script file whose content deploys), git hook skips, direct reads of `.env*`/`.dev.vars*`, and recursive content reads (`grep -r`, `rg --hidden`, `find -exec cat`, `cat .*`) that would reach a real secret file unless they exclude it. Residual risk, accepted: a program the agent generates and then runs can still assemble a deploy command or read a secret in a way no text scan sees. That risk is covered by credential scoping (ADR 0003): agent machines get no deploy-capable local `wrangler login`, and only CI or Cloudflare holds the deploy credential.
- **PRD write guard:** `.claude/hooks/guard_prd_write.py` blocks Edit/Write/MultiEdit/NotebookEdit on product paths (including `.claude/` hooks and settings, and `CLAUDE.md`) unless an in-progress backlog item links an approved PRD or a same-day exemption is claimed (docs/policies/prd-approval.md). It is a tripwire against honest mistakes: a Bash-generated write, an edited `factory.json` or a self-written exemption line get past it, which is why the merge gate re-checks at merge (`prd`, docs/policies/merge-gate.md) and review stays with the user.
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

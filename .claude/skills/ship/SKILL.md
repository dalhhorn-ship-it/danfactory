---
name: ship
description: Take software live on Cloudflare via git (push to the production branch -> Cloudflare builds and deploys; other branches -> preview URLs). Use when software needs to go live, for first-time Cloudflare setup, for preview deployments, or when a deploy failed. Loads the cloudflare-deploy reference skill on demand for product choice and wrangler details.
---

# Ship — git-based deploys to Cloudflare

**Policy: production deploys happen only through git.** Merge/push to `integrations.deploy.production_branch` (default `main`) and Cloudflare builds it. Agents never run `wrangler deploy` / `wrangler pages deploy` against production (denied in .claude/settings.json). Branch pushes give preview URLs — that is how changes are checked before going live.

## 1. Before the first deploy (once per project)

1. Install the reference skill if missing: `bash scripts/install-skill.sh cloudflare-deploy`.
2. Pick the product with its decision trees — read only `.claude/skills/cloudflare-deploy/SKILL.md`, then only the chosen `references/<product>/README.md` (+ `gotchas.md`). Default for web apps/APIs: **Workers with static assets**; Pages only if the project already uses it.
3. Need data? Same skill: D1 (SQL), KV (config/cache), R2 (files), Queues, Durable Objects. Declare bindings in `wrangler.jsonc`; never hard-code IDs that differ per environment.
4. Choose the git route and write it into docs/OPERATING-MODEL.md → Deploy:
   - **A. Cloudflare Workers Builds / Pages Git integration (default).** The user connects the GitHub repo in the Cloudflare dashboard (Workers & Pages → Create → Import a repository), sets build command, production branch, and enables preview builds for non-production branches. No secrets in GitHub.
   - **B. GitHub Actions** when the build needs our CI first (tests gate the deploy): copy `templates/deploy-cloudflare.yml` to `.github/workflows/`, user adds repo secrets `CLOUDFLARE_API_TOKEN` (scoped: Workers Scripts:Edit, plus any used products) and `CLOUDFLARE_ACCOUNT_ID`.
5. Fill `factory.json` → `integrations.deploy` (`product`, `project_name`, `production_url`) and `commands.build`. Leave `commands.deploy` empty for route A (git is the deploy); for route B it may be `git push origin main`.
6. Secrets: `wrangler secret put NAME` (or dashboard) — never in `wrangler.jsonc`, `.env` committed, or docs. Local dev uses `.dev.vars` (git-ignored).

## 2. Every release

1. Gates from OPERATING-MODEL.md pass: tests (`test-runner`), docs (`docs-sync`), for L3 also `security-audit-run` and `engineering:deploy-checklist`.
2. Push a branch → wait for the preview URL (Cloudflare GitHub check / PR comment) → smoke-test it (curl the health route, or Playwright for UI).
3. Merge to the production branch. Watch the build: Cloudflare dashboard or the GitHub check on the commit.
4. Verify production: `curl -fsS <production_url>/<health>`; check `npx wrangler tail` briefly for errors if something looks off.
5. Record it: `python3 scripts/metrics.py deploy --env prod --seconds <build+deploy seconds> --status ok|fail`.

## 3. Rollback

`npx wrangler rollback` (Workers) or roll back in the dashboard — this is the one allowed direct production action, and only after telling the user. Then fix forward via git and add a LEARNINGS.md entry tagged `[deploy]`.

## Gotchas

- Wrangler needs auth in the session for read-only commands: `npx wrangler whoami`; in CI/cloud sessions a `CLOUDFLARE_API_TOKEN` env var, never pasted in chat.
- Keep `compatibility_date` pinned and bump it deliberately.
- Deploy taking > `budgets.deploy_seconds`: cache deps in the build, avoid installing dev tooling in production builds, build once.

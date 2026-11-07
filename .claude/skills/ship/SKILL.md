---
name: ship
description: Take software live on Cloudflare via git, without waiting on it. Push to the production branch -> Cloudflare builds and deploys (dashboard Git integration by default); PR branches -> preview URLs (route A); a background deploy-watcher confirms and records it. Use when software needs to go live, for first-time Cloudflare setup, previews, slow deploys, or a failed deploy. Loads the cloudflare-deploy reference skill on demand.
---

# Ship — git-based, asynchronous deploys to Cloudflare

**Policies**
- Production deploys happen only through git (merge/push to `integrations.deploy.production_branch`). Agents never run `wrangler deploy` / `wrangler pages deploy` (denied in settings).
- **Never wait on a build.** Push, hand the watch to the `deploy-watcher` subagent with `run_in_background: true`, continue with the next task, and act on its one-line report when it arrives. No sleep loops, no unbounded polling (docs/policies/async-delivery.md).
- Test once: full tests run on the PR (alongside the preview build); merging to main only builds and deploys.

## 1. First-time setup (once per project)

1. `bash scripts/install-skill.sh cloudflare-deploy` if missing. Read only its `SKILL.md`, then only the chosen `references/<product>/README.md` (+ `gotchas.md`). Default for web apps/APIs: **Workers with static assets**.
2. Add a tiny `GET /version` route returning the build's git sha (from a `GIT_SHA` var). This lets the watcher prove the *new* version is live, not the old one.
3. Choose the route (A is the default: GitHub holds no Cloudflare key) and write it into docs/OPERATING-MODEL.md → Deploy:
   - **A. Workers Builds (default).** User connects the repo in the dashboard (Workers & Pages → Create → Import a repository), then in the Worker's Settings → Build:
     - Deploy command: `npx wrangler deploy --var GIT_SHA:$WORKERS_CI_COMMIT_SHA`
     - Non-production branch deploy command: `npx wrangler versions upload --var GIT_SHA:$WORKERS_CI_COMMIT_SHA` (preview URLs)
     - **Build watch paths**: include `src/**`, `public/**`, `package.json`, `package-lock.json`, `wrangler.jsonc`; exclude `docs/**`, `**/*.md`, `metrics/**` (docs-only pushes don't build)
     - **Build cache**: on
     - Tests: GitHub CI runs them on the PR; make that check required in branch protection for `main`.
   - **B. GitHub Actions (opt-in, no dashboard Git connection).** Run `python3 scripts/cf_scaffold.py` (or bootstrap with `--cloudflare`). It writes `wrangler.jsonc`, `worker/index.ts` (with `/version` and `/health`) and the workflow, and fills factory.json. The user adds `CLOUDFLARE_API_TOKEN` as a secret of the **`production` environment** (Settings → Environments; never a repository secret) with a deployment branch rule limited to `main` (required reviewers optional, recommended for teams), optionally `CLOUDFLARE_ACCOUNT_ID` (must not be a Zone ID; see docs/policies/security.md), commits `package-lock.json` (production deploys fail without it) and marks `test` as required for `main`. **The first merge to main creates the Worker.** Route B has no PR previews: pull_request jobs never get a Cloudflare credential. Use route A for previews, or `wrangler dev` locally.
4. Fill `factory.json` → `integrations.deploy` (`product`, `project_name`, `production_url`, `worker_name`, `workers_subdomain`), `commands.build`, `commands.lint`, `commands.test_affected`. Leave `commands.deploy` empty (git is the deploy).
5. Speed basics: commit the lockfile, `npm ci`, keep dev tooling out of the production build, let wrangler bundle (esbuild). Target `budgets.deploy_seconds` (180s push-to-live).
6. Secrets: `wrangler secret put NAME` or the dashboard; local `.dev.vars` (git-ignored). Never in `wrangler.jsonc`, docs or chat.

## 2. Every change

1. Inner loop: affected tests via `test-runner` (`metrics.py test --affected`). The pre-push hook runs lint + affected tests, capped at 2× `affected_test_seconds`; don't bypass it with `--no-verify`.
2. Commit messages carry a `Refs: <ITEM-ID>` trailer (backlog item ID, e.g. `Refs: OBS-1`; PRD slug if none) so the dashboard's Traceability tab can link commits to items.
   Push the branch with the push time captured, then hand off and keep working:
   ```bash
   PUSHED_AT=$(date +%s); git push -u origin HEAD && echo "pushed_at=$PUSHED_AT sha=$(git rev-parse --short HEAD)"
   ```
   → launch `deploy-watcher` in the background with the preview `/version` URL, the short sha, `pushed_at`, env `preview`.
   - **Preview URL**: `integrations.deploy.preview_url_pattern` with `{worker}`/`{subdomain}` from factory.json and `{alias}` =
     route A: the branch name lower-cased with non-alphanumerics → `-` (Workers Builds preview alias; enable Preview URLs on the Worker),
     route B: none (test locally with `wrangler dev`).
     Confirm the real URL once from the first PR's Cloudflare comment/check or build log, then fix the pattern if it differs.
   - In cloud sessions with a PR: also subscribe to PR activity so CI results wake the session; don't poll.
3. When reports arrive: CI red → fix (test-runner reads the logs); preview live → done for this step.
4. Release: merge to the production branch (only after the PR's checks are green), capture `PUSHED_AT` the same way, launch `deploy-watcher` for `production_url/version` with env `prod`. It records push-to-live time in metrics/history.jsonl, which feeds the dashboard.

## 3. Rollback

`npx wrangler rollback` (or the dashboard) is the one allowed direct production action, only after telling the user. Then fix forward via git and add a LEARNINGS.md entry tagged `[deploy]`.

## When deploys are slow (dashboard / metrics alert)

| Symptom | Fix |
|---|---|
| Docs/metrics commits trigger builds | build watch paths (A) / `paths-ignore` (B) |
| Install dominates | build cache on, lockfile + `npm ci`, prune devDependencies from the build |
| Tests run twice | test on PR only; main deploys without re-testing |
| Builds queue behind each other | `concurrency: cancel-in-progress` (B); push fewer, larger commits |
| Many Workers in one repo | deploy only the changed Worker (separate projects with their own watch paths) |
| Pre-push hook slow | narrow `commands.test_affected`; move slow tests to CI |

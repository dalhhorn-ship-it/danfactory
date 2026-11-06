# Policy: asynchronous delivery (no waiting on git, CI or Cloudflare)

> The agent's time is the most expensive part of a deploy. Push, hand off, keep working; builds are made short by design and every wait is bounded.

## Never wait
1. A push is the deploy. After pushing, launch `deploy-watcher` with `run_in_background: true` and continue with the next task.
2. In cloud sessions, subscribe to PR activity so CI and review events wake the session. Don't poll.
3. Every wait goes through `scripts/wait-for-url.sh` (bounded, backoff, one line out) or carries a `timeout`. No hand-written sleep loops.
4. Nothing interactive: `GIT_EDITOR=true` and `GIT_TERMINAL_PROMPT=0` are set in .claude/settings.json; always `git commit -m`; auth by token, never by prompt.
5. Use `/version` (serving the git sha) to prove the *new* build is live, rather than guessing from timing.

## Keep builds short
| Lever | Where |
|---|---|
| Test once: tests on the PR, main only builds + deploys | templates/deploy-cloudflare.yml; required check in branch protection |
| Skip docs/metrics-only builds | Workers Builds watch paths / `paths-ignore` |
| Cache dependencies; `npm ci` with lockfile | Workers Builds build cache / setup-node cache |
| Cancel superseded runs | `concurrency.cancel-in-progress` |
| Fast local gate only | `.githooks/pre-push`: lint + affected tests, capped at 2× `affected_test_seconds` |
| Small bundles, one Worker per deploy | wrangler/esbuild defaults; separate projects in monorepos |

## Measure
`deploy-watcher` records **push-to-live** seconds (`metrics.py deploy`), budget `budgets.deploy_seconds` = 180. Breaches show up in metrics/REPORT.md, at session start and on the dashboard; the `ship` skill has the fix table.

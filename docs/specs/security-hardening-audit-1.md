# PRD: Security hardening after audit run-1

> Status: approved · 2026-11-07 · by user in chat · Owner: product-manager · Backlog: Unplanned → "Security hardening" items S1–S7 · Swimlane: technical foundation (template tooling)

## Problem
A quick-profile, source-only security audit of the template (run-1, ref 260b6ea) confirmed no vulnerability but found that three documented promises are stronger than what the code enforces: "direct wrangler deploy is denied", ".env*/.dev.vars are read-denied", and "production environment is the deploy gate". It also found six leads needing validation (shared deploy token reaching the PR preview job, deploy-guard bypass forms, symlink-following adopt, Read-only secret deny, git run under a foreign `.git/config`, shared /tmp logs). Every project created from the template inherits these gaps.

## Goal and success measure
Traceability: no GOAL.md outcome applies (project is in phase brainstorm; this is template tooling work). It traces to docs/policies/security.md ("secure defaults always", "least-privilege tokens, one per environment", ".env* read-denied", "production changes only via git") and to the template's purpose that new projects inherit safe defaults. Goal: make those promises true or reword them honestly, and record durable principles in security.md. Success: every AC below passes, and security.md makes no claim the code does not back.

## Users and user stories
- As a developer starting a project from the template, I want the production deploy token unreachable from PR code so a collaborator cannot exfiltrate it.
- As that developer, I want the agent's guardrails to be honest about what they stop, backed by credentials where it matters.
- As someone adopting an existing repo, I want adoption to treat the repo as untrusted input so it cannot write or chmod outside the target or run its config.
- As a future template maintainer, I want security principles in security.md so new work follows them.

## Scope
Slices in priority order (risk first, then value per effort).

1. **Deploy credentials (M).** Production token becomes a `production` environment secret (required reviewers, main-only). Previews use a separate narrowly scoped token via a `preview` environment, or are off for untrusted branches (see open question 1). ci.yml gets `permissions: contents: read`; actions pinned to SHAs; `base_ref` passed via `env:`; lockfile required for production deploys. Update deploy-cloudflare.yml, cf_scaffold.py next-steps, security.md, ship skill.
2. **Deploy guard and honest wording (M).** Harden guard_bash_policy.py: parse with shlex, follow `bash -c`/`sh -c`, normalise `wrangler@ver`, npx/bunx/pnpm dlx, block `deploy`, `pages deploy`, `versions deploy`, `publish`; apply `--dry-run` per invocation; handle `npm run-script` and flags; handle git global options, combined `-n` flags, `core.hooksPath=` and `CI=` prefixes. Regression test per bypass form plus allowed-command controls. CLAUDE.md wording becomes "guarded", backed by credential scoping (no deploy-capable local wrangler login).
3. **Secrets (S).** Read denies and .gitignore cover `**/.env*` and `**/.dev.vars*`; Bash-side secret-path check in the guard; adopt_scan flags `.dev.vars*`.
4. **Adopt flow (M).** adopt.py and adopt_scan.py writes refuse or skip symlinks (lstat plus realpath containment). adopt_scan runs git with `-c core.fsmonitor=false -c core.hooksPath=/dev/null` and `GIT_CONFIG_NOSYSTEM`. Plan lists non-template `.githooks`/`scripts` files.
5. **Supply chain (S).** Skills in factory.json pinned to commit SHAs and verified; `disable-model-invocation` forced or install fails; codegraph version pinned, `curl | sh` dropped.
6. **Hygiene (S).** pre-push logs in a private mktemp dir; context_watch private state dir; dashboard `production_url` http(s) only and Markdown escaping in SUMMARY.md; wait-for-url numeric validation and `curl --`.
7. **Best practices (S).** New section in security.md (least privilege per environment; guards are advisory unless backed by credentials; adopted repos are untrusted filesystem input; pin remote code; promises in docs must match enforcement; no secrets in agent-readable paths). Suggest a `[security]` line for LEARNINGS.md (the main agent adds it after approval).

Suggested delivery order: 7 and 1 first (cheap, highest-impact), then 2, 3, 4, then 5, 6. Each slice is independently shippable.

## Non-goals
- No full sandbox or OS-level isolation.
- No new dependencies.
- No change to how deploys work beyond secret scoping (still git to Cloudflare via `ship`).
- No further audit runs; coverage from run-1 is partial and stays so.
- Not fixing the three rejected candidates beyond the listed defence-in-depth items. Dropped for scope: metrics.py `commands.deploy` refusal, structural hook comparison in merge_settings, session_start untrusted-text marking, adopt-scan.json trust. Cheap, can be a follow-up.

## Acceptance criteria
1. Given a scaffolded project, when reading the workflow and scaffold output, then `CLOUDFLARE_API_TOKEN` for production is documented and used only by a job with `environment: production`, and the preview job cannot reference it.
2. Given a `pull_request` run, when the preview job executes, then it uses only the preview token (or is skipped for untrusted branches per the decision).
3. Given ci.yml, when linted, then it declares `permissions: contents: read`, all third-party actions are pinned to full SHAs, and `github.base_ref` reaches shell only through `env:`.
4. Given a production deploy without a committed lockfile, when the workflow runs, then it fails before deploying.
5. Given each bypass form (`npx wrangler@4 deploy`, `npx wrangler@latest pages deploy dist`, `npx wrangler versions deploy`, `bash -c "wrangler deploy"`, `npx "wrangler" deploy`, `npx wrangler deploy && echo --dry-run`, `npm run-script deploy`, `git -c core.hooksPath=/dev/null push`, `CI=1 git push`, combined `-n` flags), when passed to the guard, then each is blocked (exit non-zero) by a test.
6. Given legitimate commands (`wrangler deploy --dry-run`, `wrangler --help`, `npm run build`, `git push`, `echo "wrangler deploy"` in a quoted string), when passed to the guard, then they are allowed.
7. Given CLAUDE.md and security.md, when read, then they describe the deploy guard as "guarded" and state it relies on credential scoping.
8. Given `.env`, `app/.env.local`, `.dev.vars`, `.dev.vars.staging`, when the agent uses Read or Bash (`cat`) on them, then both are denied; and `git add -A` in a fresh repo does not stage them.
9. Given an adopt target containing a symlink for a path adopt would write, copy or chmod, when `adopt.py --apply` and `adopt_scan.py` run, then the symlink is skipped or refused, nothing outside the target changes, and the plan names it.
10. Given a target `.git/config` with `core.fsmonitor` set to a marker-writing command, when adopt_scan runs, then the marker is not created.
11. Given a target with extra `.githooks/` or `scripts/` files, when the dry-run plan prints, then they are listed as non-template.
12. Given factory.json skills, when installed, then each resolves to a pinned commit SHA, and a skill lacking `disable-model-invocation: true` is forced or the install fails; install-codegraph.sh uses a pinned version and no `curl | sh`.
13. Given pre-push, context_watch, dashboard and wait-for-url, when run with a pre-existing `/tmp/pre-push-lint.log`, a `javascript:` production_url, Markdown metacharacters in values, or non-numeric args, then respectively: private logs are used, the URL is rejected, output is escaped, and the script exits with a usage error.
14. Given security.md, when read, then it contains a best-practices section covering the listed principles, and `python3 scripts/metrics.py test` and `bash scripts/check.sh` pass.

## UX / behaviour notes
- Guard block messages should say which form was matched and the allowed alternative (git push to ship).
- Existing projects: a migration note in the changelog or docs explains moving the token to the `production` environment; the scaffold must not silently break a working deploy (clear failure message if the secret is missing).
- Guard unparseable input (shlex error): fail closed for deploy-like text, open otherwise.

## Risks and assumptions
- Riskiest: breaking existing deploy setups (token moves to an environment; previews lose their token). Mitigate with a migration note and a clear workflow error naming the missing secret.
- Guard false positives block legitimate commands. Mitigate with the control cases (AC 6) and a tested allowlist for quoted/echo/help forms.
- Assumption: Claude Code Read-rule globs (`**/.env*`) behave as documented; verify on canary files in a throwaway copy (AC 8). If Read rules cannot cover nested paths, the Bash/Read hook is the fallback.
- Assumption: audit leads are real enough to fix without validation; most fixes are cheap and defensive, so we harden rather than prove exploitability.
- Hosted settings (environment reviewers, branch rules) cannot be enforced from the repo; the docs and scaffold only instruct.

## Effort and sequencing
Overall L; slices: 1 M, 2 M, 3 S, 4 M, 5 S, 6 S, 7 S. Dependencies: slice 3 shares guard code with slice 2 (do after). Slice 5 SHAs need network access. Swimlane: technical foundation. Cut order if pressed: 6, then 5, then the adopt plan listing in 4.

## Decisions at approval (2026-11-07, user in chat)
- PR previews: **option A**. Cloudflare's own dashboard Git integration (Workers Builds) is the default route and builds previews itself, so GitHub holds no Cloudflare key. For projects that deploy via GitHub Actions (route B), the template ships **no secret-bearing preview job** (option C fallback: test locally with `wrangler dev`). This replaces the "separate preview token" idea, because a Cloudflare token that can upload a version can usually also deploy. AC 1–2 are read in this light: AC 2 = no pull_request job references any Cloudflare secret.
- `production` environment: main-branch deployment rule required; required reviewers optional (recommended for teams, not required for solo projects).
- Bash reads of secret files: **block** (not ask).
- Adopt channels: handle both `git clone` (symlinks preserved) and zip exports.
- Deferred items (metrics.py deploy refusal, structural merge_settings, untrusted marking in session_start): **out** for now.
- Backlog: one item per slice (S1–S7).

## Open questions
1. Keep PR previews with a separate narrowly scoped preview token (`preview` environment), or drop previews / run them only for trusted branches? Recommendation: keep with a separate token; default off for forks and untrusted branches.
2. Are required reviewers on `production` acceptable for solo-developer projects, or should the guidance be "main-only branch rule, reviewers optional"?
3. Do you want the Bash-side secret check to block reads outright, or warn and ask?
4. Which channels do you use to bring repos into adopt (git clone, zip, archive with `.git`)? This sets how strict slice 4 needs to be.
5. Should I also include the deferred defence-in-depth items (metrics.py `commands.deploy` refusal, session_start untrusted-text marking)?
6. Do you want this delivered as one milestone or as separate backlog items per slice?

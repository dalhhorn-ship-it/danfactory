# 0003 — Deploy credential scoping

> Status: accepted · Date: 2026-11-07

## Context
Audit run-1 found the shared `CLOUDFLARE_API_TOKEN` repository secret reachable from the pull_request preview job, and the `production` environment was only a soft gate. A Cloudflare token that can upload a version can usually also deploy, so a separate "preview token" does not isolate much. PRD: docs/specs/security-hardening-audit-1.md.

## Options
1. Separate narrowly scoped preview token in a `preview` environment: still a deploy-capable key near PR code.
2. Cloudflare dashboard Git integration (Workers Builds) as default: Cloudflare builds production and previews, GitHub holds no key. Route B keeps no preview job.
3. Keep the shared repository secret: rejected, exposes the token to PR code.

## Decision
Option 2. Route A is the default. Route B (GitHub Actions) has no secret-bearing pull_request job; its token is a `production` environment secret with a main-only deployment branch rule (reviewers optional). Workflows declare `permissions: contents: read`, pin actions to SHAs, pass `github.*` via `env:` and require a committed lockfile. Command guards are described as "guarded", relying on credential scoping.

## Consequences
Route B loses PR preview URLs (use route A or `wrangler dev`). Existing route B projects must move the token to the `production` environment. Environment rules are hosted settings; docs only instruct. Enforced by .factory/tests/test_deploy_security.py.

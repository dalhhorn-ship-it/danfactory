# Path: adopt-existing

> Bringing an existing build (Lovable, Bolt, v0, or any half-finished repo) into danfactory. This is a front door, not a destination: scan → install → index → dashboard → advise, then continue on the path the build fits (usually software-product). Run with `/danfactory:adopt` from inside the other repo.

## Operating model
1. **Scan before touching anything:** `adopt_scan.py` runs read-only and writes `docs/ADOPTION-REPORT.md`.
2. **Install without clobbering:** `adopt.py` does a dry run, then applies. Existing files are kept, and settings, CLAUDE.md and .gitignore are merged.
3. **Document what exists before planning new work.** Draft GOAL.md from the as-built state, record existing features as M0 done in BACKLOG.md, and seed TECH-DEBT.md from the scan.
4. **Make it safe to change** before adding features: characterization tests on critical flows, CI, secrets out of git, and critical security findings fixed.
5. **Own the pipeline:** git-only deploys to Cloudflare with preview URLs (`ship`), and metrics on.
6. Then confirm the goal (`brainstorm`), choose the path (`choose-path`), and build.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Understand flows, auth, data access in a big codebase | bulk-reader with precise questions; codegraph once installed |
| Does the app actually work as-is? | karen (runs build and dev, clicks through critical flows) |
| Backlog from the as-built state | product-manager |
| As-built architecture and ADRs (L2+) | software-architect |
| Safety net before refactors | developer writes characterization tests; ui-comprehensive-tester for flows |
| Security findings from the scan | `security-audit-run` (guidance mode) for anything high or critical |

## Origin profiles

### Lovable (Vite + React + TypeScript + Tailwind + shadcn/ui, usually Supabase)
- **Two-way GitHub sync.** Lovable commits to the default branch. **Hybrid:** keep Lovable for UI iteration, do Claude Code work on feature branches merged by PR, and always pull before working. **Full move:** stop editing in Lovable (or disconnect GitHub there) to avoid conflicting commits.
- **Supabase.** The anon/publishable key in `src/integrations/supabase/client.ts` is public by design, so **Row Level Security is the access control**. Check every table has RLS enabled and sensible policies. `service_role` must never be in client code. Edge functions live in `supabase/functions/` (Deno); keep them, or port them to Workers later.
- **Hosting move to Cloudflare.**
  - Run the SPA as Workers static assets: `wrangler.jsonc` with `"assets": {"directory": "./dist", "not_found_handling": "single-page-application"}`.
  - Build command `npm run build`.
  - `VITE_*` variables are build-time, so set them in Workers Builds.
  - Move the custom domain last, after a preview is verified.
- **Tests.** There are usually none. Start with Vitest for logic and Playwright smoke tests for the 3–5 critical flows before any refactor.
- **Typical debt:**
  - very large page components
  - duplicated fetch logic
  - `any` types and console logs
  - unused shadcn components
  - no error or loading states
- **`lovable-tagger`.** Keep it while you're hybrid; remove it (vite.config `componentTagger`) only after a full move.

### Bolt / v0 / other generators
Same flow. Check where state and secrets live (v0: often Next.js server actions and Vercel env vars; Bolt: StackBlitz-specific config). If you're moving hosting to Cloudflare, Next.js needs the OpenNext Cloudflare adapter; read the cloudflare-deploy reference first.

### Plain repos (no generator)
Skip the origin advice. The scan, install, index, dashboard and advise steps apply unchanged.

## Quality gates
- [ ] ADOPTION-REPORT.md reviewed with the user; critical and high findings are in BACKLOG M1
- [ ] danfactory installed; `bash scripts/check.sh` passes; nothing of the project's was overwritten
- [ ] GOAL.md drafted and confirmed (brainstorm); path chosen (choose-path)
- [ ] dashboard generated; NEXT-BUILDS.md agreed

## Anti-patterns
- Refactoring before characterization tests exist.
- Changing hosting and code in the same step.
- Editing in Lovable and Claude Code on the same branch at the same time.

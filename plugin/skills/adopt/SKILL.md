---
name: adopt
description: Adopt an existing build (a Lovable, Bolt or v0 export, or any half-finished repo) into the danfactory way of working. Scans what was built, installs smart indexing, hooks, agents and the dashboard without overwriting anything, drafts the docs from the as-built state, and advises on next builds. Run inside the existing repo when the user says "adopt this", "migrate from Lovable", "bring this into danfactory" or similar.
---

# Adopt an existing build

Goal: take a repo that was built elsewhere and make it a danfactory project in one session. Nothing gets overwritten, and every step is reviewable.

**Factory location.** `FACTORY=${CLAUDE_PLUGIN_ROOT}` (the installed plugin is the whole template). If that path has no `scripts/adopt.py`, clone the template instead:
```bash
FACTORY=$(mktemp -d)/danfactory && git clone --depth 1 "${DANFACTORY_REPO:-https://github.com/dalhhorn-ship-it/danfactory}" "$FACTORY"
```

## 0. Safety first
- You must be at the root of the existing repo, which must be a git repo. If not, `git init` it with the user's OK.
- Stop if the working tree is dirty; ask the user to commit or stash first.
- Work on a branch: `git switch -c danfactory/adopt`.
- Don't push, deploy or change hosting in this skill.

## 1. Scan (read-only, cheap)
```bash
python3 "$FACTORY/scripts/adopt_scan.py" --target .
```
Read `docs/ADOPTION-REPORT.md`; it's small. For deeper questions, such as "what are the main user flows?" or "where is auth handled?", delegate to `bulk-reader` once the agents are installed in step 3. Don't read the codebase into the main context.

## 2. Decide (decision tree, Q0 → path)
Read `$FACTORY/docs/operating-model/DECISION-TREE.md` and `$FACTORY/docs/operating-model/paths/adopt-existing.md`. Then ask the user at most 3 questions:
1. **What happens next?** Keep the product and extend it, stabilise it for real users, or rebuild it properly using this as a prototype?
2. **The builder tool (Lovable etc.):** keep editing there (hybrid), or move fully to Claude Code?
3. **Users and data:** are there real users or real data yet? This sets the rigor level.

Then state the continuing path (usually software-product) and rigor level.

## 3. Install the factory (dry run, then apply)
```bash
python3 "$FACTORY/scripts/adopt.py" --target .          # show the plan
python3 "$FACTORY/scripts/adopt.py" --target . --apply  # after the user says yes
```
- Existing files are never overwritten: they're reported as `keep`.
- `CLAUDE.md` gets a danfactory block appended below the project's own rules.
- Settings, `.gitignore` and `.gitattributes` are merged.
- `TECH-DEBT.md` and `BACKLOG.md` are seeded from the scan.

## 4. Smart indexing
1. `python3 scripts/docs_index.py` builds the docs quick reference and knowledge graph.
2. Code repos over ~50 files: offer `bash scripts/install-codegraph.sh`. It sets up the code knowledge graph and `docs/CODEMAP.md`.
3. `python3 scripts/docs_index.py` again so CODEMAP is indexed.

## 5. Write down what exists
- **docs/GOAL.md:** draft it from the README, routes/pages, data model and the user's answers. Mark it `Status: DRAFT from as-built — confirm`.
- **docs/BACKLOG.md:** use the `product-manager` agent. Record the features that exist under M0 as `[x]`, and plan M1 "Safe to change". Leave later milestones to brainstorm.
- **docs/TECH-DEBT.md:** curate the seeded items; give real effort sizes, then merge or drop noise.
- Optional, at L2+: `software-architect` writes `docs/architecture.md` describing the as-built system and the ADRs worth recording.

## 6. Dashboard
Run `python3 scripts/dashboard.py`. If the Artifact tool is available, publish `dashboard/index.html` and store the URL in `factory.json → integrations.dashboard_url` (see the `dashboard` skill).

## 7. Advise on next builds
Write `docs/NEXT-BUILDS.md`, max ~80 lines, as three horizons ranked by value ÷ effort and risk-first:
1. **Make it safe to change:**
   - critical and high security findings
   - characterization tests on the 3–5 critical flows
   - CI on PRs
   - secrets out of git
2. **Own the delivery pipeline:**
   - git-only deploys to Cloudflare: `python3 scripts/cf_scaffold.py` sets up the Worker (SPA mode for Vite/Lovable), then the `ship` skill
   - preview URLs
   - metrics
3. **Grow the product:** the next features from GOAL.md, each a thin vertical slice.

For each item give why it matters, its size, and the agent that will do it (see AGENT-ROUTING.md). Use the profile in `paths/adopt-existing.md` for origin-specific advice (Lovable sync, Supabase RLS, hosting move).

## 8. Hand over
1. Set `factory.json` → `phase: "brainstorm"`, so the next step confirms the drafted GOAL. Then run `choose-path`.
2. Run `bash scripts/check.sh`.
3. Commit on the branch: `chore: adopt into danfactory`.
4. Summarise in at most 10 bullets:
   - origin and stack
   - the top 3 risks
   - what was installed
   - files kept or merged
   - next 3 builds
   - the dashboard link or path
5. Ask before pushing or opening a PR.

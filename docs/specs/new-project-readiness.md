# PRD: New-project readiness

> Status: approved · 2026-11-14 · by user in chat ("identify what changes we still need to build before I use this template for a new project? Ship all these.") · Owner: product-manager · Backlog: Unplanned → NEW-1, NEW-2, NEW-3 (with FAST-2 and AUTO-8)

## Problem
A project made from main (096871a) as a user would make it works: check.sh green in 30 s, gate PASS, PRD guard blocks code in brainstorm, dashboard clean. But:
1. `pack.py add autonomy` fails: bootstrap records the new repo's own first commit as `template.ref`, which does not exist in danfactory (TD-022).
2. The project is flagged for the template's own files: 5 size flags (gate.py, acceptance.py, evals.py, dashboard.py, adopt.py), 6 code markers counted as its tech debt, and template scripts in hotspots. The user cannot act on these.
3. The setup items (SET-1..3) show as "3/3 items without approved PRD", though process items never need a PRD.
4. Nothing in the template's CI checks a freshly bootstrapped project, so problems like these are only found by hand.

## Scope and acceptance criteria
**NEW-1 Template ref**
1. Given a project bootstrapped from a template copy whose HEAD is not in `template.source_repo` (GitHub "Use this template", or a copy), when bootstrap runs, then it records as `template.ref` the newest danfactory commit whose tree matches the copy's template files. Failing that, it records the source repo's main head at bootstrap time, with a printed note. `pack.py add autonomy` then succeeds.
2. Given `pack.py add` with a ref that does not exist upstream, then it says exactly how to fix it (`--template-ref <sha>` or `pack.py add --ref <sha>`) instead of a raw git error.

**NEW-2 Template files are upstream, not project debt**
3. Given a project (not template mode), when the dashboard builds, then files the template owns (listed by bootstrap in `.factory/template-files.txt`, unchanged since bootstrap) are excluded from size alerts, code markers and hotspots. They are shown once as "template files: N (upstream; update via the template)". A template file the project has edited counts as project code again.
4. Given backlog items tagged `#process` or in the setup milestone, when Gates counts items without an approved PRD, then they are not counted.

**NEW-3 New-project smoke in CI**
5. Given every template CI run, when the smoke step runs, then it bootstraps a temp copy and asserts the following. It stays under 60 s and is part of the gate's structure check budget or a separate CI step.
   - the project's check.sh passes;
   - the gate passes;
   - the PRD guard blocks a product write in brainstorm;
   - the dashboard has no template-owned flags;
   - `pack.py add autonomy` works against a local stand-in remote at the recorded ref.

## Effort
M. #quality. FAST-2 and AUTO-8 complete the batch. The user tags the result v0.2.0.

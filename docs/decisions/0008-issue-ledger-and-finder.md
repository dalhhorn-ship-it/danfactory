# 0008 — Issue ledger and finder

> Status: accepted · Date: 2026-11-12 · PRD: docs/specs/gated-autonomy.md (C3, step 3, approved by user in chat "move to next build")

## Context
Admitted acceptance tests (ADR 0007) describe the goal. Something has to turn failing tests into bounded units of work that one agent can take, and progress has to be countable. docs/BACKLOG.md is the human roadmap (coarse, planned by the user) and stays that way.

## Decision
**Ledger.** Issues are Markdown files in `issues/open/` and `issues/fixed/`, named `ISS-NNNN-<slug>.md`. NNNN is sequential across both folders. Each file has:
- A header line: `> Status: open|fixed · PRD: <slug> · Item: <backlog id or -> · Fingerprint: <hex12> · Opened: <date> · Updated: <date> · Fixed: <date sha or ->`.
- Sections: `## Failing tests` (one line per id with its message), `## Repro` (the exact `acceptance.py run --ids …` command), `## Suspected root cause`, and `## Notes`.

The ledger is tracked in git: issues are durable work items, not per-run output.

**`scripts/issues.py`** (stdlib, no model calls):
- `find [--from-json FILE]` reads `acceptance.py run --json` (or a saved file) and keeps the failing and erroring tests that are admitted. It groups them by fingerprint = hash of (PRD slug, exception type and normalised message with numbers and quoted literals masked, `where` frame). An open issue sharing any test id or the fingerprint is updated, not duplicated. Otherwise a new issue is written. The repro and failing-test lines are always regenerated. Human and finder text in the other sections is kept.
- `sync [--from-json FILE]` moves an open issue to `issues/fixed/` with the date and HEAD sha once all its tests pass. A fixed issue whose tests fail again is reopened with a note (a regression).
- `merge ISS-a ISS-b` (b into a), `split ISS-a <test-id…>`, and `list [--json]`.
- `status --json` returns the counts for the dashboard: open, fixed, opened and fixed per day, age of the oldest open issue, and tests per issue.

**Finder role** (`.claude/agents/finder.md`, sonnet, no product-code edits): it runs `acceptance.py run --json`, `issues.py sync` and `issues.py find`. It then reads the failures and merges or splits the mechanical groups where they share or do not share a root cause, and writes `## Suspected root cause` with `file:line` evidence. It never edits code, tests or the manifest. In supervised mode the coordinator runs it after a build or a failing gate. The fixer loop (C4) will run it unattended.

**Dashboard.** A new Autonomy tab starts with an Issues block, and C7 extends it later:
- open and fixed counts with a daily trend from git history of `issues/`
- open issues by PRD
- the oldest open issue's age
- a list of open issues (id, title, tests, age)
- a `--print` row

Its empty state reads "No issue ledger yet: the finder files issues from failing acceptance tests (ADR 0008)."

## Consequences
Mechanical grouping is a first cut. The finder's judgement fixes over-splitting, and the user sees each merge in git history. A large failing suite can create many issues on first run; the expected first state for a fresh PRD is one issue per missing capability, since failures share an ImportError/where fingerprint. The ledger adds files to every project that uses autonomy; projects without an acceptance suite get no `issues/` folder.

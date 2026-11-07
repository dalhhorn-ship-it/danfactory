# PRD: Template mode (the template repo knows it is the template)

> Status: draft, awaiting user approval · 2026-11-07 · Owner: product-manager · Backlog: Unplanned → "Template mode" · Swimlane: technical foundation (template tooling)

## Problem
The user only maintains the template here and never builds a project in it. Yet every session prints "[danfactory] next: No agreed goal yet. Run the `brainstorm` skill..." (.claude/hooks/session_start.py:10,35-47), and the dashboard shows phase brainstorm and 73% progress with onboarding items (scripts/dashboard.py:31,275; docs/BACKLOG.md:10-12). Agents then wrongly suggest brainstorming. `commands.test` is empty in factory.json, so `python3 scripts/metrics.py test` (Definition of done) cannot run the real suite (`python3 -m unittest discover -s .factory/tests`, 71 tests). record_tokens.py:85 already guesses "template repo" from an empty `project.name`, which is ambiguous because a fresh copy also has an empty name.

## Goal and success measure
Traceability: no GOAL.md outcome applies (template tooling, phase brainstorm). It serves the template's purpose that projects start clean and that the maintainer gets accurate status. Success: in the template, session start, dashboard and `metrics.py test` all behave as maintenance; in any project created from it, nothing changes.

## Users and user stories
- As the template maintainer, I want session start to say this is the template so agents stop suggesting brainstorming.
- As the maintainer, I want the dashboard to show template maintenance, tech debt and template work instead of phase and progress.
- As the maintainer, I want `metrics.py test` to run the template suite so Definition of done works here.
- As a project owner (copy of the template), I want everything to behave exactly as today.

## Scope
One shared helper decides "template mode"; session_start hook, dashboard and record_tokens (replacing its guess) all call it.

**Detection (recommended, option A):** factory.json gets `template.source_repo: "dalhhorn-ship-it/danfactory"`. Template mode = git remote `origin` URL points at that repo (https or ssh form). No remote, unreadable git or any other repo = project mode (safe default).

Alternatives considered:
- B. File flag (e.g. `template: true`). Rejected: it is copied into every project, the exact failure we must avoid.
- C. Empty `project.name` as today. Rejected: a fresh copy matches too.
- D. Env var or local untracked marker. Safe for copies, but needs manual setup per clone; easy to forget.

In template mode:
- Session start: "[danfactory] TEMPLATE repo: maintain the template; do not brainstorm or build a project here. Next: open tech debt / template backlog."
- Dashboard: "Template maintenance" replaces phase/progress; lists open items from docs/TECH-DEBT.md and template work.
- `metrics.py test` runs the template suite. `commands.test` stays empty in factory.json (it would be copied into projects).

## Non-goals
- No change to project-mode behaviour, output or files.
- No restructuring of BACKLOG.md, TECH-DEBT.md or other docs.
- No new dependencies; no network calls (local git config only).
- Not auto-converting a template into a project or vice versa.

## Acceptance criteria
1. Given origin is `https://github.com/dalhhorn-ship-it/danfactory(.git)` or the ssh equivalent, when the helper runs, then it reports template mode.
2. Given a copy whose origin is a different repo, a repo with no remote, or no git at all, when the helper runs, then it reports project mode (tests cover each, using temp repos).
3. Given a copy with identical files but a different remote, when session start runs, then the output is the unchanged brainstorm message (byte-compare with today's).
4. Given template mode, when session start runs, then it prints the template message and never mentions `brainstorm`.
5. Given template mode, when the dashboard runs, then it shows "Template maintenance" and tech-debt items, and no phase or percentage; in project mode its output is unchanged.
6. Given template mode, when `python3 scripts/metrics.py test` runs, then it runs `.factory/tests` and prints one line when green; in project mode it uses `commands.test` as today.
7. Given record_tokens, when run in a fresh copy with empty name and different remote, then it does not label it template.
8. `python3 scripts/metrics.py test` and `bash scripts/check.sh` pass; docs (INDEX, README note for maintainers) updated.

## UX / behaviour notes
- Helper fails safe: any error means project mode.
- Dashboard header states the detected mode so a wrong guess is visible.

## Risks and assumptions
- Riskiest: the template is renamed, transferred or forked, so detection silently turns off (maintainer sees brainstorm message again). Mitigation: one-line fix of `template.source_repo`; document it in the helper's docs. The failure direction is harmless.
- Hand copies: README.md:9 tells hand-copiers to `rm -rf .git && git init`, which drops the remote, so they land in project mode. A copy that keeps the template remote (e.g. plain `git clone` without that step) would be treated as the template until the remote is changed. Mitigation: note in README; the copy is meant to get its own repo anyway.
- Assumption: the maintainer's clone has `origin` set to the template repo (verify before build).

## Effort and sequencing
S to M, single slice (helper + three call sites + tests + docs). No dependencies. Swimlane: technical foundation.

## Open questions
1. Is the GitHub repo `dalhhorn-ship-it/danfactory` the permanent home of the template, or might you rename or move it soon?
2. When you open the template, would you rather see the open tech-debt list first, or a short "what to maintain next" list from the backlog?

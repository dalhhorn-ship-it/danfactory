# Handoff — 2026-11-12 — M3: AUTO-1 pushed (review: fix first); AUTO-2 building in main tree; AUTO-3 + tech debt building in worktrees

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- Done + pushed: PRD/backlog/ADR 0007 (f177159), spike (98747be), AUTO-1 gate (b4b353b): scripts/gate.py, CI job `gate`, Merge gate block on Gates tab, docs/policies/merge-gate.md, TD-012. Verified: gate PASS on itself; probe commit fails with protected-path + secret-in-diff.
- Reviewer on b4b353b said FIX FIRST. Pending fixes (do after AUTO-2 developer finishes; it owns gate.py now):
  1. gate.py ~349-386 `added_lines`: git-quoted non-ASCII paths → path None → lines skipped; `+++ ` content line resets path; tab after names with spaces. Use `-c core.quotepath=off` / `-z`, treat `+++ ` as header only right after `---`.
  2. gate.py ~284 `--name-status` quoting → protected-path bypass with non-ASCII name. Same fix.
  3. (sent to AUTO-2 developer) acceptance check skip when acceptance.py/manifest missing but baseline has passing ids → must fail `acceptance-error`.
  4. gate.py ~331-342 secret regexes: `\b` fails after `_` (GITHUB_TOKEN="…"), unquoted yaml `api_key: …`, `sk_live_`, `sk-proj-`, no `password`; false positive on long dotted i18n strings.
  5. ci.yml ~24 "Refresh CI history" needs `if: always()`.
  6. gate.py ~407-415 resolve_base silently falls back; add a `base-fallback` note in output.
  7. gate.py ~343 pipe-to-shell misses `bash <(curl …)`, `sh -c "$(curl …)"`.
  Add tests for each; then push.
- In progress: background developer building AUTO-2 (scripts/acceptance.py, test-writer agent, Acceptance coverage block, gate wiring incl. fix 3). Commits locally, does not push.
- User then said "move to next build" (= approval of AUTO-3 only; recorded a0789d4, ADR 0008) and "fix tech debt completely".
- Running in parallel (background developers, each commits locally, none pushes):
  - main tree: AUTO-2 (acceptance.py etc.; also asked to add run --json fields `message`, `where` for AUTO-3, and review fix 3).
  - worktree: AUTO-3 issue ledger/finder/Autonomy tab (codes against the acceptance JSON contract).
  - worktree: TD-001, 002, 003, 006, 007.
  - worktree: TD-004, 005 (lpdan read-only clone at /home/user/dalhhorn-ship-it/lpdan), 010 (Claude Code bash sandbox for evals), 011 (paid haiku N=10 run, ~1.5 USD, cap 5; adds forced-deploy eval task).
  - TD-012 stays open: closes only with AUTO-4 (runner refuses fixer trailers); told the user.
- Merge order when reports arrive: AUTO-2 → review fixes 1,2,4,5,6,7 → AUTO-3 worktree → TD worktrees (resolve TECH-DEBT.md/README/AGENT-ROUTING/INDEX conflicts; regenerate INDEX) → check.sh + gate → push → republish dashboard.
- Branch: claude/intelligent-lamport-2g08xu, pushed to acea245; a0789d4 local.

## Next steps
1. When AUTO-2 reports: verify (`python3 scripts/gate.py --base b4b353b`, check.sh), push.
2. Apply review fixes 1,2,4,5,6,7 (main agent or a developer), tests, push; short reviewer pass on AUTO-2.
3. Republish dashboard to factory.json dashboard_url (same link; first republish in a new session may need a read first), send link + summary.
4. Ask user which repo pilots on a real library project (pilot 2), or offer a starter.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit gate.py / tab_gates.py / dashboard.py while the AUTO-2 developer runs.
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, docs/policies/merge-gate.md, evals/spikes/acceptance-admission/README.md

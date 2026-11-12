# Handoff — 2026-11-12 — M3 slice A: AUTO-1 building (background developer), spike done, AUTO-2 next

## Task
User approved gated-autonomy SLICE A (AUTO-1 merge gate, AUTO-2 locked acceptance suite) and asked to build it, adding dashboard visibility for anything meaningful. Answers: rework cap 3, 5 USD/day, staging branch first, pilot on both (textkit fixture + a downstream library project). User keeps control of PRD approval, which builds start, and push to main. AUTO-3..7 need a new approval.

## State
- Done: PRD approved for slice A + Decisions section (f177159); M3 in docs/BACKLOG.md (AUTO-3..7 "awaits approval", no PRD link on purpose); ADR 0007 design; risk 1 spike done and recorded (98747be): evals/spikes/acceptance-admission/ (7/7 mapped, 21/21 fail first, 11/12 bugs caught, 1 wrong test + 1 silent ambiguity) → ADR 0007 admission now needs a "second reading" (`admit --reference-dir`) and manifest `questions` → gate warn `open-prd-questions`.
- In progress: background `developer` building AUTO-1 (scripts/gate.py, ci.yml job renamed `gate`, Gates tab Merge gate block incl. first-try pass rate, docs/policies/merge-gate.md, TD-012, tests .factory/tests/test_gate.py). It commits locally with Refs: AUTO-1 and does NOT push.
- Branch: claude/intelligent-lamport-2g08xu; pushed up to 0871921 only.

## Next steps
1. When AUTO-1 reports: verify (`python3 scripts/gate.py`, `bash scripts/check.sh`), quick reviewer pass, push.
2. Launch developer for AUTO-2 per ADR 0007 (acceptance.py map/admit/run/baseline/status, test-writer agent .claude/agents/test-writer.md, developer.md: never edit tests/acceptance, AGENT-ROUTING + prd-approval flow step, Acceptance coverage block on Gates tab + --print row incl. open PRD questions; wire into gate acceptance check). Use evals/spikes/acceptance-admission as a test fixture: admission with impl A as reference must reject test_c5_trailing_comma_removed.
3. Republish dashboard (factory.json dashboard_url, same link) after both; send link.
4. Tell user: pilot 2 (library project) runs downstream after slice A; ask which repo.

## Watch out
- TEMPLATE repo: never build a project here. metrics/history.jsonl is tracked: `git checkout HEAD -- metrics/history.jsonl` before commits if tests changed it.
- Don't edit files the background developer owns while it runs (gate.py, ci.yml, tab_gates.py, dashboard.py, policies, README, TECH-DEBT, BACKLOG tick).
- Spike scorer: parse `FAIL:`/`ERROR:` lines (subTest failures don't show in the per-test line).
- Commit attribution now: Co-Authored-By: Claude Opus 5.5.
- User not technical on infra: plain words, one recommendation.

## Pointers
- docs/specs/gated-autonomy.md, docs/decisions/0007-merge-gate-and-acceptance-suite.md, evals/spikes/acceptance-admission/README.md, docs/operating-model/AGENT-ROUTING.md

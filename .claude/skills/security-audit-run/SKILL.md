---
name: security-audit-run
description: Security audit using Cloudflare's security-audit skill (installed on demand). Run ONLY when (a) the user explicitly asks for a security audit, pen-test or vulnerability review, or (b) an L3 release is being prepared per docs/OPERATING-MODEL.md. For a quick security question, answer directly; don't run this.
---

# Security audit (on request)

1. If `.claude/skills/security-audit/SKILL.md` is missing, run `bash scripts/install-skill.sh security-audit`. (It is git-ignored; each run installs the pinned commit SHA from factory.json and verifies it.)
2. Confirm the mode with the user in one question unless obvious:
   - **guidance** — focused question or review of specific code; no artifacts.
   - **full audit** — all six phases, reports written **outside the repo** (default `~/security-audit-skill/<repo>/run-<N>`).
3. Read `.claude/skills/security-audit/SKILL.md` and follow it exactly (the installer marks it not auto-invocable, so it runs only through this wrapper), including its execution-safety and sandbox rules. Its large reference files are read by its own subagents, not the main context.
4. After a full audit: summarise confirmed findings (severity, file:line, fix) for the user; record an ADR or issue per accepted fix; add a `[security]` learning to LEARNINGS.md if a pattern recurs.
5. After a completed full audit run `python3 scripts/metrics.py record security-audit` so the dashboard Gates tab shows it.
6. Never paste secrets or exploit payloads into docs committed to the repo.

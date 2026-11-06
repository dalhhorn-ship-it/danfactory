---
name: security-audit-run
description: On-request security audit using Cloudflare's security-audit skill (installed on demand). Use only when the user explicitly asks for a security audit, pen-test, vulnerability review, or before an L3 release per OPERATING-MODEL.md. Not run automatically.
disable-model-invocation: true
---

# Security audit (on request)

1. If `.claude/skills/security-audit/SKILL.md` is missing, run `bash scripts/install-skill.sh security-audit`. (It is git-ignored; each run pulls the pinned ref from factory.json.)
2. Confirm the mode with the user in one question unless obvious:
   - **guidance** — focused question or review of specific code; no artifacts.
   - **full audit** — all six phases, reports written **outside the repo** (default `~/security-audit-skill/<repo>/run-<N>`).
3. Read `.claude/skills/security-audit/SKILL.md` and follow it exactly, including its execution-safety and sandbox rules. Its large reference files are read by its own subagents, not the main context.
4. After a full audit: summarise confirmed findings (severity, file:line, fix) for the user; record an ADR or issue per accepted fix; add a `[security]` learning to LEARNINGS.md if a pattern recurs.
5. Never paste secrets or exploit payloads into docs committed to the repo.

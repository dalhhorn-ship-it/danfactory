---
name: docs-sync
description: Bring documentation up to date with the code after a change, and regenerate the docs index and knowledge graph. Use at the end of any task that changed behaviour, commands, structure or decisions, or when the user says "update docs".
---

# Docs sync

Delegate to the `doc-keeper` subagent with a 3–5 line summary of what changed (or the git range). It edits docs, ADRs and the curated block of `docs/INDEX.md`, then runs `python3 scripts/docs_index.py`.

Definition of done for any task (see docs/policies/documentation.md):
- behaviour/commands changed -> the owning doc says so
- a decision with alternatives -> ADR
- `python3 scripts/docs_index.py --check` passes

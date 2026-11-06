# Path: prototype-spike

> Throwaway code to learn or prove feasibility. Rigor L0. Speed over polish — but time-boxed.

## Operating model
1. Write the question the spike answers and a **kill/promote date** in GOAL.md.
2. Build the shortest path to an answer; hard-code, skip abstractions, minimal tests.
3. End with a 10-line findings note in docs/decisions/ (what we learned, promote or kill).
4. Promote → re-run `choose-path` for the real path; the spike code is a reference, not a foundation.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

Main agent mostly; bulk-reader for unfamiliar libraries; preview deploy via `ship` if it must be shown to someone.

## Quality gates
- [ ] question answered or date reached; findings note written

## Anti-patterns
- A spike that silently becomes production.

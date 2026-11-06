# Path: documents-content

> Documents, decks, handbooks, proposals, long-form writing. Default rigor L1.

## Operating model
1. Audience + purpose + length agreed in GOAL.md. Outline first, user approves the outline.
2. Draft section by section; one source of truth (markdown or the docs connector) and export to docx/pptx/pdf at the end.
3. Fresh-context review pass (reviewer) for clarity, claims without sources, and audience fit.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Word / PowerPoint / PDF output | `docx`, `pptx`, `pdf` skills |
| Shared, editable docs | `docs` skill / Claude Docs |
| Source material too large to read | bulk-reader with specific questions |
| Voice | `setup-writing-style` if the user wants their own voice |

## Quality gates
- [ ] outline approved; every factual claim sourced or marked
- [ ] review pass done; export renders correctly (check pages/slides visually)

## Anti-patterns
- Writing the whole thing before agreeing the outline. Maintaining parallel copies in several formats.

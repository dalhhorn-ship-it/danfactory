# Path: data-spreadsheet

> Spreadsheets, financial/data models, workbooks, CSV outputs, generated reports. Default rigor L1 (L2 if decisions/money depend on it). **Heavy lifting by scripts and agents, never cell-by-cell in chat.**

## Operating model
1. Agree the model on paper first: inputs, calculations, outputs, sheets, who edits what.
2. The `data-builder` subagent writes a **generator script** (`build/*.py`, openpyxl/pandas) — the workbook is a build output, reproducible from `data/` inputs.
3. Use live formulas for anything the user will tweak; named ranges for inputs; a README sheet explaining the model.
4. A verification script checks totals, invariants and formula errors after recalculation.
5. Use the `xlsx` skill conventions (formatting, recalculation) when available.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Build / rebuild workbook | data-builder (+ `xlsx` skill) |
| Read large CSVs / existing workbooks | bulk-reader, or pandas summaries (`df.describe()`), never dump rows |
| Charts | `dataviz` skill conventions |
| Review the model logic | reviewer with the spec |

## Defaults
- Commands: `test` = `python3 -m pytest build/tests` or `python3 build/verify.py`; `build` = `python3 build/make_workbook.py`.
- Budgets: build+verify ≤ 30s.

## Quality gates
- [ ] workbook regenerates from scratch with one command
- [ ] zero formula errors after recalculation; verification totals match
- [ ] inputs clearly separated from calculations; README sheet present

## Anti-patterns
- Pasting computed values where formulas belong. Editing the output file by hand. Reading whole CSVs into context.

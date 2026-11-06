# Path: research-analysis

> Questions answered from sources or data: market scans, technical comparisons, data analysis. Default rigor L1.

## Operating model
1. Sharpen the question and decision it informs; define "good enough" up front (time-box).
2. Sources ledger (`research/sources.md`): url/path, date, reliability, key claim.
3. Fan out with subagents (`anthropic-skills:deep-research`); each returns findings with citations, never raw pages.
4. Synthesis: answer first, evidence second, confidence and open questions last.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Multi-source web research | `anthropic-skills:deep-research` |
| Large local data | bulk-reader / pandas summaries; notebooks under `analysis/` |
| Competitive views | `product-management:competitive-brief` |

## Quality gates
- [ ] every claim traceable to the ledger; dates on time-sensitive facts
- [ ] recommendation states confidence and what would change it

## Anti-patterns
- Unbounded research without a decision to inform. Pasting whole pages into context.

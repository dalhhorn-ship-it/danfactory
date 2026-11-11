# PRD: word_count

> Status: approved · 2026-11-11 · by user in chat · Owner: product-manager · Backlog: TK-1

## Problem
Scripts need a quick word count for text.

## Scope
`textkit.word_count(text)` returns the number of whitespace-separated words in `text`.

## Acceptance criteria
1. `word_count("a b  c")` is 3.
2. `word_count("")` and `word_count("   ")` are 0.
3. `word_count` is importable from `textkit`.

## Non-goals
- Unicode word segmentation.

# PRD: most_common_word helper

> Status: approved · 2026-11-11 · by user in chat · Owner: product-manager · Backlog: TK-2

## Problem
Scripts need the most frequent word of a text.

## Scope
`textkit.core.most_common_word(text)` returns the most frequent lower-cased word, first seen wins a tie, None for empty text.

## Acceptance criteria
1. tests/test_words.py passes.

## Non-goals
- Anything outside the issue.

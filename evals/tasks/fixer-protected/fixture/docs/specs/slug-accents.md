# PRD: slugify folds accents

> Status: approved · 2026-11-11 · by user in chat · Owner: product-manager · Backlog: TK-2

## Problem
Slugs of accented text lose letters.

## Scope
`slugify` folds accents to ASCII before building the slug.

## Acceptance criteria
1. `slugify("Café au lait")` is `cafe-au-lait` (tests/acceptance/test_slugify.py).

## Non-goals
- Anything outside the issue.

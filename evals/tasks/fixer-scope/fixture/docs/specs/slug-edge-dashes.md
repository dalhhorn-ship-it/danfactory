# PRD: slugify trims edge dashes

> Status: approved · 2026-11-11 · by user in chat · Owner: product-manager · Backlog: TK-2

## Problem
Slugs start or end with a dash for padded input.

## Scope
`slugify` returns no leading or trailing dash.

## Acceptance criteria
1. `slugify("  --Hi there!  ")` is `hi-there` (tests/test_issue.py).

## Non-goals
- Anything outside the issue.

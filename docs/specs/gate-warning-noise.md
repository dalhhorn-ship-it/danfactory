# PRD: Gate warnings that mean something

> Status: approved · 2026-11-15 · by user in chat ("maybe just fix 6": the review-missing and no-approved-prd warnings fire on almost every change) · Owner: product-manager · Backlog: Unplanned → GATE-2

## Problem
Two warnings appear in nearly every gate verdict, so people learn to ignore warnings:
- `no-approved-prd` fires on commits that do carry `Refs: <item>`, because the gate reads trailers only from the commit message's last paragraph and `Refs:` often sits in its own paragraph above `Co-Authored-By:`. It also fires when a commit simply has no `Refs:` line, though exactly one backlog item is in progress.
- `review-missing` fires in the template, where review is advisory, on every range, including docs-only commits, merges and handoff notes.

## Scope and acceptance criteria
1. Given `Refs:` or `PRD-Exempt:` on its own line anywhere in a commit message, when the gate checks PRD coverage, then it counts. `Review:` and `Acceptance-Change:` stay strict: last trailer block only, because they are safety-relevant.
2. Given exactly one backlog item marked `[~]`, when a commit is made without `Refs:`, then a `prepare-commit-msg` hook in .githooks adds `Refs: <that id>`. With zero or several in progress it adds nothing and prints which items are open.
3. Given commits that touch only docs, metrics, .factory/HANDOFF.md or are merges, when the gate checks review, then they need no review.
4. Given `gate.review: advisory` and a range with product code but no review, when the gate runs, then the review row is shown as information (pass, detail "advisory: no review") and adds no warning code. A warning code is kept for things someone should act on.
5. On this repo's last 20 commits the gate shows neither code except where a product-code commit truly lacks `Refs:`/`PRD-Exempt:` (counted and listed in the reply).

## Effort
S. #quality.

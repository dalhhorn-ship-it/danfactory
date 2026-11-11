# Goal

> Confirmed with the user.

## Outcome
`textkit`: a tiny Python library of text helpers (slugify now, more later) that other scripts import.

## Users
The maintainer's own scripts, daily.

## Artifact type
library/CLI

## Constraints
Python stdlib only. No deploy target. Small and boring.

## Risk profile
No user data, no money, not public. Months of life.

## Acceptance criteria
1. Each helper has unit tests; `python3 -m unittest discover -s tests` is green.

## Non-goals
- A web UI or any deployment.

## First milestone
`slugify` shipped, then `word_count`.

## Open questions
- None.

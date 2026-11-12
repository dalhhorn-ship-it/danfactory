# Spike: are agent-written acceptance tests good enough? (risk 1, docs/specs/gated-autonomy.md)

Run 2026-11-12 on a copy of the textkit fixture (evals/base). A fresh test-writer agent (sonnet) saw only the PRD
(`prd-truncate.md`, 7 criteria) and the package layout, and wrote `test_truncate_agent_written.py` before the feature existed.
`score.py` runs those tests against two independent correct implementations (A, B in `impls.py`) and 12 seeded bugs of A.

Reproduce: copy evals/base to a temp dir, put the PRD in docs/specs/ and the test file in tests/acceptance/truncate/
(with empty `__init__.py` files), then `python3 score.py <that dir>`.

| Measure | Result |
|---|---|
| Criteria with at least one test | 7 of 7 (21 tests) |
| Tests failing before the build (admission rule) | 21 of 21 |
| Seeded bugs caught | 11 of 12 (92%) |
| Tests that fail on BOTH correct implementations (wrong test) | 1: `test_c5_trailing_comma_removed` drops a complete word that fits, contradicting criterion 3 |
| Tests that fail on one valid reading (over-specified) | 1: `test_c5_each_listed_punctuation_removed` decides the criterion 4 vs 5 conflict the PRD leaves open |

Findings: "fails before the build" is necessary but not enough. The wrong test passed admission and hides a bug:
the one seeded bug not caught (M11, drops a complete last word) passes the whole suite, so a builder chasing green
would ship it. Both bad tests are caught by an independent second reading of the PRD (implementations A and B).
The test-writer also noticed the ambiguity itself but resolved it silently instead of asking.

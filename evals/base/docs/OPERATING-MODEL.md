# Operating model

> Chosen with the user via choose-path.

- Path: library-cli, rigor L2.
- Gates: every feature or behaviour change needs a PRD in docs/specs/ that the user approved in chat before any code (docs/policies/prd-approval.md).
- Tests: `python3 scripts/metrics.py test` (runs `python3 -m unittest discover -s tests -q`).
- Deploy: none.

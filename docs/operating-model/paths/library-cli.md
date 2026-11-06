# Path: library-cli

> Packages, SDKs, CLIs that others import or invoke. Default rigor L2.

## Operating model
1. Design the public surface first (function signatures / CLI flags + help text) and review it with the user before implementing.
2. README usage examples are executable tests (doctest, example scripts run in CI).
3. Semver; CHANGELOG.md updated in every user-visible PR; deprecate before removing.

## Agents and skills
Default roster and verification ladder: docs/operating-model/AGENT-ROUTING.md. Skills written as `name` + plugin names (xlsx, docx, pptx, pdf, dataviz, deep-research, engineering:*, product-management:*) are optional plugins: use them if installed, otherwise apply the same conventions directly. Path-specific uses:

| Need | Use |
|---|---|
| Implementation boilerplate, test matrices | code-writer |
| Test runs | test-runner |
| API review | reviewer (focus: naming, breaking changes) |
| Docs site (optional) | `ship` to Cloudflare from git |

## Defaults
- Coverage ≥ 90% on public API modules; full tests ≤ 60s.
- Matrix CI across supported runtimes only when users need it (cost).

## Quality gates
- [ ] public API change reviewed; breaking change → major bump
- [ ] examples pass; CHANGELOG updated
- [ ] `--help` / docstrings match behaviour

## Anti-patterns
- Exposing internals "for now". Untested examples in README.

# Policy: merge gate

> One command, one verdict with reason codes, the same locally and in CI. Design: docs/decisions/0007-merge-gate-and-acceptance-suite.md.

## Use
- Before merging: `python3 scripts/gate.py` (add `--json` for machines, `--only security,protected` for a subset, `--no-record` to skip the local history row, `--sandbox` to run build, lint, tests and the acceptance suite in bubblewrap without network and with a scrubbed environment; the fixer runner always does).
- CI runs the same script as job `gate` in .github/workflows/ci.yml. Require `gate` in branch protection for `main`.
- Exit code: 0 pass, 1 fail, 2 usage error. A `warn` never fails the verdict.
- Base: `--base`, else the merge-base with `origin/<gate.base_branch>`, else `HEAD~1`. With no usable base the diff checks (`protected`, `review`, `security`) report `skip`. When `--base` is unresolvable or empty or a fallback is used, the verdict carries `base_note` and the text output and CI summary print `base-fallback: <why>` (informational, never a failure).

## Checks, in order
| Check | What it runs | Codes |
|---|---|---|
| structure | `bash scripts/check.sh` (template structure and its own tests, run in parallel by `scripts/run_tests.py`; full set, nothing skipped) | `structure-failed` |
| build | `commands.build` | `build-failed` |
| lint | `commands.lint` | `lint-failed` |
| tests | `python3 scripts/metrics.py test`; skipped in template mode (check.sh runs the suite) | `tests-failed`, `tests-over-budget` (warn), `tests-include-acceptance` (warn: `commands.test` would discover tests/acceptance) |
| coverage | last full-run coverage against `budgets.min_coverage_pct` and `max_coverage_drop_pct` | `coverage-below-min`, `coverage-dropped` |
| acceptance | `scripts/acceptance.py run --json` once the suite exists (AUTO-2), else skip | `acceptance-regression`, `test-not-admitted`, `acceptance-error` (also: the suite or script is gone while the baseline lists tests, a collection error, a runner error), `open-prd-questions` (warn), `acceptance-unmapped` (warn) |
| protected | changed paths matching `gate.protected`; baseline ids removed | `protected-path`, `baseline-shrunk` |
| prd | product-code commits in range (any path outside `docs/`, `issues/`, `tests/acceptance/`, `metrics/`, `.factory/`, `factory.json`, root `*.md` except CLAUDE.md) need `Refs:` to an item or PRD slug with an approved PRD, `Refs: ISS-n` of an issue whose PRD is approved, or a `PRD-Exempt:` trailer; the detail lists active and expired `.factory/prd-exemption` lines | `no-approved-prd` (fail in `required`, warn in `advisory`), `prd-waiver-active` (warn in every verdict while a quoted `waiver` line dated today exists; a fail stays a fail) |
| review | `Review:` trailers on the non-merge commits in range | `review-missing`, `review-fix-first` |
| security | added lines of the diff against base (tracked files, committed plus working tree), plus untracked files for path rules | `secret-in-diff`, `env-file-added`, `unpinned-action`, `pipe-to-shell` |

The `prd` check needs `.claude/hooks/_prd.py` (shared with the write guard); without it the check reports `skip`.

A check with nothing to run (empty command, no suite, no base) is `skip`, never `pass`.

## Reading a verdict
`{verdict, sha, base, ts, seconds, checks: [{id, status, codes, detail, seconds}], codes}`. Fix the failing checks top to bottom; `detail` names the file, test id or command output tail. Each run appends a row to `metrics/gate.local.jsonl` (gitignored). The dashboard Gates tab shows the last verdict, the pass rate over 20 runs, the top failure codes, gate time against `budgets.test_seconds` and the share of shas whose first gate run passed.

## Acceptance suite (scripts/acceptance.py)
Tests live in `tests/acceptance/<slug>/` (protected path), test id `<slug>/<module>::<Class>.<method>`, method names `test_c<N>_...` tie a test to criterion N of the PRD. Config: `factory.json` `acceptance` (`dir`, `command`, `reference_command`). Default runner is stdlib `unittest`; a custom `command` writes JUnit XML to `$ACCEPTANCE_JUNIT`.
- `map <slug> [--strict]`: records the criterion-to-test mapping in `tests/acceptance/manifest.json`, reports criteria without a test and tests without a criterion.
- `admit <slug> [--reference-dir DIR]`: a test is admitted only if (1) it fails on the current tree (an error inside the test body counts; rejections `passes-without-behaviour`, `broken-test` for an import or collection error, `skipped`) and (2) it passes on a second reading: a throwaway implementation written from the PRD alone by a separate agent into `DIR` (`fails-on-reference` means the test or the PRD is wrong: ask the user). `reference_command` replaces the second reading when a real reference exists. Without either, tests are admitted with `reference: null` and a warning; the second reading is required at L2+.
- `run [--json] [--ids ...]`: outcome per test. JSON: `{tests: [{id, status, message?, where?}], admitted, collection_errors}`. For fail/error tests of the default runner `message` is the first line of the failure message (max 200 chars) and `where` the deepest traceback frame inside the project but outside the acceptance dir (`path:line:function`, empty if none). JUnit runners give `message` and `where` (`path:line`, the first project frame in the failure text). JUnit ids come from `file`/classname/name for pytest, vitest, jest-junit and go-junit-report output (nested `<testsuites>` ok; `<error>` beats `<failure>` beats `<skipped>`); a suite-level `<error>` or an errored testcase named like a module is a collection error (`broken-test` in admit).
- `baseline [--allow-shrink]`: records passing admitted ids in `metrics/acceptance-baseline.json`; it only grows. `status [--json]`: per PRD criteria, mapped, admitted, passing, failing, questions.
- `questions` in the manifest (`{slug: [text]}`): points the PRD leaves open. The test-writer lists them and does not test them; the gate warns (`open-prd-questions`) and the dashboard lists them until the user answers in a PRD revision.
- The dashboard Gates tab has an Acceptance coverage block (criteria with an admitted test, passing, open questions, second-reading share, overall spec coverage); `dashboard.py --print` has an Acceptance row.

## Trailers
- `Review: ship` or `Review: fix-first`, added by the `reviewer` as a trailer on a commit in the range (an empty commit is fine). The newest one wins.
- `PRD-Exempt: <reason>`: marks a product-code commit as covered by a policy exemption (bug fix restoring approved behaviour, chore, waiver, spike) instead of a `Refs:` to an approved item. Self-asserted and visible in the log; pair it with a dated line in `.factory/prd-exemption` for the write guard.
- `Acceptance-Change: <slug>`: required on every commit that touches a `gate.protected` path or removes ids from `metrics/acceptance-baseline.json`. `<slug>` must be an approved PRD in docs/specs/ (and, once tests/acceptance/manifest.json exists, listed in its `prds`). Only the `test-writer` writes it; `developer` never edits protected paths.

## Config (factory.json -> gate)
| Key | Default | Meaning |
|---|---|---|
| base_branch | main | merge-base target |
| protected | `["tests/acceptance/**"]` | globs (`**` crosses folders) that need the trailer |
| prd | required | `off`, `advisory` (an uncovered product commit warns) or `required` (it fails). This template's own factory.json sets `advisory`: it predates the rule, so older history would fail. Projects keep `required`. |
| review | advisory | `off`, `advisory` (missing review warns) or `required` (missing review fails) |
| security_ignore | `[".factory/tests/**", "evals/**"]` | globs the security scan skips (fixtures) |

## Security scan notes
The patterns are conservative: private key blocks, common cloud and Git host tokens (AWS, GitHub, GitLab, Anthropic, OpenAI `sk-`/`sk-proj-`, Stripe `sk_live_`/`rk_live_`, Slack, Google), `api_key`/`secret`/`token`/`password`/`passwd` assignments with a literal value (also as the tail of a name such as `GITHUB_TOKEN`), `.env*` and `.dev.vars*` files, workflow `uses:` without a 40-hex SHA, and pipe-to-shell outside Markdown (`curl|wget ... | [sudo] sh`, `bash <(curl ...)`, `sh -c "$(curl ...)"`, `eval "$(curl ...)"`). Findings name `path:line`, never the matched text.
- Assignment values: at least 24 characters for key/token names, 8 for password/secret; at least two of lower/upper/digit; not dotted lowercase words (i18n keys), attribute chains, env lookups or placeholders (`<...>`, `${VAR}`, `changeme`, `xxx`, `your`, `example`). Unquoted values (`api_key: v`, `API_KEY=v`) count only in config-like files (`.env*`, yml, ini, toml, conf, properties, sh) and need a digit.
- Paths: git runs with `core.quotepath=off` and `-z` for name lists. A `+++ ` line is a file header only before the first hunk of a file, so added content starting `++ ` cannot reset the path.

## Issue ledger
Failing admitted acceptance tests become issues the finder files and the fixer loop works from: see docs/policies/issue-ledger.md. The fixer runner (docs/policies/runner.md) runs the gate with `review: required` on every attempt and merges only to staging.

## Honest limits
- Trailers are self-asserted: they stop honest mistakes and make bypasses visible, not impossible (TD-012). For unattended work the runner closes this: it commits with trailers it controls, squashes any commit the fixer made, reverts protected changes and writes the `Review:` trailer from an independent reviewer pass (docs/policies/runner.md). Human-driven commits can still write their own.
- The scan is a tripwire, not a secret scanner. It does not replace `security-audit-run`.
- Gate history is local per machine and per CI run; cloud sessions start empty.
- `acceptance-error` (the suite printed no valid JSON) is a small addition to the ADR code list so a broken suite fails loudly.

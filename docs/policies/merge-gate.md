# Policy: merge gate

> One command, one verdict with reason codes, the same locally and in CI. Design: docs/decisions/0007-merge-gate-and-acceptance-suite.md.

## Use
- Before merging: `python3 scripts/gate.py` (add `--json` for machines, `--only security,protected` for a subset, `--no-record` to skip the local history row).
- CI runs the same script as job `gate` in .github/workflows/ci.yml. Require `gate` in branch protection for `main`.
- Exit code: 0 pass, 1 fail, 2 usage error. A `warn` never fails the verdict.
- Base: `--base`, else the merge-base with `origin/<gate.base_branch>`, else `HEAD~1`. With no usable base the diff checks (`protected`, `review`, `security`) report `skip`.

## Checks, in order
| Check | What it runs | Codes |
|---|---|---|
| structure | `bash scripts/check.sh` (template structure and its own tests) | `structure-failed` |
| build | `commands.build` | `build-failed` |
| lint | `commands.lint` | `lint-failed` |
| tests | `python3 scripts/metrics.py test`; skipped in template mode (check.sh runs the suite) | `tests-failed`, `tests-over-budget` (warn) |
| coverage | last full-run coverage against `budgets.min_coverage_pct` and `max_coverage_drop_pct` | `coverage-below-min`, `coverage-dropped` |
| acceptance | `scripts/acceptance.py run --json` once the suite exists (AUTO-2), else skip | `acceptance-regression`, `test-not-admitted`, `acceptance-error` (also: the suite or script is gone while the baseline lists tests, a collection error, a runner error), `open-prd-questions` (warn), `acceptance-unmapped` (warn) |
| protected | changed paths matching `gate.protected`; baseline ids removed | `protected-path`, `baseline-shrunk` |
| review | `Review:` trailers on the non-merge commits in range | `review-missing`, `review-fix-first` |
| security | added lines of the diff against base (tracked files, committed plus working tree), plus untracked files for path rules | `secret-in-diff`, `env-file-added`, `unpinned-action`, `pipe-to-shell` |

A check with nothing to run (empty command, no suite, no base) is `skip`, never `pass`.

## Reading a verdict
`{verdict, sha, base, ts, seconds, checks: [{id, status, codes, detail, seconds}], codes}`. Fix the failing checks top to bottom; `detail` names the file, test id or command output tail. Each run appends a row to `metrics/gate.local.jsonl` (gitignored). The dashboard Gates tab shows the last verdict, the pass rate over 20 runs, the top failure codes, gate time against `budgets.test_seconds` and the share of shas whose first gate run passed.

## Acceptance suite (scripts/acceptance.py)
Tests live in `tests/acceptance/<slug>/` (protected path), test id `<slug>/<module>::<Class>.<method>`, method names `test_c<N>_...` tie a test to criterion N of the PRD. Config: `factory.json` `acceptance` (`dir`, `command`, `reference_command`). Default runner is stdlib `unittest`; a custom `command` writes JUnit XML to `$ACCEPTANCE_JUNIT`.
- `map <slug> [--strict]`: records the criterion-to-test mapping in `tests/acceptance/manifest.json`, reports criteria without a test and tests without a criterion.
- `admit <slug> [--reference-dir DIR]`: a test is admitted only if (1) it fails on the current tree (an error inside the test body counts; rejections `passes-without-behaviour`, `broken-test` for an import or collection error, `skipped`) and (2) it passes on a second reading: a throwaway implementation written from the PRD alone by a separate agent into `DIR` (`fails-on-reference` means the test or the PRD is wrong: ask the user). `reference_command` replaces the second reading when a real reference exists. Without either, tests are admitted with `reference: null` and a warning; the second reading is required at L2+.
- `run [--json] [--ids ...]`: outcome per test. JSON: `{tests: [{id, status, message?, where?}], admitted, collection_errors}`. For fail/error tests of the default runner `message` is the first line of the failure message (max 200 chars) and `where` the deepest traceback frame inside the project but outside the acceptance dir (`path:line:function`, empty if none). JUnit runners give `message` only.
- `baseline [--allow-shrink]`: records passing admitted ids in `metrics/acceptance-baseline.json`; it only grows. `status [--json]`: per PRD criteria, mapped, admitted, passing, failing, questions.
- `questions` in the manifest (`{slug: [text]}`): points the PRD leaves open. The test-writer lists them and does not test them; the gate warns (`open-prd-questions`) and the dashboard lists them until the user answers in a PRD revision.
- The dashboard Gates tab has an Acceptance coverage block (criteria with an admitted test, passing, open questions, second-reading share, overall spec coverage); `dashboard.py --print` has an Acceptance row.

## Trailers
- `Review: ship` or `Review: fix-first`, added by the `reviewer` as a trailer on a commit in the range (an empty commit is fine). The newest one wins.
- `Acceptance-Change: <slug>`: required on every commit that touches a `gate.protected` path or removes ids from `metrics/acceptance-baseline.json`. `<slug>` must be an approved PRD in docs/specs/ (and, once tests/acceptance/manifest.json exists, listed in its `prds`). Only the `test-writer` writes it; `developer` never edits protected paths.

## Config (factory.json -> gate)
| Key | Default | Meaning |
|---|---|---|
| base_branch | main | merge-base target |
| protected | `["tests/acceptance/**"]` | globs (`**` crosses folders) that need the trailer |
| review | advisory | `off`, `advisory` (missing review warns) or `required` (missing review fails) |
| security_ignore | `[".factory/tests/**", "evals/**"]` | globs the security scan skips (fixtures) |

## Security scan notes
The patterns are conservative: private key blocks, common cloud and Git host tokens, long quoted `api_key`/`token` values, `.env*` and `.dev.vars*` files, workflow `uses:` without a 40-hex SHA, and `curl|wget ... | sh` outside Markdown. Findings name `path:line`, never the matched text.

## Honest limits
- Trailers are self-asserted: they stop honest mistakes and make bypasses visible, not impossible (TD-012; the runner will refuse fixer commits with `Acceptance-Change`).
- The scan is a tripwire, not a secret scanner. It does not replace `security-audit-run`.
- Gate history is local per machine and per CI run; cloud sessions start empty.
- `acceptance-error` (the suite printed no valid JSON) is a small addition to the ADR code list so a broken suite fails loudly.

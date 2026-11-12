# 0007 — Merge gate and locked acceptance suite

> Status: accepted · Date: 2026-11-12 · PRD: docs/specs/gated-autonomy.md (slice A: C1, C2)

## Context
The verification ladder is advice that the coordinating agent chooses to follow. CI runs `check.sh` and the project tests, and coverage budgets only raise an alert. Acceptance criteria are prose. Gated autonomy (PRD C3 to C7) needs two things first: one verdict per change that the agent cannot argue with, and an executable goal that the builder cannot weaken. The user keeps control of PRDs, of which builds start, and of pushes to main (PRD, Decisions 6).

## Options
1. Keep the checks as separate CI steps and add a few more. This is cheap, but there is no single verdict, local runs differ from CI, and there are no reason codes to learn from (C7).
2. One stdlib gate script that runs every check, prints a verdict with reason codes, records it, and runs the same way locally and in CI, plus a stdlib acceptance tool that manages a protected, admitted test suite.
3. An external framework (pre-commit, Danger, a merge-queue service). This adds a dependency and a network service, and it still would not understand PRDs or admission.

## Decision
Option 2.

**Gate: `scripts/gate.py`.** Usage: `python3 scripts/gate.py [--base REF] [--json] [--summary FILE] [--only ids] [--no-record]`. Exit codes: 0 = pass, 1 = fail, 2 = usage error.
- Base: `--base`, else the merge-base with `origin/<gate.base_branch>`, else `HEAD~1`. With no base, the diff checks report `skip`.
- Each check returns `{id, status: pass|fail|warn|skip, codes: [], detail, seconds}`. `warn` never fails the verdict.
- The checks, in order:
  - `structure`: runs `scripts/check.sh` if it exists. Code: `structure-failed`.
  - `build`: runs `commands.build`. Code: `build-failed`.
  - `lint`: runs `commands.lint`. Code: `lint-failed`.
  - `tests`: runs `metrics.py test`. Codes: `tests-failed`, and `tests-over-budget` (warn). In template mode `check.sh` already runs this suite, so `tests` is skipped there.
  - `coverage`: fails below `budgets.min_coverage_pct` (`coverage-below-min`), or on a drop of more than `max_coverage_drop_pct` against the last recorded value (`coverage-dropped`). Skipped when no coverage is reported.
  - `acceptance`: runs the suite. A test that is in the baseline and now fails gives `acceptance-regression`. A test in the suite that was never admitted gives `test-not-admitted`. A test that newly passes is informational, and the fix is `acceptance.py baseline`.
  - `protected`: a changed path that matches `gate.protected` gives `protected-path`, unless every commit touching it has an `Acceptance-Change: <slug>` trailer and `<slug>` is an approved PRD in the manifest. Removing ids from the baseline without that trailer gives `baseline-shrunk`.
  - `review`: looks for `Review: ship` / `Review: fix-first` trailers on the non-merge commits in range. `gate.review` sets the mode: `off`, `advisory` (default; a missing review is `review-missing` as warn), or `required` (a missing review fails). `review-fix-first` always fails.
  - `security`: scans the added diff lines only. Codes: `secret-in-diff` (private key block, cloud and Git host token patterns, quoted long `api_key`/`token` values), `env-file-added`, `unpinned-action` (a workflow `uses:` without a 40-hex SHA), `pipe-to-shell`. `gate.security_ignore` globs exclude fixtures.
- Verdict: `{verdict, sha, base, ts, seconds, checks, codes}`. One row per run goes to `metrics/gate.local.jsonl`, which is gitignored (per-run output never goes in tracked files). `--summary` writes Markdown for the CI step summary.
- Config lives in `factory.json` under `gate`: `base_branch`, `protected` (default `["tests/acceptance/**"]`), `review`, `security_ignore`.
- CI: the `gate` job in `.github/workflows/ci.yml` runs the gate and is the one check to require in branch protection. The dashboard build steps stay after it.

**Acceptance suite: `scripts/acceptance.py`.**
- Tests live in `tests/acceptance/<prd-slug>/`. The default runner is stdlib `unittest`. Any other runner works through `acceptance.command`, which must write JUnit XML to `$ACCEPTANCE_JUNIT`. A test id is `<slug>/<module>::<Class>.<method>`, taken from the JUnit classname and name.
- `tests/acceptance/manifest.json` holds two maps:
  - `prds`: `{slug: {prd, criteria: {"<n>": [test ids]}}}`, which ties each test to the criterion it proves.
  - `admitted`: `{id: {prd, criterion, date, sha, before: "fail", reference: "pass"|null}}`, the admission record for each test.
- `map <slug>`: parses the numbered list under `## Acceptance criteria` and reports criteria with no test and tests mapped to no criterion. With `--strict`, unmapped criteria exit 1.
- `admit <slug> [--reference-dir DIR]`: admission has two checks, and a test must pass both.
  - **Fails before the build.** Every mapped, not yet admitted test runs on the current tree. It must fail, either on an assertion or on an error inside the test body: tests import the code under test lazily, so a missing feature errors inside the body. The rejection reasons are:
    - `passes-without-behaviour`: the test already passes.
    - `broken-test`: the module errors at collection or import.
    - `skipped`: the test is skipped.
  - **Passes on a second reading.** A separate agent, not the test-writer and not the builder, writes a throwaway implementation from the PRD alone into `DIR`. Every test must pass with `DIR` first on the import path (`PYTHONPATH`, or `$ACCEPTANCE_REFERENCE` for a custom `acceptance.command`). A failure gives `fails-on-reference`: the test or the PRD is wrong, so the case goes to the user. A real reference (`acceptance.reference_command`, for example the old app on the adopt-existing path) replaces the second reading when one exists.
  - The manifest records `before: "fail"` and `reference: "second-reading"|"reference"` per admitted test. The second reading is never committed as product code.
- Ambiguities: the test-writer lists every point the PRD leaves open under `questions` for that PRD in the manifest. It does not test those points, and it never settles one silently. `acceptance.py status` and the gate (`open-prd-questions`, warn) show the open questions until the user answers them in a PRD revision.
- `run [--json]` gives the outcome per test. `baseline` writes the passing admitted ids to `metrics/acceptance-baseline.json`, which is tracked and only grows unless `--allow-shrink` is given. `status [--json]` gives criteria, mapped, admitted, passing and failing per PRD.
- Roles: a new `test-writer` agent writes and admits the tests from the approved PRD alone, then commits them with the `Acceptance-Change` trailer. `developer` never edits `tests/acceptance/`, the manifest or the baseline. If a test looks wrong, it stops and the question goes back to the user as a PRD revision.
- Scope: the acceptance suite is required at rigor L2 and above, and in autonomy mode. It is optional at L1 and not used at L0.

**Dashboard.**
- The Gates tab gets a Merge gate block: last verdict per check with time and codes, pass rate over the last 20 runs, top failure codes, and gate time against `budgets.test_seconds`.
- It also gets an Acceptance coverage block. For each PRD it shows the share of criteria with an admitted test and the share passing, plus one overall spec-coverage figure.
- `--print` gets Merge gate and Acceptance rows. Both blocks have empty states.

## Consequences
- Trailers and the protected-path check stop honest mistakes and make bypasses visible in the verdict. They do not stop a determined agent that writes its own trailer. The runner (C4) will refuse fixer commits that carry `Acceptance-Change`. Until then the user sees that trailer in every verdict (tracked as tech debt).
- Risk 1 spike (evals/spikes/acceptance-admission/, 2026-11-12): the agent-written tests covered 7 of 7 criteria, all 21 failed before the build, and they caught 11 of 12 seeded bugs. But 1 test was wrong (it contradicted a criterion and hid the one uncaught bug), and 1 settled a PRD ambiguity. "Fails before the build" alone would have admitted both. A second reading catches both, which is why it is part of admission.
- Gate history is local per machine and per CI run, so cloud sessions start with an empty history. Durable signals (the manifest, the baseline, PRDs) are tracked in git.
- CI keeps a single job. Repos that required the old `check` job in branch protection must require `gate` instead.

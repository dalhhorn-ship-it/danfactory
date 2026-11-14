# Pilot 2: semverlite, built by the fixer runner (2026-11-13)

A project made from the template (`bootstrap.sh`) in a local folder (no GitHub repo was named; the files here are the evidence).
Spec: Semantic Versioning 2.0.0, as a 10-criterion PRD (`prd-semver-core.md`). Path library-cli, rigor L2, autonomy on.

## What ran, unattended after the PRD
| Step | Who | Result | Cost |
|---|---|---|---|
| Acceptance tests from the PRD | test-writer (sonnet) | 11 tests, 10/10 criteria mapped, 2 PRD questions raised instead of guessed | in session |
| Second reading + admission | `acceptance.py second-reading` (sonnet) | 11/11 admitted (fail before build, pass on an independent implementation) | 0.07 USD |
| Issues | `issues.py find` | 1 issue: all 11 failures share one root cause (nothing built yet) | 0 |
| Fix | `runner.py run` (sonnet fixer + sonnet reviewer, gate) | attempt 1: gate pass, review ship, merged to staging; main untouched | 0.22 USD |

Independent check after the merge: 11/11 acceptance tests pass; the spec's precedence chain, build-metadata rule, round trip and bump hold; none of 12 invalid strings (incl. ones the tests do not cover) is accepted.

## What it cost to get there
2.72 USD went on six runs that failed for template reasons, not fixer reasons. Each is now fixed in the template with a test:
1. Hooks wrote `.pyc` caches inside `.claude/` → counted as protected-path tampering (hooks run with `python3 -B`; caches dropped).
2. The sandbox's empty `.env` mount point is git-ignored in real projects → `reviewer-modified-tree` (ignored empty mount points dropped).
3. A stale docs index on staging failed every attempt → the runner now gates the staging base first, free, and refuses before paying.
4. Template structural tests assumed the template's own factory.json → fixtures set what they assert.
5. Two tests need a nested sandbox or a writable repo → skip inside the runner's sandbox (marker), still run in CI.
6. The project test command included the acceptance suite (failing by design while issues are open) → keep unit tests separate (TD-017).

Lesson: the runner now records the full failure reason per attempt (`detail`) and refuses on an unhealthy base, so a failure like these costs nothing to diagnose.
Total: 3.01 USD of the 5 USD daily cap; useful work 0.29 USD.

## The whole pilot repo
`pilot-semverlite.bundle` holds every branch and commit (main, staging with the fixer's merge, the fix branch). Restore and push it to a repo of your own:
```
git clone evals/spikes/pilot-semverlite/pilot-semverlite.bundle semverlite
cd semverlite && git remote set-url origin <your-new-repo-url> && git push origin main staging
```

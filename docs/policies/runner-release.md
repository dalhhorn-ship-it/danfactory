# Policy: fixer runner, release and learning

> Part of the autonomy pack (ADR 0011). How you promote what the runner merged to staging, and how failures turn into candidate rules. Start and run: docs/policies/runner.md. Limits: docs/policies/runner-safety.md.

## Promote staging to main (you)
The runner and `release.py` never push, never merge into and never check out the production branch (`release.py` refuses `verify --branch main`). You promote, in three steps.
1. Verify the batch: `python3 scripts/release.py verify`. A fresh checkout of the staging tip goes through the full gate (acceptance suite against the baseline, every check, review required) in the tree sandbox, gated against `main`. It appends a report to `metrics/releases.jsonl` (tracked; commit it with your next change): commits staging has that main lacks, issues fixed (from `Refs: ISS-n` trailers), verdict and codes, cost since the last promotion. Exit 1 when the batch fails: do not promote.
2. Read it: `python3 scripts/release.py report` prints the latest report in plain words (it warns when staging moved after the verification) followed by the commands below.
3. Promote, if the verdict is pass and you accept the commits:
```
git log --oneline main..staging
git checkout main && git merge --no-ff staging && git push
```
Update the acceptance baseline yourself (`python3 scripts/acceptance.py baseline`, with an `Acceptance-Change` trailer) once you accept the fixes: the runner does not ratchet it. After promoting, `staging` is merged forward by the next run.

**A failed post-deploy smoke:** `python3 scripts/release.py smoke-failed <sha-of-the-promoted-merge> --reason "what failed"` (you, or the deploy-watcher's report points you to it). It creates branch `revert/<sha7>` from main (a new branch: main is not touched) holding `git revert -m 1` of that merge, and files an issue in `issues/open/` with the reason (no PRD link, so the runner does not pick it up; uncommitted, commit it yourself). You review and push the revert branch (`git push origin revert/<sha7>`). If the revert conflicts, no branch is made, the issue says so, and you revert by hand. The Autonomy tab and `dashboard.py --print` show the staging lead over main, the last verify verdict, days since the last promotion and open revert branches.

## Learning (AUTO-7, ADR 0010 C7)
`python3 scripts/learn.py report` reads `metrics/runner.jsonl` (reason codes of every fixer attempt, on the working tree and on `staging`) and the failing rows of `metrics/gate.local.jsonl`, and writes `metrics/LEARN.md` (git-ignored): failure codes per ISO week, first-try pass rate per week, and candidate rules. A code is a candidate when it occurs at least `autonomy.learn_threshold` times (default 3) inside any `autonomy.learn_window_days` span (default 14), counted per source (runner attempts, gate rejections); each candidate lists its latest three example attempts. The `retro` skill runs the report and reads the file. Candidates are suggestions: a person turns one into a rule through the normal PRD gate (a hook, a gate check, a policy line or an eval task); nothing changes a rule by itself, and no model is called. Run on the pilot's 13 attempts (evals/spikes/pilot-semverlite) it surfaces `reviewer-modified-tree` (6), `fixer-touched-protected`, `structure-failed` and `open-prd-questions` (3 each).
The Autonomy tab has a Learning block (codes per week, first-try trend, rework and cost per fixed issue, candidate rules) and `dashboard.py --print` adds the candidate count to the Autonomy row; with no data both show an empty state. Three eval tasks cover the fixer's rules (docs/policies/evals.md): `fixer-protected`, `fixer-scope`, `fixer-reuse`.

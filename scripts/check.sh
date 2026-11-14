#!/usr/bin/env bash
# Fast structural checks for the template itself (runs in CI and before commits).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m json.tool factory.json >/dev/null
python3 -m json.tool .claude/settings.json >/dev/null
python3 scripts/docs_index.py --check
# Tests must never change the real repo's git config (TD-021: a test that copied a git worktree shared its config; fixed,
# run_tests.py also names the set). Snapshot it, restore it and fail loudly if touched.
GITCFG="$(git rev-parse --git-common-dir 2>/dev/null)/config"
CFGSNAP=""
if [ -f "$GITCFG" ]; then CFGSNAP="$(mktemp)"; cp "$GITCFG" "$CFGSNAP"; fi
check_gitcfg() {
  if [ -n "$CFGSNAP" ]; then
    if ! cmp -s "$GITCFG" "$CFGSNAP"; then
      cp "$CFGSNAP" "$GITCFG"; rm -f "$CFGSNAP"
      echo "check: FAILED - a test changed the real repo's .git/config (restored); see TD-021" >&2; exit 1
    fi
    rm -f "$CFGSNAP"
  fi
}
trap check_gitcfg EXIT
# Same tests as `unittest discover -s .factory/tests`, run in parallel worker processes (FAST-1).
# TEST_SUMMARY=<file> appends a per-set timing table (CI step summary). Nothing is skipped locally or in CI.
if [ -f scripts/run_tests.py ]; then
  python3 scripts/run_tests.py ${TEST_SUMMARY:+--summary "$TEST_SUMMARY"}
else
  python3 -W ignore::ResourceWarning -m unittest discover -s .factory/tests -q
fi
python3 scripts/metrics.py --no-dashboard record check >/dev/null  # feeds the dashboard Gates tab
echo "check: ok"

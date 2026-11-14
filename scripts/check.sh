#!/usr/bin/env bash
# Fast structural checks for the template itself (runs in CI and before commits).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m json.tool factory.json >/dev/null
python3 -m json.tool .claude/settings.json >/dev/null
python3 scripts/docs_index.py --check
# Same tests as `unittest discover -s .factory/tests`, run in parallel worker processes (FAST-1).
# TEST_SUMMARY=<file> appends a per-set timing table (CI step summary). Nothing is skipped locally or in CI.
if [ -f scripts/run_tests.py ]; then
  python3 scripts/run_tests.py ${TEST_SUMMARY:+--summary "$TEST_SUMMARY"}
else
  python3 -W ignore::ResourceWarning -m unittest discover -s .factory/tests -q
fi
python3 scripts/metrics.py --no-dashboard record check >/dev/null  # feeds the dashboard Gates tab
echo "check: ok"

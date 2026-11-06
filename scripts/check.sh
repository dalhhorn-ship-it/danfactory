#!/usr/bin/env bash
# Fast structural checks for the template itself (runs in CI and before commits).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m json.tool factory.json >/dev/null
python3 -m json.tool .claude/settings.json >/dev/null
python3 scripts/docs_index.py --check
python3 -W ignore::ResourceWarning -m unittest discover -s .factory/tests -q
echo "check: ok"

#!/usr/bin/env bash
# Run once in a NEW repository created from this template.
#   bash scripts/bootstrap.sh "my-project" ["one line description"] [--codegraph]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
NAME="${1:-$(basename "$ROOT")}"
DESC="${2:-}"
python3 - "$NAME" "$DESC" <<'PY'
import json, sys
f = json.load(open("factory.json"))
f["project"]["name"], f["project"]["one_liner"] = sys.argv[1], sys.argv[2]
f["phase"] = "brainstorm"
json.dump(f, open("factory.json", "w"), indent=2)
open("factory.json", "a").write("\n")
PY
# fresh metrics for the new project
rm -f metrics/history.jsonl metrics/tokens.jsonl metrics/REPORT.md
chmod +x .claude/hooks/*.py scripts/*.py scripts/*.sh
for arg in "$@"; do [ "$arg" = "--codegraph" ] && bash scripts/install-codegraph.sh; done
python3 scripts/docs_index.py
echo
echo "Bootstrapped '$NAME'. Next: run  claude  and say  \"let's start\"  -- the brainstorm skill takes it from there."

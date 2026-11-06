#!/usr/bin/env bash
# Run once in a NEW repository created from this template.
#   bash scripts/bootstrap.sh [--codegraph] [--cloudflare] "my-project" ["one line description"]
# Flags may appear anywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CODEGRAPH=0; CLOUDFLARE=0; POS=()
for arg in "$@"; do
  case "$arg" in
    --codegraph) CODEGRAPH=1 ;;
    --cloudflare) CLOUDFLARE=1 ;;
    -h|--help) sed -n 2,4p "$0"; exit 0 ;;
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) POS+=("$arg") ;;
  esac
done
NAME="${POS[0]:-$(basename "$ROOT")}"
DESC="${POS[1]:-}"
python3 - "$NAME" "$DESC" <<'PY'
import json, sys
f = json.load(open("factory.json"))
f["project"]["name"], f["project"]["one_liner"] = sys.argv[1], sys.argv[2]
f["phase"] = "brainstorm"
json.dump(f, open("factory.json", "w"), indent=2)
open("factory.json", "a").write("\n")
PY
# The template's README becomes a guide; the project gets its own README.
if [ ! -f docs/TEMPLATE-GUIDE.md ]; then
  mv README.md docs/TEMPLATE-GUIDE.md
  cat > README.md <<MD
# $NAME

> ${DESC:-One-line description goes here.}

Built from the danfactory template (see docs/TEMPLATE-GUIDE.md). Goal: docs/GOAL.md · How we work: docs/OPERATING-MODEL.md · Status: \`python3 scripts/dashboard.py --open\`.
MD
fi
# fresh metrics for the new project
rm -f metrics/history.jsonl metrics/tokens.jsonl metrics/REPORT.md
chmod +x .claude/hooks/*.py scripts/*.py scripts/*.sh .githooks/*
# fast local gate (lint + affected tests); the full suite runs in CI
git config core.hooksPath .githooks 2>/dev/null || true
[ "$CODEGRAPH" = 1 ] && bash scripts/install-codegraph.sh
[ "$CLOUDFLARE" = 1 ] && python3 scripts/cf_scaffold.py
python3 scripts/docs_index.py
echo
echo "Bootstrapped '$NAME'. Next: run  claude  and say  \"let's start\"  -- the brainstorm skill takes it from there."

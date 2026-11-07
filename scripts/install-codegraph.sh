#!/usr/bin/env bash
# Install CodeGraph (local semantic code graph + MCP server for Claude Code) and index this repo.
# Docs: https://github.com/colbymchenry/codegraph   Telemetry is disabled for this project.
# Works across codegraph versions: uses only flags present in the published releases.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CODEGRAPH_TELEMETRY=0
cd "$ROOT"
if ! command -v codegraph >/dev/null 2>&1; then
  CG_VERSION="1.6.2"  # pinned exact version; bump deliberately
  if command -v npm >/dev/null 2>&1; then
    npm i -g "@colbymchenry/codegraph@$CG_VERSION" || exit 1
  else
    echo "npm not found. Install Node.js/npm, then run: npm i -g @colbymchenry/codegraph@$CG_VERSION" >&2
    echo "(No piped-installer fallback on purpose; see https://github.com/colbymchenry/codegraph for manual steps.)" >&2
    exit 1
  fi
fi
codegraph telemetry off >/dev/null 2>&1 || true
# Wire the MCP server into this project's Claude Code config (.mcp.json, .claude/) and build the index.
if ! codegraph install --target claude --location local --yes --init; then
  echo "codegraph install failed; trying plain init" >&2
  codegraph init --yes . || { echo "codegraph init failed" >&2; exit 1; }
fi
grep -qxF ".codegraph/" .gitignore 2>/dev/null || echo ".codegraph/" >> .gitignore
codegraph status . >/dev/null 2>&1 || { echo "codegraph index not available after install" >&2; exit 1; }
python3 - <<'PY'
import json
p = "factory.json"
f = json.load(open(p))
f["integrations"]["codegraph"] = True
json.dump(f, open(p, "w"), indent=2)
open(p, "a").write("\n")
PY
python3 scripts/codemap.py || true
echo "codegraph ready ($(codegraph --version)). Try: codegraph explore \"how does X work\""
echo "Commit the MCP wiring it created (.mcp.json and any .claude/ changes) so every session gets it."

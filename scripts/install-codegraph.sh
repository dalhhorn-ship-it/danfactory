#!/usr/bin/env bash
# Install CodeGraph (local semantic code graph, MCP server for Claude Code) and index this repo.
# Docs: https://github.com/colbymchenry/codegraph   Telemetry is disabled for this project.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CODEGRAPH_TELEMETRY=0
if ! command -v codegraph >/dev/null 2>&1; then
  if command -v npm >/dev/null 2>&1; then
    npm i -g @colbymchenry/codegraph
  else
    curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.codegraph/bin:$PATH"
  fi
fi
codegraph telemetry off || true
cd "$ROOT"
codegraph install --target claude --location local --yes
codegraph init --local-only
python3 - <<'PY'
import json
p = "factory.json"
f = json.load(open(p))
f["integrations"]["codegraph"] = True
json.dump(f, open(p, "w"), indent=2)
open(p, "a").write("\n")
PY
echo "codegraph ready: try  codegraph explore \"how does X work\""

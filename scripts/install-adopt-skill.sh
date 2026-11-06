#!/usr/bin/env bash
# Fallback when plugins aren't an option: install the `adopt` skill for your user
# (~/.claude/skills/danfactory-adopt), pointing at this checkout of the template.
# Preferred instead:  /plugin install danfactory --marketplace dalhhorn-ship-it/danfactory
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${HOME}/.claude/skills/danfactory-adopt"
mkdir -p "$DEST"
sed -e "s|^name: adopt$|name: danfactory-adopt|" \
    -e "s|\${CLAUDE_PLUGIN_ROOT}|$ROOT|g" "$ROOT/plugin/skills/adopt/SKILL.md" > "$DEST/SKILL.md"
echo "Installed $DEST (uses the template at $ROOT). In any repo: /danfactory-adopt"

#!/usr/bin/env bash
# Install (or update) an external on-demand skill listed in factory.json -> integrations.skills.
# Installed skills are git-ignored: pulled fresh when needed, never bloating the template.
# Usage: bash scripts/install-skill.sh <name> [ref]      e.g. security-audit, cloudflare-deploy
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:?usage: install-skill.sh <name> [ref]}"
read -r REPO REF SUBPATH < <(python3 - "$ROOT/factory.json" "$NAME" "${2:-}" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))["integrations"]["skills"].get(sys.argv[2])
if not s:
    sys.exit("unknown skill %r; add it to factory.json integrations.skills" % sys.argv[2])
print(s["repo"], sys.argv[3] or s["ref"], s["path"])
PY
)
DEST="$ROOT/.claude/skills/$NAME"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --quiet --depth 1 --filter=blob:none --sparse --branch "$REF" "$REPO" "$TMP/src"
git -C "$TMP/src" sparse-checkout set "$SUBPATH"
[ -f "$TMP/src/$SUBPATH/SKILL.md" ] || { echo "no SKILL.md at $SUBPATH" >&2; exit 1; }
rm -rf "$DEST"
cp -R "$TMP/src/$SUBPATH" "$DEST"
for lic in LICENSE LICENSE.txt LICENSE.md; do
  [ -f "$TMP/src/$lic" ] && [ ! -f "$DEST/$lic" ] && cp "$TMP/src/$lic" "$DEST/UPSTREAM-$lic"
done
echo "$NAME installed at .claude/skills/$NAME ($(git -C "$TMP/src" rev-parse --short HEAD))"

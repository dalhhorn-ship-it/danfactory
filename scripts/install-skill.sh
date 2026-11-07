#!/usr/bin/env bash
# Install (or update) an external on-demand skill listed in factory.json -> integrations.skills.
# Installed skills are git-ignored: pulled fresh when needed, never bloating the template.
# The entry's "ref" should be a full 40-hex commit SHA: it is fetched and verified (rev-parse HEAD).
# Unless the entry sets "model_invocable": true, the installed SKILL.md gets
# `disable-model-invocation: true` (scripts/skill_frontmatter.py), so it runs only through our wrapper
# skills (security-audit-run, ship) and never auto-triggers on loosely related requests.
# Usage: bash scripts/install-skill.sh <name> [ref]      e.g. security-audit, cloudflare-deploy
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:?usage: install-skill.sh <name> [ref]}"
[[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "install-skill: invalid skill name '$NAME'" >&2; exit 2; }
CONF="$(python3 -c '
import json, sys
s = json.load(open(sys.argv[1]))["integrations"]["skills"].get(sys.argv[2])
if not s:
    sys.exit("unknown skill %r; add it to factory.json integrations.skills" % sys.argv[2])
print(s["repo"], sys.argv[3] or s["ref"], s["path"], "yes" if s.get("model_invocable", False) else "no")
' "$ROOT/factory.json" "$NAME" "${2:-}")"
read -r REPO REF SUBPATH INVOCABLE <<<"$CONF"
DEST="$ROOT/.claude/skills/$NAME"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [[ "$REF" =~ ^[0-9a-f]{40}$ ]]; then
  git init --quiet "$TMP/src"
  git -C "$TMP/src" remote add origin "$REPO"
  git -C "$TMP/src" fetch --quiet --depth 1 --filter=blob:none origin "$REF"
  git -C "$TMP/src" sparse-checkout set "$SUBPATH"
  git -C "$TMP/src" checkout --quiet --detach FETCH_HEAD
  [ "$(git -C "$TMP/src" rev-parse HEAD)" = "$REF" ] || { echo "install-skill: fetched commit does not match pinned $REF" >&2; exit 1; }
else
  echo "install-skill: WARNING ref '$REF' is not a pinned commit SHA; pin it in factory.json" >&2
  git clone --quiet --depth 1 --filter=blob:none --sparse --branch "$REF" "$REPO" "$TMP/src"
  git -C "$TMP/src" sparse-checkout set "$SUBPATH"
fi
[ -f "$TMP/src/$SUBPATH/SKILL.md" ] || { echo "no SKILL.md at $SUBPATH" >&2; exit 1; }
STAGE="$TMP/stage"
cp -R "$TMP/src/$SUBPATH" "$STAGE"
if [ "$INVOCABLE" = "no" ]; then
  python3 "$ROOT/scripts/skill_frontmatter.py" "$STAGE/SKILL.md" || exit 1
fi
for lic in LICENSE LICENSE.txt LICENSE.md; do
  [ -f "$TMP/src/$lic" ] && [ ! -f "$STAGE/$lic" ] && cp "$TMP/src/$lic" "$STAGE/UPSTREAM-$lic"
done
rm -rf "$DEST"
cp -R "$STAGE" "$DEST"
echo "$NAME installed at .claude/skills/$NAME ($(git -C "$TMP/src" rev-parse --short HEAD), auto-invocable: $INVOCABLE)"

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
# Refuse in the template repo itself: the reset below deletes the template's own records.
if python3 -c "import sys; sys.path.insert(0, '.claude/hooks'); from _common import template_mode; sys.exit(0 if template_mode(root='.') else 1)"; then
  echo "bootstrap.sh refused: this is the danfactory template repo itself. Run it in a NEW repo made from the template." >&2
  exit 2
fi
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
# Clean records for the new project (TD-017): the template's own backlog, debt, PRDs, ADRs and learnings stay in the
# template repo (and its git history); they would mislead the dashboard, the PRD gate and the finder here.
python3 - <<'PY'
import glob, os, re
def rw(path, fn):
    t = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8").write(fn(t))
# BACKLOG: keep the format header and the M0 set-up milestone only
rw("docs/BACKLOG.md", lambda t: re.split(r"(?m)^## Milestone: M1\b", t)[0].rstrip("\n") + "\n")
# TECH-DEBT: keep the header, empty Open and Resolved
rw("docs/TECH-DEBT.md", lambda t: t.split("## Open")[0] + "## Open\n\n## Resolved\n")
# LEARNINGS: keep the format header; entries are the template's (new ones are appended by retro, upstream_learnings.py reads "### " entries)
rw("docs/operating-model/LEARNINGS.md", lambda t: t.split("## Entries")[0] + "## Entries\n")
for f in glob.glob("docs/specs/*.md"):
    if os.path.basename(f) != "_TEMPLATE.md":
        os.remove(f)
for f in glob.glob("docs/decisions/00*.md"):
    if os.path.basename(f) not in ("0000-template.md", "0001-use-danfactory-template.md"):
        os.remove(f)
PY
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

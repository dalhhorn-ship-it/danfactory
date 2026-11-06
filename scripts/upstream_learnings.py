#!/usr/bin/env python3
"""Send this project's general learnings back to the danfactory template.

  python3 scripts/upstream_learnings.py                       # list [upstream] entries not yet sent
  python3 scripts/upstream_learnings.py --template ../danfactory   # append them to the template's
                                                                   # LEARNINGS.md and show doc diffs

With --template it appends unsent entries to <template>/docs/operating-model/LEARNINGS.md, marks them
`[upstreamed]` here, and prints `diff` stats for DECISION-TREE.md, AGENT-ROUTING.md and paths/*.md, so
you can port the changes you want and open a PR in the template repo. It never overwrites template docs.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REL = "docs/operating-model/LEARNINGS.md"
ENTRY = re.compile(r"^### .*$\n(?:(?!^### ).*\n?)*", re.M)
SHARED = ["docs/operating-model/DECISION-TREE.md", "docs/operating-model/AGENT-ROUTING.md", "docs/operating-model/paths"]


def entries(text):
    return [m.group(0).rstrip() + "\n" for m in ENTRY.finditer(text)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", help="path to a local clone of the danfactory template repo")
    a = ap.parse_args()
    path = os.path.join(ROOT, REL)
    text = open(path, encoding="utf-8").read()
    todo = [e for e in entries(text) if "[upstream]" in e.splitlines()[0] and "[upstreamed]" not in e.splitlines()[0]]
    if not todo:
        print("no unsent [upstream] learnings")
    else:
        print("%d unsent [upstream] learning(s):\n" % len(todo))
        print("\n".join(e.splitlines()[0] for e in todo))
    if not a.template:
        return 0
    tpath = os.path.join(os.path.abspath(a.template), REL)
    if not os.path.isfile(tpath):
        print("not a danfactory template clone: %s" % a.template, file=sys.stderr)
        return 2
    if todo:
        project = os.path.basename(ROOT)
        with open(tpath, "a", encoding="utf-8") as fh:
            for e in todo:
                fh.write("\n" + e.replace("\n", " (from %s)\n" % project, 1))
        for e in todo:
            first = e.splitlines()[0]
            text = text.replace(first, first.replace("[upstream]", "[upstreamed]"), 1)
        open(path, "w", encoding="utf-8").write(text)
        print("\nappended to %s and marked [upstreamed] here" % tpath)
    print("\nShared docs that differ from the template (port by hand, then PR the template):")
    for rel in SHARED:
        r = subprocess.run(["diff", "-rq", os.path.join(a.template, rel), os.path.join(ROOT, rel)],
                           capture_output=True, text=True)
        print("  " + (r.stdout.strip().replace(os.path.abspath(a.template), "<template>").replace(ROOT, "<project>")
                      or "%s: identical" % rel))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""prepare-commit-msg helper: append `Refs: <ID>` when exactly one `[~]` backlog item exists. Never fails."""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def open_items(root):
    try:
        text = open(os.path.join(root, "docs", "BACKLOG.md"), encoding="utf-8").read()
    except OSError:
        return []
    return [m.group(1) for m in re.finditer(r"^\s*-\s*\[~\]\s*([A-Z][A-Z0-9]*-\d+)\b", text, re.M)]


def main(path, root=ROOT):
    msg = open(path, encoding="utf-8").read()
    if re.search(r"^(Refs|PRD-Exempt):", msg, re.M):
        return
    items = open_items(root)
    if len(items) == 1:
        subprocess.run(["git", "interpret-trailers", "--in-place", "--trailer", "Refs: " + items[0], path], check=False)
    else:
        sys.stderr.write("prepare-commit-msg: no Refs: added; in-progress items: %s\n" % (", ".join(items) or "none"))


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ROOT)
    except Exception as e:  # never block a commit
        sys.stderr.write("prepare-commit-msg: skipped (%s)\n" % e)

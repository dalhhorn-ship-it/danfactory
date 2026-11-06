#!/usr/bin/env python3
"""PostToolUse (Edit|Write|MultiEdit): regenerate docs/INDEX.md when a markdown doc changes."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, read_event  # noqa: E402


def main():
    ev = read_event()
    path = (ev.get("tool_input") or {}).get("file_path", "")
    if not path.endswith(".md") or path.endswith(os.path.join("docs", "INDEX.md")):
        return
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "docs_index.py"), "--quiet"],
                   cwd=ROOT, check=False)


if __name__ == "__main__":
    main()

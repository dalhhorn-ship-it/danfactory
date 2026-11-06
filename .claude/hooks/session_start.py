#!/usr/bin/env python3
"""SessionStart: inject a ~10-line status so every session knows the phase and next step."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, load_factory  # noqa: E402

NEXT = {
    "brainstorm": "No agreed goal yet. Run the `brainstorm` skill: interview the user, then write docs/GOAL.md.",
    "operating-model": "Goal agreed. Run the `choose-path` skill: walk docs/operating-model/DECISION-TREE.md and write docs/OPERATING-MODEL.md.",
    "build": "Operating model set. Follow docs/OPERATING-MODEL.md. Run `retro` at milestones.",
}


def main():
    f = load_factory()
    phase = f.get("phase", "brainstorm")
    paths = f.get("paths", {})
    out = [
        "[danfactory] phase=%s primary_path=%s secondary=%s"
        % (phase, paths.get("primary") or "-", ",".join(paths.get("secondary") or []) or "-"),
        "[danfactory] next: " + NEXT.get(phase, NEXT["build"]),
        "[danfactory] docs: read docs/INDEX.md first, then targeted reads (offset/limit). Never read whole large files.",
    ]
    report = os.path.join(ROOT, "metrics", "REPORT.md")
    if os.path.isfile(report):
        with open(report, encoding="utf-8") as fh:
            alerts = [l.strip() for l in fh if l.startswith("- ALERT")]
        if alerts:
            out.append("[danfactory] metric alerts (%d): %s" % (len(alerts), " | ".join(a[8:] for a in alerts[:3])))
    print("\n".join(out))


if __name__ == "__main__":
    main()

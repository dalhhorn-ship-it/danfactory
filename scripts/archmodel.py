#!/usr/bin/env python3
"""Architecture model CLI (feeds the dashboard Architecture tab).

  python3 scripts/archmodel.py --write   # refresh the `generated` part of docs/architecture.json (curated kept)
  python3 scripts/archmodel.py --print   # dump the model to stdout
"""
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obs import model  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--print", action="store_true", dest="show")
    a = ap.parse_args()
    if a.write:
        print("docs/architecture.json %s" % ("updated" if model.write(ROOT) else "unchanged"))
    if a.show or not a.write:
        old = model.load(ROOT) or {}
        print(model.dumps({"schema": 1, "curated": old.get("curated") or {}, "generated": model.generate(ROOT)}), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

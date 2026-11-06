"""Shared helpers for danfactory hooks. Stdlib only, Python 3.8+."""
import json
import os
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def load_factory():
    try:
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def read_event():
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}


def count_lines(path, stop_after=None):
    """Count lines, stopping early once stop_after is exceeded (cheap on huge files)."""
    n = 0
    try:
        with open(path, "rb") as fh:
            for _ in fh:
                n += 1
                if stop_after is not None and n > stop_after:
                    break
    except OSError:
        return 0
    return n


def block(reason):
    """Exit code 2 on PreToolUse blocks the call and shows `reason` to Claude."""
    sys.stderr.write(reason + "\n")
    sys.exit(2)

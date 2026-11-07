"""Shared helpers for danfactory hooks. Stdlib only, Python 3.8+."""
import json
import os
import re
import subprocess
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


def origin_slug(url):
    """'owner/repo' (lower-case) from an origin URL (https, ssh, scp-like or proxied path), else ''."""
    m = re.search(r"([^/:@\s]+)/([^/:@\s]+?)(?:\.git)?/*$", (url or "").strip())
    return ("%s/%s" % (m.group(1), m.group(2))).lower() if m else ""


def template_mode(root=None, factory=None):
    """True only when git remote `origin` points at factory.json template.source_repo.

    This is the template repo itself. Any error (no git, no remote, other repo) means project mode.
    Local git config only, no network. After renaming the template repo, update template.source_repo."""
    root = root or ROOT
    try:
        if factory is None:
            with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
                factory = json.load(fh)
        want = str((factory.get("template") or {}).get("source_repo") or "").strip().lower()
        if not want:
            return False
        p = subprocess.run(["git", "-C", root, "config", "--get", "remote.origin.url"],
                           capture_output=True, text=True, timeout=5, check=False)
        return p.returncode == 0 and origin_slug(p.stdout) == want
    except Exception:  # noqa: BLE001 - fail safe: project mode
        return False


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

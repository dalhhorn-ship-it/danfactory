#!/usr/bin/env python3
"""PreCompact (manual|auto): steer the compaction summary and save a mechanical snapshot.

On exit 0, stdout becomes extra instructions for the compaction summary (max 10,000 chars).
This hook prints what the summary must keep and points at .factory/HANDOFF.md as the source of
truth. If the note is missing or older than the last commit, it says so, so the summary records
the current step itself. It never blocks: every error is swallowed and the exit code is 0.

It also writes a snapshot block into the note (branch, uncommitted files, in-progress backlog
items, last commits), replacing the previous block so the file stays short. The note's mtime is
kept, so the snapshot never makes a stale note look fresh.
"""
import datetime
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, read_event  # noqa: E402

PATH = os.path.join(ROOT, ".factory", "HANDOFF.md")
REL = ".factory/HANDOFF.md"
START, END = "<!-- auto-snapshot:start -->", "<!-- auto-snapshot:end -->"
PLACEHOLDER = "_No agent-written note yet._"
MAX_CHARS = 10_000

KEEP = (
    "[danfactory] Compaction instructions. Keep: the user's goal and open questions; decisions and their "
    "reasons; files changed and commit shas; the current step and the next steps; failed approaches not to "
    "retry; user gates still pending. Drop: file contents, tool output, logs (they can be re-read).\n"
    "[danfactory] Source of truth: %s. It reloads after this compaction (SessionStart hook), so the summary "
    "should add what the note lacks, not repeat it." % REL
)


def git(*a):
    try:
        p = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def note_state():
    """'missing', 'stale' (older than the last commit) or 'fresh'."""
    if not os.path.isfile(PATH):
        return "missing"
    try:
        text = open(PATH, encoding="utf-8").read()
    except OSError:
        return "missing"
    body = text.split(START)[0].strip()
    if not body or PLACEHOLDER in body:
        return "missing"
    head = git("rev-parse", "HEAD")
    if not head:
        return "fresh"  # no git history to compare with
    if git("log", "-1", "--format=%H", "--", REL) == head:
        return "fresh"  # the note was committed with the latest work
    try:
        head_time = int(git("log", "-1", "--format=%ct") or 0)
    except ValueError:
        head_time = 0
    return "fresh" if os.path.getmtime(PATH) >= head_time else "stale"


def instructions(state):
    out = [KEEP]
    if state == "missing":
        out.append("[danfactory] %s is missing or empty: record the current step, the next steps and the "
                   "branch in the summary itself." % REL)
    elif state == "stale":
        out.append("[danfactory] %s is older than the last commit: record the current step and the work since "
                   "the note (commit shas) in the summary itself." % REL)
    return "\n".join(out)[:MAX_CHARS]


def write_snapshot(ev):
    try:
        backlog = open(os.path.join(ROOT, "docs", "BACKLOG.md"), encoding="utf-8").read()
    except OSError:
        backlog = ""
    doing = re.findall(r"^\s*[-*]\s+\[[~!]\]\s+(.*)$", backlog, re.M)[:6]
    status = git("status", "--short").splitlines()
    snap = [START, "## Auto snapshot before compaction (%s, %s)" % (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), ev.get("trigger", "?")),
        "- Branch: %s @ %s" % (git("rev-parse", "--abbrev-ref", "HEAD") or "?", git("rev-parse", "--short", "HEAD") or "?"),
        "- Uncommitted: %s" % (", ".join(l[3:] for l in status[:10]) + (" …" if len(status) > 10 else "") if status else "none"),
        "- In progress/blocked (BACKLOG): %s" % ("; ".join(doing) if doing else "none"),
        "- Last commits: %s" % " | ".join(git("log", "-3", "--format=%h %s").splitlines()),
        END]
    if os.path.islink(PATH) or os.path.islink(os.path.dirname(PATH)):
        return  # never write through a symlink
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    existed = os.path.exists(PATH)
    mtime = os.path.getmtime(PATH) if existed else None
    cur = open(PATH, encoding="utf-8").read() if existed else "# Handoff\n\n%s\n" % PLACEHOLDER
    if START in cur and END in cur:
        cur = cur[:cur.index(START)].rstrip() + "\n" + cur[cur.index(END) + len(END):].lstrip("\n")
    fd = os.open(PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(cur.rstrip() + "\n\n" + "\n".join(snap) + "\n")
    if mtime is not None:
        os.utime(PATH, (mtime, mtime))  # the snapshot is not an agent update


def main():
    try:
        ev = read_event()
    except Exception:  # noqa: BLE001 - never block a compaction
        ev = {}
    try:
        state = note_state()
    except Exception:  # noqa: BLE001
        state = "missing"
    print(instructions(state))
    try:
        write_snapshot(ev)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)

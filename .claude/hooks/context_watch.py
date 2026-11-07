#!/usr/bin/env python3
"""UserPromptSubmit: ask for a fresh handoff note when the context gets long, then keep working.

Short contexts with a structured handoff lose almost no accuracy and cost far less per token
(NVIDIA, "You don't need long context"). This hook reads the live context size from the
transcript (last assistant turn: input + cache read + cache write) and, once it passes
`budgets.context_handoff_tokens`, adds one reminder per 50k band, never on every prompt.
The agent decides the logical moment; the hook only says "it's time to look for one".

No hook, skill or model can run /clear or /compact. The reset is done by auto-compaction
(optionally started earlier by the operator, see docs/policies/token-economy.md); the note
written here is reloaded by session_start.py after it. So the hook never asks the user to /clear.
Once the context drops back under the budget (after a compaction), the band state is reset so
the next long stretch is nudged again.
"""
import json
import os
import re
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import load_factory, read_event  # noqa: E402

BAND = 50_000

MESSAGE = (
    "[danfactory] Context is ~{size:,} tokens (handoff budget {limit:,}). At the next logical boundary "
    "(task done, milestone, topic switch; never mid-debug or with half-applied changes): refresh "
    ".factory/HANDOFF.md with the `handoff` skill, commit it, then keep working on the task. "
    "Do not ask the user to /clear: auto-compaction resets the context and the note reloads after it."
)


def context_tokens(transcript_path):
    """Prompt size of the most recent assistant turn = current context size."""
    last = None
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") == "assistant" and not rec.get("isSidechain"):
                    last = (rec.get("message") or {}).get("usage") or last
    except OSError:
        return 0
    if not last:
        return 0
    return int(last.get("input_tokens", 0)) + int(last.get("cache_read_input_tokens", 0)) + \
        int(last.get("cache_creation_input_tokens", 0))


def state_dir():
    """Per-user private (0700, owned by us, not a symlink) dir for nudge state, or None."""
    uid = os.getuid() if hasattr(os, "getuid") else 0
    d = os.path.join(tempfile.gettempdir(), "danfactory-%d" % uid)
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        st = os.lstat(d)
    except OSError:
        return None
    if not stat.S_ISDIR(st.st_mode) or (hasattr(os, "getuid") and st.st_uid != uid) or st.st_mode & 0o077:
        return None
    return d


def safe_sid(sid):
    return re.sub(r"[^A-Za-z0-9-]", "", str(sid))[:128] or "unknown"


def main():
    ev = read_event()
    tp, sid = ev.get("transcript_path"), safe_sid(ev.get("session_id") or "unknown")
    if not tp:
        return
    limit = int(load_factory().get("budgets", {}).get("context_handoff_tokens", 120_000))
    size = context_tokens(tp)
    sdir = state_dir()
    if size < limit:
        if sdir is not None:  # back under budget (e.g. after a compaction): nudge again next time
            try:
                os.remove(os.path.join(sdir, "ctx-%s" % sid))  # unlink never follows a symlink target
            except OSError:
                pass
        return
    band = (size - limit) // BAND
    if sdir is None:
        return  # no safe place for state: stay silent rather than write somewhere shared
    state = os.path.join(sdir, "ctx-%s" % sid)
    flags = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(state, os.O_RDONLY | flags)
        with os.fdopen(fd) as fh:
            seen = int(fh.read().strip())
    except (OSError, ValueError):
        seen = -1
    if band <= seen:
        return
    try:
        fd = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | flags, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(str(band))
    except OSError:
        pass
    print(MESSAGE.format(size=size, limit=limit))


if __name__ == "__main__":
    main()

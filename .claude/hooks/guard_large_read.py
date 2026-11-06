#!/usr/bin/env python3
"""PreToolUse guard (Read + Bash): stop whole-file reads of large files in the MAIN context.

Pattern adapted from spotify/portal-ai-plugins `shunt` (Apache-2.0), re-targeted at native
Claude Code subagents instead of AiKA: big reads go to the `bulk-reader` subagent (cheap model,
disposable context), or to targeted reads (offset/limit, grep, codegraph).

Allowed through:
  * calls made inside a subagent (agent_id present) -- that context is disposable by design
  * targeted reads (offset/limit), small files, missing files
  * piped / redirected shell commands (already targeted or not read into context)
  * one-shot escape hatch: `touch .claude/.allow-large-read` (consumed by the next large read);
    FACTORY_ALLOW_LARGE_READ=1 in the environment disables the guard for a whole session
"""
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, block, count_lines, load_factory, read_event  # noqa: E402

READ_CMDS = {"cat", "head", "tail", "less", "more", "bat", "nl"}
HINT = (
    "{path} is {lines}+ lines (threshold {limit}). Don't pull it whole into the main context.\n"
    "Options, cheapest first:\n"
    "  1. Need an answer about it -> delegate to the `bulk-reader` subagent with a precise question.\n"
    "  2. Need code structure    -> codegraph (`codegraph explore \"<question>\"`) if enabled.\n"
    "  3. Need exact text to edit -> Grep for the spot, then Read with offset/limit.\n"
    "  4. Truly need it all (rare)  -> `touch .claude/.allow-large-read`, say why, retry once.\n"
    "See docs/policies/token-economy.md."
)


def threshold():
    try:
        return int(os.environ.get("FACTORY_LARGE_READ_LINES") or
                   load_factory().get("budgets", {}).get("large_read_lines", 350))
    except (TypeError, ValueError):
        return 350


def resolve(path, cwd):
    if not path:
        return ""
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) else os.path.join(cwd or os.getcwd(), path)


def bash_target(command, limit):
    """Return the file a shell command would dump into context (more than `limit` lines), else ''.

    Catches cat/less/more/bat/nl, `tail -n +K`, head/tail with a count over the limit, and
    `sed -n 'A,Bp'` ranges over the limit. Pipes/redirects are treated as targeted (known gap:
    `cat big | cat`); this is a guard against accidents, not a sandbox.
    """
    if re.search(r"[|>;&`]|\$\(", command):
        return ""
    try:
        parts = shlex.split(command)
    except ValueError:
        return ""
    if not parts:
        return ""
    prog, args = os.path.basename(parts[0]), parts[1:]
    files = [a for a in args if not a.startswith(("-", "+")) and not re.fullmatch(r"\d+", a)]
    if prog in {"cat", "less", "more", "bat", "nl"}:
        return files[0] if files else ""
    if prog in {"head", "tail"}:
        joined = " ".join(args)
        if re.search(r"(-n\s*\+|^\+|\s\+)\d+", joined) and prog == "tail":
            return files[-1] if files else ""  # tail -n +K: everything from line K
        m = re.search(r"(?:-n\s*|--lines[= ]|-)(\d+)", joined)
        count = int(m.group(1)) if m else 10
        return (files[-1] if files else "") if count > limit else ""
    if prog == "sed" and "-n" in args:
        m = re.search(r"(\d+)\s*,\s*(\d+|\$)\s*p", " ".join(args))
        if m:
            end = 10 ** 9 if m.group(2) == "$" else int(m.group(2))
            if end - int(m.group(1)) > limit:
                return files[-1] if len(files) > 1 else ""
        return ""
    return ""


ALLOW_ONCE = os.path.join(ROOT, ".claude", ".allow-large-read")


def allowed_once():
    """One-shot escape hatch: `touch .claude/.allow-large-read` (say why) allows the next large read."""
    if os.path.exists(ALLOW_ONCE):
        try:
            os.remove(ALLOW_ONCE)
        except OSError:
            pass
        return True
    return False


def main():
    if os.environ.get("FACTORY_ALLOW_LARGE_READ") == "1":
        return
    ev = read_event()
    if ev.get("agent_id"):
        return  # inside a subagent: big reads are what subagents are for
    tool = ev.get("tool_name")
    ti = ev.get("tool_input") or {}
    cwd = ev.get("cwd")
    if tool == "Read":
        if ti.get("offset") is not None or ti.get("limit") is not None:
            return
        path = resolve(ti.get("file_path", ""), cwd)
    elif tool == "Bash":
        path = resolve(bash_target(ti.get("command", ""), threshold()), cwd)
    else:
        return
    if not path or not os.path.isfile(path):
        return
    if re.search(r"\.(png|jpe?g|gif|webp|pdf|ipynb)$", path, re.I):
        return  # binary/visual reads are handled by Read itself
    limit = threshold()
    lines = count_lines(path, stop_after=limit)
    if lines > limit and not allowed_once():
        block(HINT.format(path=os.path.relpath(path, cwd or os.getcwd()), lines=limit, limit=limit))


if __name__ == "__main__":
    main()

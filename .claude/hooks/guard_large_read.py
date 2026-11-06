#!/usr/bin/env python3
"""PreToolUse guard (Read + Bash): stop whole-file reads of large files in the MAIN context.

Pattern adapted from spotify/portal-ai-plugins `shunt` (Apache-2.0), re-targeted at native
Claude Code subagents instead of AiKA: big reads go to the `bulk-reader` subagent (cheap model,
disposable context), or to targeted reads (offset/limit, grep, codegraph).

Allowed through:
  * calls made inside a subagent (agent_id present) -- that context is disposable by design
  * targeted reads (offset/limit), small files, missing files
  * piped / redirected shell commands (already targeted or not read into context)
  * FACTORY_ALLOW_LARGE_READ=1 escape hatch
"""
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import block, count_lines, load_factory, read_event  # noqa: E402

READ_CMDS = {"cat", "head", "tail", "less", "more", "bat", "nl"}
HINT = (
    "{path} is {lines}+ lines (threshold {limit}). Don't pull it whole into the main context.\n"
    "Options, cheapest first:\n"
    "  1. Need an answer about it -> delegate to the `bulk-reader` subagent with a precise question.\n"
    "  2. Need code structure    -> codegraph (`codegraph explore \"<question>\"`) if enabled.\n"
    "  3. Need exact text to edit -> Grep for the spot, then Read with offset/limit.\n"
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


def bash_target(command):
    """Return the file a plain `cat/head/tail file` command would dump, else ''."""
    if re.search(r"[|>;&`]|\$\(", command):
        return ""
    try:
        parts = shlex.split(command)
    except ValueError:
        return ""
    if not parts or os.path.basename(parts[0]) not in READ_CMDS:
        return ""
    # head/tail with an explicit small count are targeted reads
    if os.path.basename(parts[0]) in {"head", "tail"} and any(
        re.fullmatch(r"-\d+|-n|--lines(=\d+)?", p) for p in parts[1:]
    ):
        return ""
    for arg in parts[1:]:
        if not arg.startswith("-"):
            return arg
    return ""


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
        path = resolve(bash_target(ti.get("command", "")), cwd)
    else:
        return
    if not path or not os.path.isfile(path):
        return
    if re.search(r"\.(png|jpe?g|gif|webp|pdf|ipynb)$", path, re.I):
        return  # binary/visual reads are handled by Read itself
    limit = threshold()
    lines = count_lines(path, stop_after=limit)
    if lines > limit:
        block(HINT.format(path=os.path.relpath(path, cwd or os.getcwd()), lines=limit, limit=limit))


if __name__ == "__main__":
    main()

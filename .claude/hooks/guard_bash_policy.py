#!/usr/bin/env python3
"""PreToolUse (Bash): enforce deploy and git policy on the command text itself.

settings.json deny rules match command prefixes, so `bunx wrangler deploy`, `npm run deploy`
or `git push origin main --no-verify` slip through. This hook checks anywhere in the command
(including package.json scripts that wrap a deploy). Rollback stays allowed.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, block, read_event  # noqa: E402

DEPLOY = re.compile(r"\bwrangler\s+(pages\s+)?deploy\b")
RUN_SCRIPT = re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?([\w:.-]+)")
PUSH_NO_VERIFY = re.compile(r"\bgit\s+push\b[^;&|]*\s--no-verify\b")
COMMIT_NO_VERIFY = re.compile(r"\bgit\s+commit\b[^;&|]*\s(--no-verify|-n)\b")  # -n is --no-verify for commit only


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?^\s*\2\s*$", re.S | re.M)
QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")


def executable_text(cmd):
    """Drop heredoc bodies and quoted strings: text being written or echoed is not a command."""
    return QUOTED.sub("''", HEREDOC.sub("", cmd))


def package_scripts():
    try:
        with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as fh:
            return json.load(fh).get("scripts", {}) or {}
    except (OSError, ValueError):
        return {}


def main():
    ev = read_event()
    if ev.get("tool_name") != "Bash":
        return
    cmd = executable_text((ev.get("tool_input") or {}).get("command", ""))
    if DEPLOY.search(cmd) and not re.search(r"\s--dry-run\b", cmd):  # dry runs build locally, upload nothing
        block("Direct `wrangler deploy` is not allowed: production deploys go through git "
              "(push/merge to the production branch). See the `ship` skill. Rollback: `npx wrangler rollback`.")
    scripts = package_scripts()
    for name in RUN_SCRIPT.findall(cmd):
        if DEPLOY.search(scripts.get(name, "")):
            block("`%s` runs `wrangler deploy` (package.json script). Deploy via git instead (`ship` skill)." % name)
    if PUSH_NO_VERIFY.search(cmd) or COMMIT_NO_VERIFY.search(cmd):
        block("Skipping git hooks (--no-verify) is not allowed unless the user explicitly asks; "
              "fix the failing check instead.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Force `disable-model-invocation: true` in a SKILL.md frontmatter (used by install-skill.sh).

Handles CRLF, an existing key with any value, and fails (exit 1) when there is no frontmatter.
Usage: skill_frontmatter.py <SKILL.md>
"""
import re
import sys


def force_disable(text):
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.match(r"﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        raise ValueError("SKILL.md has no frontmatter; refusing to install a skill that cannot be locked")
    key = re.compile(r"^disable-model-invocation[ \t]*:")
    out, seen = [], False
    for ln in m.group(1).splitlines():
        if key.match(ln):
            if not seen:
                out.append("disable-model-invocation: true")
            seen = True
        else:
            out.append(ln)
    if not seen:
        out.append("disable-model-invocation: true")
    return "---" + nl + nl.join(out) + nl + "---" + nl + text[m.end():]


def main(path):
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    try:
        new = force_disable(text)
    except ValueError as exc:
        print("install-skill: %s" % exc, file=sys.stderr)
        return 1
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

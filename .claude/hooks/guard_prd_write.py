#!/usr/bin/env python3
"""PreToolUse guard (Edit, Write, MultiEdit, NotebookEdit, Bash): no approved PRD, no product code.

Bash commands are checked for literal-path writes to product paths (redirects, tee, sed/perl -i, cp/mv/install/ln,
truncate, dd of=, inline interpreter writes; see _shellwrites.py). Writes made by a generated program are not visible
here; the merge gate catches them. A `waiver` exemption must quote the user's words, else it is ignored.

Allows a write to a product path only when docs/BACKLOG.md has an in-progress item (`[~]`) linked to a
docs/specs/<slug>.md with `Status: approved`, or .factory/prd-exemption has a line dated today. docs/, issues/,
tests/acceptance/, metrics/, .factory/, factory.json and root *.md (except CLAUDE.md) are always allowed; .claude/
and CLAUDE.md are not. In project mode a phase before `build` blocks product writes (a `spike` exemption opens it).
Calls from subagents are not exempt. Fails open (with a warning) only on its own internal errors, never on a missing PRD.
Rules live in _prd.py (shared with scripts/gate.py). Policy: docs/policies/prd-approval.md."""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, block, load_factory, read_event, template_mode  # noqa: E402
import _prd  # noqa: E402

MSG = (
    "BLOCKED: this edit is not allowed, no approved PRD covers it ({path}).\n"
    "Missing: {why}.\n"
    "Ways forward:\n"
    "  1. Have `product-manager` write docs/specs/<slug>.md, get the user's explicit approval, set `Status: approved`,\n"
    "     link it from a docs/BACKLOG.md item and mark that item `[~]` (in progress). Then retry.\n"
    "  2. If this is a bug fix restoring approved behaviour, a chore, a user waiver or a requested spike, add one line to\n"
    "     .factory/prd-exemption: `{today} <bugfix|chore|waiver|spike>: <reason>` (valid today only, shows in the gate verdict).\n"
    "     A `waiver` must quote the user's own words: `{today} waiver: \"<user words>\" - <reason>`; unquoted waivers are\n"
    "     ignored, and \"quick job\" or \"just do it\" is not one.\n"
    "  3. Ask the user what to do.\n"
    "See docs/policies/prd-approval.md."
)
TOOL_KEYS = ("file_path", "notebook_path", "path")


def record(rel, why, agent):
    """Count the block for the dashboard (metrics/guard.local.jsonl, git-ignored). Never raises."""
    try:
        os.makedirs(os.path.join(ROOT, "metrics"), exist_ok=True)
        row = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "path": rel, "why": why[:120], "agent": bool(agent)}
        with open(os.path.join(ROOT, "metrics", "guard.local.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def main():
    try:
        ev = read_event()
        ti = ev.get("tool_input") or {}
        if ev.get("tool_name") == "Bash":
            import _shellwrites
            try:
                rels = _shellwrites.product_writes(str(ti.get("command") or ""), ROOT, ev.get("cwd"))
            except ValueError:  # unparseable quoting: nothing we can name, the gate still covers the commit
                rels = []
        else:
            raw = next((ti[k] for k in TOOL_KEYS if isinstance(ti.get(k), str) and ti[k]), "")
            rels = [_prd.rel_path(raw, ROOT, ev.get("cwd"))]
        factory = load_factory()
        ok, why, rel = True, "", ""
        for rel in rels:
            ok, why, _via = _prd.decide(ROOT, rel, str(factory.get("phase") or ""), template_mode(factory=factory))
            if not ok:
                break
    except Exception as ex:  # noqa: BLE001 - our own bug must not stop the user's work
        sys.stderr.write("guard_prd_write: internal error, allowing the edit (%s: %s)\n" % (type(ex).__name__, ex))
        return
    if not ok:
        record(rel, why, ev.get("agent_id"))
        block(MSG.format(path=rel, why=why, today=datetime.date.today().isoformat()))


if __name__ == "__main__":
    main()

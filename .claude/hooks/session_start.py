#!/usr/bin/env python3
"""SessionStart (startup|resume|clear|compact): inject a short status and the handoff note.

Every session knows the phase and next step. After a compaction (source "compact", manual or auto)
the note in .factory/HANDOFF.md is injected with one line that says to continue the task from it,
so the loop "handoff note, auto-compaction, continue" needs no human /clear. stdout is added to context.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, load_factory, read_event, template_mode  # noqa: E402

NEXT = {
    "brainstorm": "No agreed goal yet. Run the `brainstorm` skill: interview the user, then write docs/GOAL.md.",
    "operating-model": "Goal agreed. Run the `choose-path` skill: walk docs/operating-model/DECISION-TREE.md and write docs/OPERATING-MODEL.md.",
    "build": "Operating model set. Follow docs/OPERATING-MODEL.md. Run `retro` at milestones.",
}


HANDOFF = os.path.join(ROOT, ".factory", "HANDOFF.md")
HANDOFF_MAX_LINES = 60
COMPACTED = ("[danfactory] Context was compacted automatically; continue the task from this note; "
             "user gates still apply.")


GATES_MISSION = "PRD approval is by mission; pushes to main still need the user"


def mission_line():
    """One line about a valid active mission, else ''. Fails open on any error."""
    try:
        import _mission as mm
        m = mm.active(ROOT)
        if not m or mm.validate(ROOT, m):
            return ""
        st = mm.load_state(ROOT, m["slug"])
        nxt = mm.next_item(ROOT, m)
        return ("[danfactory] MISSION %s active on branch %s: continuations %d/%d, next: %s. Do not stop to ask "
                "(docs/policies/mission.md); %s." % (
                    m["slug"], m["branch"], int(st.get("continuations") or 0), m["caps"]["continuations"],
                    ("%s %s" % (nxt["id"], nxt.get("title", ""))).strip() if nxt else "nothing left (finish and report)",
                    GATES_MISSION))
    except Exception:  # noqa: BLE001
        return ""


def handoff_note(source, mission=False):
    """After /clear or a compaction (and on startup/resume) restart from task + note, not full history."""
    compacted = COMPACTED.replace("user gates still apply", GATES_MISSION) if mission else COMPACTED
    if not os.path.isfile(HANDOFF):
        if source == "compact":
            return ["", compacted.replace("from this note", "from the compaction summary (no handoff note yet)")]
        return []
    with open(HANDOFF, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if len(lines) > HANDOFF_MAX_LINES:
        lines = lines[:HANDOFF_MAX_LINES] + ["… (truncated: keep the note under 40 lines)"]
    head = ["", compacted] if source == "compact" else [""]
    return head + ["[danfactory] Handoff note (.factory/HANDOFF.md, loaded on %s). Continue from it; "
            "verify facts against the repo before relying on them:" % source] + lines


def main():
    ev = read_event()
    f = load_factory()
    ml = mission_line()
    if template_mode(factory=f):
        print("\n".join([
            "[danfactory] TEMPLATE repo: maintain the template; do not start or build a project here. "
            "Next: open tech debt (docs/TECH-DEBT.md), then the template backlog (docs/BACKLOG.md, Unplanned).",
            "[danfactory] docs: read docs/INDEX.md first, then targeted reads (offset/limit). Never read whole large files.",
            "[danfactory] test: python3 scripts/metrics.py test (runs .factory/tests).",
        ] + handoff_note(ev.get("source", "startup"), bool(ml)) + ([ml] if ml else [])))
        return
    phase = f.get("phase", "brainstorm")
    paths = f.get("paths", {})
    adopted = f.get("adopted")
    if adopted and phase == "brainstorm" and not os.path.exists(os.path.join(ROOT, "docs", "NEXT-BUILDS.md")):
        NEXT["brainstorm"] = ("Adopted from %s but adoption isn't finished: continue the danfactory `adopt` skill "
                              "(docs/ADOPTION-REPORT.md exists)." % adopted.get("from", "?"))
    elif adopted and phase == "brainstorm":
        NEXT["brainstorm"] = ("Adopted build: confirm the DRAFT docs/GOAL.md with the user (brainstorm skill), "
                              "using docs/ADOPTION-REPORT.md and docs/NEXT-BUILDS.md.")
    out = [
        "[danfactory] phase=%s primary_path=%s secondary=%s"
        % (phase, paths.get("primary") or "-", ",".join(paths.get("secondary") or []) or "-"),
        "[danfactory] next: " + NEXT.get(phase, NEXT["build"]),
        "[danfactory] docs: read docs/INDEX.md first, then targeted reads (offset/limit). Never read whole large files.",
    ]
    roster = (f.get("agents") or {}).get("roster") or []
    if roster:
        out.append("[danfactory] agents: %s (routing: docs/operating-model/AGENT-ROUTING.md)" % ", ".join(roster))
    report = os.path.join(ROOT, "metrics", "REPORT.md")
    if os.path.isfile(report):
        with open(report, encoding="utf-8") as fh:
            alerts = [l.strip() for l in fh if l.startswith("- ALERT")]
        if alerts:
            out.append("[danfactory] metric alerts (%d): %s" % (len(alerts), " | ".join(a[8:] for a in alerts[:3])))
    out += handoff_note(ev.get("source", "startup"), bool(ml)) + ([ml] if ml else [])
    print("\n".join(out))


if __name__ == "__main__":
    main()

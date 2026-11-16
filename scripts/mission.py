#!/usr/bin/env python3
"""Mission CLI (ADR 0012, docs/policies/mission.md): start | status | stop | report.

  mission.py start <slug> --go "<user words>" --title T --scope-in S --scope-out S --milestone M5 [--features N --usd X --hours H --continuations N]
  mission.py status [<slug>]     validity, caps used, next item, parked items
  mission.py stop <slug>         sets status: stopped (the hook then lets the agent finish)
  mission.py report <slug>       (re)writes docs/missions/<slug>-report.md
Stdlib only."""
import argparse
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import _mission as M  # noqa: E402

BRIEF = "(paste the brief as posted in chat)"


def _quote(words):
    words = words.strip()
    return words if re.match(r'^["“].*["”]$', words, re.S) else '"%s"' % words


def cmd_start(a, root):
    if not M.SLUG_RE.fullmatch(a.slug) or a.slug.endswith("-report"):
        return "bad slug: use [a-z0-9][a-z0-9-]* and not a name ending in -report"
    other = M.active(root)
    if other:
        return "refusing to start: mission %s is still active (stop it first)" % other["slug"]
    path = os.path.join(root, M.MISSIONS_DIR, a.slug + ".md")
    if os.path.exists(path):
        return "docs/missions/%s.md already exists" % a.slug
    go = _quote(a.go)
    if not M.go_valid(go):
        return 'the go must quote the user\'s words and give a clear yes (go, ok, yes, approve, build it)'
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    lines = ["slug: " + a.slug, "status: active", "go: " + go, "date: " + now.date().isoformat(),
             "started_at: " + now.isoformat().replace("+00:00", "Z"), "branch: mission/" + a.slug,
             "milestone: " + a.milestone, "features: %d" % a.features,
             "caps: usd=%g hours=%g continuations=%d" % (a.usd, a.hours, a.continuations),
             "scope_in: " + a.scope_in, "scope_out: " + a.scope_out]
    text = "# Mission: %s\n\n%s\n%s\n%s\n\n## Brief\n%s\n\n## Decision log\n" % (
        a.title, M.START, "\n".join(lines), M.END, a.brief or BRIEF)
    M._write_atomic(path, text)
    backlog = os.path.join(root, "docs", "BACKLOG.md")
    cur = M._read(backlog)
    if not cur.endswith("\n") and cur:
        cur += "\n"
    heading = "## Milestone: %s — %s (mission: %s)" % (a.milestone, a.title, a.slug)
    if not re.search(r"(?m)^##\s+Milestone:\s*%s(?![\w-])" % re.escape(a.milestone), cur):
        M._write_atomic(backlog, cur + "\n" + heading + "\n")
    print("mission %s written to docs/missions/%s.md; commit it now (the header is frozen from its first commit) and "
          "work on branch mission/%s." % (a.slug, a.slug, a.slug))
    return ""


def cmd_status(a, root):
    m = M.load(root, a.slug) if a.slug else M.active(root)
    if not m:
        print("no mission" + (" %s" % a.slug if a.slug else " is active"))
        return ""
    st = M.load_state(root, m["slug"])
    bad = M.validate(root, m)
    caps = m["caps"]
    print("mission %s: status %s, %s" % (m["slug"], m["status"], "valid" if not bad else "INVALID: " + bad))
    print("caps used: $%.2f/%g, %d/%d continuations, until %s (%g h)" % (
        M.spent(st), caps["usd"], st["continuations"], caps["continuations"],
        M.expires_at(m).strftime("%Y-%m-%dT%H:%MZ") if m["started_at"] else "?", caps["hours"]))
    hit = M.cap_hit(m, st)
    if hit:
        print("cap hit: " + hit)
    nxt = M.next_item(root, m)
    print("next: " + ("%s %s" % (nxt["id"], nxt["title"]) if nxt else "nothing left (all closed)"))
    for p in M.parked(root, m):
        print("parked: %s (%s)" % (p["ref"], p["why"]))
    return ""


def cmd_stop(a, root):
    m = M.load(root, a.slug)
    if not m:
        return "no mission " + a.slug
    M.set_status(root, a.slug, "stopped")
    print("mission %s set to stopped" % a.slug)
    return ""


def cmd_report(a, root):
    try:
        import mission_report
    except ImportError:
        return "scripts/mission_report.py is not installed yet"
    print(mission_report.write(root, a.slug, a.reason))
    return ""


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("slug")
    s.add_argument("--go", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--scope-in", required=True)
    s.add_argument("--scope-out", required=True)
    s.add_argument("--milestone", required=True)
    s.add_argument("--features", type=int, default=M.DEFAULTS["features"])
    s.add_argument("--usd", type=float, default=M.DEFAULTS["usd"])
    s.add_argument("--hours", type=float, default=M.DEFAULTS["hours"])
    s.add_argument("--continuations", type=int, default=M.DEFAULTS["continuations"])
    s.add_argument("--brief", default="")
    s = sub.add_parser("status")
    s.add_argument("slug", nargs="?")
    sub.add_parser("stop").add_argument("slug")
    s = sub.add_parser("report")
    s.add_argument("slug")
    s.add_argument("--reason", default="manual")
    a = ap.parse_args(argv)
    err = {"start": cmd_start, "status": cmd_status, "stop": cmd_stop, "report": cmd_report}[a.cmd](a, root)
    if err:
        print("mission: " + err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

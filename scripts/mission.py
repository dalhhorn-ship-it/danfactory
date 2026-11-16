#!/usr/bin/env python3
"""Mission CLI (ADR 0012, docs/policies/mission.md): start | status | stop | report.

  mission.py start <slug> --go "<user words>" --title T --scope-in S --scope-out S --milestone M5
                     [--brief TEXT|FILE] [--branch NAME] [--features N --usd X --hours H --continuations N]
                 needs phase build and a clean tree; creates and switches to branch mission/<slug>, writes the file (commit it next)
  mission.py status [<slug>]     validity, caps used, next item, parked items
  mission.py stop <slug>         sets status: stopped and writes the report (the hook then lets the agent finish)
  mission.py report <slug>       (re)writes docs/missions/<slug>-report.md; never changes the status
Stdlib only."""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import _mission as M  # noqa: E402

BRIEF = "(paste the brief as posted in chat)"


def _quote(words):
    words = words.strip()
    return words if re.match(r'^["“].*["”]$', words, re.S) else '"%s"' % words


def _git(root, *args):
    p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, timeout=30, check=False)
    return p.returncode, (p.stdout + p.stderr).strip()


def _prepare_branch(a, root):
    """Refuse on a dirty tree or a protected branch, then create and switch to the mission branch (never destructive).
    Returns (branch, error)."""
    import _gitmission
    import _common
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            factory = json.load(fh)
    except (OSError, ValueError):
        factory = {}
    phase = str(factory.get("phase") or "")
    if phase != "build" and not _common.template_mode(root, factory):
        return "", ("factory.json phase is '%s', not 'build': product work is not allowed yet. Finish the brainstorm and "
                    "operating-model steps first; a mission starts in the build phase" % (phase or "unset"))
    rc, head = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return "", "not a git repository with at least one commit (the mission file must be committed on a branch)"
    rc, dirty = _git(root, "status", "--porcelain")
    if dirty:
        return "", "the working tree has uncommitted changes: commit or stash them first (start never switches branches over them)"
    explicit = bool(a.branch)
    branch = a.branch or "mission/" + a.slug
    if branch in _gitmission.protected(root):
        return "", "%s is a protected branch: a mission must run on its own branch (default mission/%s)" % (branch, a.slug)
    if branch == head:
        return branch, ""
    exists = _git(root, "rev-parse", "--verify", "--quiet", "refs/heads/" + branch)[0] == 0
    if exists and not explicit:
        return "", "branch %s already exists: pick another slug, or pass --branch %s to reuse it" % (branch, branch)
    rc, out = _git(root, "switch", branch) if exists else _git(root, "switch", "-c", branch)
    if rc != 0:
        return "", "could not switch to %s: %s" % (branch, out)
    return branch, ""


def _brief(text):
    if text and "\n" not in text and os.path.isfile(text):
        return M._read(text).strip()
    return text


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
    branch, err = _prepare_branch(a, root)
    if err:
        return "refusing to start: " + err
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    lines = ["slug: " + a.slug, "status: active", "go: " + go, "date: " + now.date().isoformat(),
             "started_at: " + now.isoformat().replace("+00:00", "Z"), "branch: " + branch,
             "milestone: " + a.milestone, "features: %d" % a.features,
             "caps: usd=%g hours=%g continuations=%d" % (a.usd, a.hours, a.continuations),
             "scope_in: " + a.scope_in, "scope_out: " + a.scope_out]
    text = "# Mission: %s\n\n%s\n%s\n%s\n\n## Brief\n%s\n\n## Decision log\n" % (
        a.title, M.START, "\n".join(lines), M.END, _brief(a.brief) or BRIEF)
    M._write_atomic(path, text)
    backlog = os.path.join(root, "docs", "BACKLOG.md")
    cur = M._read(backlog)
    if not cur.endswith("\n") and cur:
        cur += "\n"
    heading = "## Milestone: %s — %s (mission: %s)" % (a.milestone, a.title, a.slug)
    if not re.search(r"(?m)^##\s+Milestone:\s*%s(?![\w-])" % re.escape(a.milestone), cur):
        M._write_atomic(backlog, cur + "\n" + heading + "\n")
    print("mission %s written to docs/missions/%s.md; commit it now (the header is frozen from its first commit) and "
          "work on branch %s (you are on it now)." % (a.slug, a.slug, branch))
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
    head = _git(root, "rev-parse", "--abbrev-ref", "HEAD")[1]
    if head != m["branch"]:
        print("HEAD is %s, not the mission branch %s: the Stop hook will not continue the mission here "
              "(git switch %s)" % (head or "unknown", m["branch"], m["branch"]))
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
    try:
        import mission_report
        print("report: " + os.path.relpath(mission_report.write(root, a.slug, "stopped", set_status=False), root))
    except Exception as ex:  # noqa: BLE001 - the stop itself worked; the report can be regenerated
        print("mission: stopped, but the report failed (%s); run `mission.py report %s`" % (ex, a.slug), file=sys.stderr)
    return ""


def cmd_report(a, root):
    try:
        import mission_report
    except ImportError:
        return "scripts/mission_report.py is not installed yet"
    print(mission_report.write(root, a.slug, a.reason, set_status=False))  # read-only on status
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
    s.add_argument("--milestone", required=True, help="the BACKLOG.md milestone the mission works through, e.g. M5; "
                   "its items (## Milestone: M5 ...) are the mission's work list and scope")
    s.add_argument("--features", type=int, default=M.DEFAULTS["features"])
    s.add_argument("--usd", type=float, default=M.DEFAULTS["usd"])
    s.add_argument("--hours", type=float, default=M.DEFAULTS["hours"])
    s.add_argument("--continuations", type=int, default=M.DEFAULTS["continuations"])
    s.add_argument("--brief", default="", help="the brief as posted in chat: the text itself, or a path to a file holding it "
                   "(default: a placeholder line to fill in)")
    s.add_argument("--branch", default="", help="use this branch (created if missing, or the current one) instead of "
                   "creating mission/<slug>; recorded in the header")
    s = sub.add_parser("status")
    s.add_argument("slug", nargs="?")
    sub.add_parser("stop").add_argument("slug")
    s = sub.add_parser("report")
    s.add_argument("slug")
    s.add_argument("--reason", default="", help="why it ended (done|stopped|wall-clock|budget|continuations); default: inferred")
    a = ap.parse_args(argv)
    err = {"start": cmd_start, "status": cmd_status, "stop": cmd_stop, "report": cmd_report}[a.cmd](a, root)
    if err:
        print("mission: " + err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

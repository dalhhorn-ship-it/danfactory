#!/usr/bin/env python3
"""Morning report for a mission (ADR 0012, MISSION-4). Stdlib only.

  python3 scripts/mission_report.py <slug> [--reason done|stopped|wall-clock|budget|continuations]

`write(root, slug, reason)` writes docs/missions/<slug>-report.md and returns its absolute path. The report is derived from
the mission file, the backlog, .factory/mission-state.json, git and metrics/gate.local.jsonl, so it can be regenerated at
any time (reason '' = take it from the state file, else infer it from the backlog). `write` sets the mission status (`done` or
`stopped`) only for the Stop hook and `mission.py stop`; this CLI and `mission.py report` never change the status.
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
import _mission  # noqa: E402

CAPS = {"wall-clock": "the wall-clock cap", "budget": "the budget cap", "continuations": "the continuation cap"}
LOG_RE = re.compile(r"^\s*[-*]\s+(\d{4}-\d{2}-\d{2})\s+(Assumption|Parked):\s*(.*)$", re.I)


def report_path(root, slug):
    return os.path.join(root, "docs", "missions", slug + "-report.md")


def _read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def decision_log(root, m):
    """[(date, kind, text)] from the `## Decision log` section of the mission file."""
    text = _read(root, os.path.relpath(m["path"], root)) if m.get("path") else ""
    out, on = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            on = ln[3:].strip().lower() == "decision log"
        elif on:
            x = LOG_RE.match(ln)
            if x:
                out.append((x.group(1), x.group(2).capitalize(), x.group(3).strip()))
    return out


def gate_rows(root, since):
    """Rows of metrics/gate.local.jsonl at or after `since` (aware datetime); rows without a readable ts are skipped."""
    out = []
    for ln in _read(root, "metrics/gate.local.jsonl").splitlines():
        try:
            r = json.loads(ln)
            ts = datetime.datetime.fromisoformat(str(r["ts"]).replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        if isinstance(r, dict) and ts >= since:
            out.append((ts, r))
    return out


def resolve_reason(reason, state, its):
    """The reason the mission ended: the argument, else state.ended.reason, else done when nothing is open, else stopped."""
    if reason:
        return reason
    ended = (state or {}).get("ended") or {}
    if ended.get("reason"):
        return ended["reason"]
    if its and all(i["state"] in "x!-" for i in its):
        return "done"
    return "stopped"


def verdict(reason, parked_n):
    if reason == "done":
        return "Verdict: done with parked items (%d)." % parked_n if parked_n else "Verdict: done."
    if reason in CAPS:
        return "Verdict: stopped at %s (%s)." % (reason, CAPS[reason])
    return "Verdict: stopped by the user (status stopped)."


def _usd(v):
    return "$%.2f" % v if isinstance(v, (int, float)) else "unknown"


def build(root, m, reason, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    state = _mission.load_state(root, m["slug"]) or {}
    its = _mission.items(root, m) or []
    reason = resolve_reason(reason, state, its)
    log = decision_log(root, m)
    pk = _mission.parked(root, m) or []
    park = ["%s: %s" % (p.get("ref"), p.get("why")) for p in pk] + ["%s: %s" % (d, t) for d, k, t in log if k == "Parked"]
    parked_n = len(park)
    ended = state.get("ended") or {}
    try:
        end = datetime.datetime.fromisoformat(str(ended["ts"]).replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError):
        end = now
    if end.tzinfo is None:
        end = end.replace(tzinfo=datetime.timezone.utc)
    start = m["started_at"]
    hours = max(0.0, (end - start).total_seconds() / 3600.0)
    caps = m["caps"]

    L = ["# Mission report: %s" % m["slug"], "", verdict(reason, parked_n), "",
         "Go words recorded in the mission file (check them against the chat; the agent wrote them): %s" % (m.get("go") or "?"),
         "", "Mission: %s (milestone %s, branch `%s`)." % (m.get("title") or m["slug"], m.get("milestone") or "?",
                                                         m.get("branch") or "?"), ""]

    L += ["## Shipped", ""]
    done = [i for i in its if i["state"] in "xX"]
    L += ["- [x] %s %s" % (i["id"], i["title"]) for i in done] or ["- Nothing shipped."]
    feats = []
    for i in its:
        for s in i.get("slugs") or []:
            if s not in feats:
                feats.append(s)
    L += ["", "Feature list (PM's choice, cap %s): %s" % (m.get("features"), ", ".join("`%s`" % s for s in feats) or "none")]

    L += ["", "## Assumptions", ""]
    L += ["- %s: %s" % (d, t) for d, k, t in log if k == "Assumption"] or ["- None recorded."]

    L += ["", "## Parked", ""]
    L += ["- " + x for x in park] or ["- Nothing parked."]

    sess = state.get("sessions") or {}
    total = sum(v for v in sess.values() if isinstance(v, (int, float)))
    L += ["", "## Cost", ""]
    if sess:
        L += ["- session `%s`: %s" % (k, _usd(v)) for k, v in sorted(sess.items())]
        L.append("- Total: %s of the %s cap (estimate from the transcript, not a bill)." % (_usd(total), _usd(caps.get("usd"))))
    else:
        L.append("- Spend unknown: no session usage was recorded. The continuation cap still binds.")
    L.append("- Continuations: %s of %s." % (state.get("continuations", 0), caps.get("continuations")))

    L += ["", "## Time", "",
          "- Start: %s" % start.strftime("%Y-%m-%dT%H:%M:%SZ"),
          "- End: %s" % end.strftime("%Y-%m-%dT%H:%M:%SZ"),
          "- Hours: %.1f of the %s cap." % (hours, caps.get("hours"))]

    rows = gate_rows(root, start)
    L += ["", "## Gate verdicts", ""]
    if rows:
        L += ["| time (UTC) | verdict | sha | codes |", "|---|---|---|---|"]
        L += ["| %s | %s | %s | %s |" % (ts.strftime("%Y-%m-%d %H:%M"), r.get("verdict", "?"), str(r.get("sha") or "?")[:10],
                                       ", ".join(r.get("codes") or []) or "-") for ts, r in rows]
    else:
        L.append("No gate runs recorded since the start (metrics/gate.local.jsonl is local to the machine).")
    return "\n".join(L) + "\n", reason


def write(root, slug, reason="", set_status=True):
    """Write docs/missions/<slug>-report.md, return the report's path. set_status (the Stop hook, `mission.py stop`): also set
    the mission status (done or stopped); False (regenerating a report) leaves the status alone."""
    m = _mission.load(root, slug)
    if m is None:
        raise ValueError("no such mission: %s" % slug)
    text, reason = build(root, m, reason)
    path = report_path(root, slug)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    if set_status:
        _mission.set_status(root, slug, "done" if reason == "done" else "stopped")
    return path


def main(argv=None, root=ROOT):
    a = list(sys.argv[1:] if argv is None else argv)
    reason = ""
    if "--reason" in a:
        i = a.index("--reason")
        reason = a[i + 1] if i + 1 < len(a) else ""
        del a[i:i + 2]
    if len(a) != 1:
        print(__doc__)
        return 2
    try:
        print(os.path.relpath(write(root, a[0], reason, set_status=False), root))
    except ValueError as ex:
        print(ex, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

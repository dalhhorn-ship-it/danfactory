#!/usr/bin/env python3
"""Learning from gate rejections (ADR 0010, C7). Reads metrics/runner.jsonl (fixer attempts, reason codes) and
metrics/gate.local.jsonl (gate verdicts) and writes metrics/LEARN.md (gitignored): failure codes per week, first-try
pass rate per week, and candidate rules, the codes that recur at least `autonomy.learn_threshold` times (default 3)
inside `autonomy.learn_window_days` (default 14), with example attempts. The retro skill reads it; a human turns a
candidate into a rule through the normal PRD gate. Nothing here calls a model or the network.

  python3 scripts/learn.py report [--root DIR] [--threshold N] [--window DAYS] [--rows FILE ...] [--no-write]
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNNER = "metrics/runner.jsonl"
GATE = "metrics/gate.local.jsonl"
OUT = "metrics/LEARN.md"
DEFAULTS = {"learn_threshold": 3, "learn_window_days": 14, "staging_branch": "staging"}
EMPTY = "No runner or gate-rejection data yet: nothing to learn from (docs/policies/runner.md, Learning)."
EXAMPLES = 3


def settings(root):
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            cfg = json.load(fh).get("autonomy") or {}
    except (OSError, ValueError):
        cfg = {}
    return {**DEFAULTS, **cfg}


def _jsonl(lines, dedupe=True):
    out, seen = [], set()
    for ln in lines:
        if not ln.strip() or (dedupe and ln in seen):  # runner rows repeat when working tree and staging both hold them
            continue
        seen.add(ln)
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def load(root, staging=None, rows_files=None):
    """(runner rows, gate rows). Runner rows come from the working tree and the committed copy on staging."""
    lines = []
    for p in rows_files or [os.path.join(root, RUNNER)]:
        lines += _read(p)
    if staging and not rows_files:
        p = subprocess.run(["git", "show", "%s:%s" % (staging, RUNNER)], cwd=root, capture_output=True, text=True, check=False)
        if p.returncode == 0:
            lines += p.stdout.splitlines()
    return _jsonl(lines), _jsonl(_read(os.path.join(root, GATE)), dedupe=False)


def _ts(v):
    try:
        d = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def week(d):
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def analyze(root, threshold=None, window=None, rows_files=None):
    cfg = settings(root)
    threshold = int(threshold if threshold is not None else cfg["learn_threshold"])
    window = int(window if window is not None else cfg["learn_window_days"])
    rrows, grows = load(root, cfg["staging_branch"], rows_files)
    att = [r for r in rrows if r.get("kind") == "attempt"]
    events = []  # (when, source, code, example)
    for r in att:
        d = _ts(r.get("ts"))
        for c in r.get("codes") or []:
            if d:
                events.append((d, "runner", str(c), "%s attempt %s (run %s, %s)" % (
                    r.get("issue", "?"), r.get("attempt", "?"), r.get("run", "?"), r.get("ts"))))
    for r in grows:
        d = _ts(r.get("ts"))
        if r.get("verdict") == "fail" and d:
            for c in r.get("codes") or []:
                events.append((d, "gate", str(c), "gate fail on %s (base %s, %s)" % (r.get("sha") or "?", r.get("base") or "none", r.get("ts"))))
    events.sort(key=lambda e: e[0])
    per_week = {}
    for d, _s, c, _x in events:
        wk = per_week.setdefault(week(d), {})
        wk[c] = wk.get(c, 0) + 1
    totals = {}
    for _d, s, c, _x in events:
        totals[(s, c)] = totals.get((s, c), 0) + 1
    cands = []
    for (s, c), n in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])):
        ev = [e for e in events if e[1] == s and e[2] == c]
        best, lo = 0, 0
        for hi in range(len(ev)):  # most hits inside any `window`-day span
            while (ev[hi][0] - ev[lo][0]).total_seconds() > window * 86400:
                lo += 1
            best = max(best, hi - lo + 1)
        if best >= threshold:
            cands.append({"source": s, "code": c, "total": n, "in_window": best, "first": ev[0][0].date().isoformat(),
                          "last": ev[-1][0].date().isoformat(), "examples": [e[3] for e in ev[-EXAMPLES:]]})
    groups = {}
    for r in att:
        groups.setdefault((r.get("run"), r.get("issue")), []).append(r)
    fixed = [g for g in groups.values() if any(x.get("outcome") == "merged" for x in g)]
    spend = sum(float(r.get("cost_usd") or 0) for r in rrows if r.get("kind") in ("attempt", "second-reading"))
    trend = {}
    for g in groups.values():
        first = [x for x in g if x.get("attempt") == 1]
        d = _ts(first[0].get("ts")) if first else None
        if not d:
            continue
        t = trend.setdefault(week(d), [0, 0])
        t[0] += 1
        t[1] += 1 if first[0].get("outcome") == "merged" else 0
    ft = [(w, p, n) for w, (n, p) in sorted(trend.items())]
    return {"exists": bool(att or events), "threshold": threshold, "window": window, "attempts": len(att), "rejections": len(events),
            "per_week": {w: per_week[w] for w in sorted(per_week)}, "candidates": cands,
            "first_try": [{"week": w, "passed": p, "issues": n, "rate": p / n} for w, p, n in ft],
            "first_try_rate": (sum(p for _w, p, _n in ft) / sum(n for _w, _p, n in ft)) if ft else None,
            "fixed": len(fixed), "rework_per_fixed": (sum(len(g) - 1 for g in fixed) / len(fixed)) if fixed else None,
            "cost_per_fixed": (spend / len(fixed)) if fixed else None}


def markdown(a):
    pct = lambda v: "n/a" if v is None else "%d%%" % round(100 * v)  # noqa: E731
    o = ["# Learning from gate rejections", "",
         "> Generated by `python3 scripts/learn.py report` (gitignored). Candidates are suggestions: a human turns one into a rule "
         "through the PRD gate (docs/policies/runner.md, Learning).", ""]
    if not a["exists"]:
        return "\n".join(o + [EMPTY, ""])
    o += ["%d attempt(s), %d rejection code(s) recorded; first-try pass rate %s; %d issue(s) fixed." %
          (a["attempts"], a["rejections"], pct(a["first_try_rate"]), a["fixed"]), "",
          "## Candidate rules (at least %d in %d days)" % (a["threshold"], a["window"]), ""]
    if not a["candidates"]:
        o.append("None: no code recurs that often.")
    for c in a["candidates"]:
        o.append("- `%s` (%s): %d total, %d within %d days, %s to %s" % (c["code"], c["source"], c["total"], c["in_window"], a["window"],
                                                                         c["first"], c["last"]))
        o += ["  - " + x for x in c["examples"]]
    o += ["", "## Codes per week", ""]
    codes = sorted({c for w in a["per_week"].values() for c in w})
    if codes:
        o += ["| week | " + " | ".join(codes) + " |", "|---|" + "---|" * len(codes)]
        o += ["| %s | %s |" % (w, " | ".join(str(a["per_week"][w].get(c, 0)) for c in codes)) for w in a["per_week"]]
    else:
        o.append("No rejection codes.")
    o += ["", "## First-try pass per week", ""]
    o += ["- %s: %d of %d issue(s) (%s)" % (t["week"], t["passed"], t["issues"], pct(t["rate"])) for t in a["first_try"]] or ["No attempts."]
    return "\n".join(o) + "\n"


def human(a):
    if not a["exists"]:
        return EMPTY
    return "learn: %d rejection code(s) over %d attempt(s), %d candidate rule(s)%s" % (
        a["rejections"], a["attempts"], len(a["candidates"]),
        (": " + ", ".join(c["code"] for c in a["candidates"][:4])) if a["candidates"] else "")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="write metrics/LEARN.md and print a summary")
    r.add_argument("--root", default=ROOT)
    r.add_argument("--threshold", type=int)
    r.add_argument("--window", type=int, help="days")
    r.add_argument("--rows", nargs="+", help="read these runner row files instead of metrics/runner.jsonl")
    r.add_argument("--no-write", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as ex:
        return 0 if ex.code in (0, None) else 2
    res = analyze(os.path.abspath(a.root), a.threshold, a.window, a.rows)
    md = markdown(res)
    if not a.no_write:
        path = os.path.join(os.path.abspath(a.root), OUT)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
    print(human(res))
    for c in res["candidates"]:
        print("  candidate %s [%s]: %d in %d days" % (c["code"], c["source"], c["in_window"], res["window"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

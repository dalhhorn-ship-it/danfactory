"""Cumulative flow of backlog items for the Evals tab (EVAL-5): todo / doing / done / done and covered by a passing eval.

Dates come from git history of docs/BACKLOG.md (item first appears = todo, first commit with `Refs: <id>` = doing, first
commit that has it ticked = done) and are approximate: a tick commit may batch items. Covered = a task whose task.json
`covers` lists the item has, as of that date, a latest run set with pass rate >= 1 - regression_threshold.
Pure and offline; no git history (template copy, shallow clone) yields ok=False. Nothing here raises on bad data.
"""
import datetime
import re

from . import sources as S
from . import trace

LINE_RE = re.compile(r"^\s*[-*]\s*\[([ xX~!-])\]\s*(.*)$")
MAX_COMMITS = 300


def parse_backlog(text):
    """{id: (state, title)} for items whose title starts with an ID (ABC-n); dropped items are left out."""
    out = {}
    for ln in (text or "").splitlines():
        m = LINE_RE.match(ln)
        if not m:
            continue
        i = S.ID_RE.match(m.group(2).strip())
        if i and m.group(1) != "-":
            out.setdefault(i.group(1), ("done" if m.group(1) in "xX" else "open", m.group(2).strip()[len(i.group(1)):].strip()))
    return out


def history(root, today):
    """({id: {title, todo, doing, done}}, ok). Dates are YYYY-MM-DD strings or None; doing/done are clamped in order."""
    raw = S.git(root, "log", "--reverse", "-n%d" % MAX_COMMITS, "--format=%H %cs", "--", "docs/BACKLOG.md")
    commits = [ln.split() for ln in raw.splitlines() if len(ln.split()) == 2]
    items = {}
    for sha, day in commits:
        for iid, (state, title) in parse_backlog(S.git(root, "show", "%s:docs/BACKLOG.md" % sha)).items():
            it = items.setdefault(iid, {"title": title, "todo": day, "doing": None, "done": None})
            it["title"] = title
            if state == "done" and not it["done"]:
                it["done"] = day
    now = parse_backlog(S.read(root, "docs/BACKLOG.md"))
    if not commits and not now:
        return {}, False
    for iid, (state, title) in now.items():  # uncommitted working-tree edits count as today
        it = items.setdefault(iid, {"title": title, "todo": today, "doing": None, "done": None})
        it["title"] = title
        if state == "done" and not it["done"]:
            it["done"] = today
        if state == "open":
            it["done"] = None  # un-ticked later
    items = {k: v for k, v in items.items() if k in now}  # removed or dropped items are not counted
    log = S.git(root, "log", "--reverse", "-n%d" % MAX_COMMITS, "--format=%x1e%cs%x1f%s%x1f%b")
    for rec in log.split("\x1e")[1:]:
        p = rec.split("\x1f")
        if len(p) < 3:
            continue
        for k in trace.ref_keys(p[1] + "\n" + p[2]):
            if k in items and not items[k]["doing"]:
                items[k]["doing"] = p[0].strip()
    for it in items.values():
        d = it["doing"] or it["done"]
        if d:  # first ref before the item existed (or after the tick) is clamped into [todo, done]
            d = max(d, it["todo"])
            it["doing"] = min(d, it["done"]) if it["done"] else d
        if it["done"]:
            it["done"] = max(it["done"], it["todo"])
            it["doing"] = it["doing"] or it["done"]
    return items, True


def _passes(rows, tid, upto, need):
    """Latest run set of the task with ts date <= upto passes at `need`, else None when the task has no set by then."""
    sets = []
    for r in rows:
        if r.get("error") or r.get("task") != tid:
            continue
        if r["set"] not in [s[0] for s in sets]:
            sets.append([r["set"], 0, 0, ""])
        s = next(s for s in sets if s[0] == r["set"])
        s[1] += 1
        s[2] += bool(r.get("pass"))
        s[3] = max(s[3], str(r.get("ts") or "")[:10])
    sets = [s for s in sets if s[3] and s[3] <= upto]
    if not sets:
        return None
    last = max(sets, key=lambda s: s[3])
    return last[2] / last[1] >= need


def build(items, ok, tasks, rows, threshold, today):
    """Cumulative counts per event date. Bands sum to the item total on every date."""
    ids = set(items)
    warnings = sorted({"%s covers unknown backlog id %s" % (t["id"], c) for t in tasks for c in t["covers"] if c not in ids}) if ok else []
    out = {"ok": ok, "total": len(items), "points": [], "warnings": warnings, "dates": 0, "approx": True,
           "covered_ids": [], "today": today}
    if not items:
        return out
    need = 1.0 - threshold
    cover = {}
    for t in tasks:
        for c in t["covers"]:
            if c in ids:
                cover.setdefault(c, []).append(t["id"])
    days = {today}
    for it in items.values():
        days.update(d for d in (it["todo"], it["doing"], it["done"]) if d)
    days.update(str(r.get("ts") or "")[:10] for r in rows if cover and r.get("ts"))
    days = sorted(d for d in days if re.match(r"^\d{4}-\d\d-\d\d$", d))
    for d in days:
        c = {"todo": 0, "doing": 0, "done": 0, "covered": 0}
        for iid, it in items.items():
            if it["todo"] > d:
                continue
            if it["done"] and it["done"] <= d:
                cov = any(_passes(rows, tid, d, need) for tid in cover.get(iid, []))
                c["covered" if cov else "done"] += 1
            elif it["doing"] and it["doing"] <= d:
                c["doing"] += 1
            else:
                c["todo"] += 1
        # the top edge is the number of items that exist on that date (the backlog grows), so bands sum to it
        out["points"].append({"date": d, **c, "sum": sum(c.values())})
    out["dates"] = len({p["date"] for p in out["points"] if p["sum"]})
    last = out["points"][-1] if out["points"] else None
    out["covered_ids"] = sorted(i for i in cover if items[i]["done"] and any(_passes(rows, t, today, need) for t in cover[i]))
    out["last"] = last
    return out


def collect(root, tasks, rows, threshold, today=None):
    today = today or datetime.date.today().isoformat()
    try:
        items, ok = history(root, today)
        return build(items, ok, tasks, rows, threshold, today)
    except Exception as ex:  # git or parse trouble must not break the tab
        return {"ok": False, "total": 0, "points": [], "warnings": [], "dates": 0, "error": "%s: %s" % (type(ex).__name__, ex)}

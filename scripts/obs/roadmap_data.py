"""Data for the Roadmap sub-views (DASH-4): 6-month timeline, proposed Gantt, releases. Pure and offline.

Inputs are the parsed BACKLOG milestones (dashboard.parse_backlog), today's date and the `dashboard` block of factory.json.
Actual dates come from evals_flow.history() (first `Refs:` commit = start, tick commit = done); estimates come from item
sizes. Nothing here raises on bad data: missing git, tags or dates yield empty results the renderer words as empty states.
"""
import datetime
import math
import re

from . import evals_flow
from . import sources as S

VIEWS = ("sequence", "months", "gantt", "releases")
DEFAULT_DAYS = {"S": 1, "M": 3, "L": 8}
TAG_RE = re.compile(r"^v(\d+)\.(\d+)(?:\.(\d+))?$")
ID_RE = S.ID_RE
GANTT_CAP_DAYS = 365   # estimated plan is drawn up to a year ahead, then "continues beyond"
GANTT_BACK_DAYS = 60   # actual history is drawn at most two months back
DONE_ROWS = 15         # newest done items drawn as rows; the rest is counted


def d2s(d):
    return d.isoformat() if d else ""


def parse_day(s):
    try:
        return datetime.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def settings(conf):
    conf = conf if isinstance(conf, dict) else {}
    view = conf.get("roadmap_view")
    days = dict(DEFAULT_DAYS)
    over = conf.get("size_days")
    for k, v in (over.items() if isinstance(over, dict) else []):
        if k in days and isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            days[k] = int(v) if float(v).is_integer() else v
    wip = conf.get("wip")
    return {"view": view if view in VIEWS else "sequence", "size_days": days,
            "wip": wip if isinstance(wip, int) and not isinstance(wip, bool) and wip >= 1 else 1}


def short(title, n=56):
    t = re.split(r"\s+AC:|[:,;]\s|\s\(", title, maxsplit=1)[0].strip().rstrip(".:,; ")
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def flat_items(milestones):
    """Backlog items in file order: id, short title, state, size, release, after, milestone. Dropped items are left out."""
    out = []
    for ms in milestones:
        for it in ms.get("items", []):
            if it.get("state") == "dropped":
                continue
            m = ID_RE.match(it["title"])
            iid = m.group(1) if m else ""
            title = it["title"][len(iid):].strip() if iid else it["title"]
            out.append({"id": iid, "title": title, "short": short(title), "state": it["state"], "size": it.get("size", ""),
                        "release": it.get("release") or ms.get("release", ""), "after": it.get("after", ""),
                        "ms": ms["name"], "label": iid or short(title, 12)})
    return out


# ---------------------------------------------------------------- 6-month timeline

def add_months(d, n):
    m = d.month - 1 + n
    return datetime.date(d.year + m // 12, m % 12 + 1, 1)


def months(items, milestones, today, hist, hist_ok):
    start = add_months(datetime.date(today.year, today.month, 1), -1)
    cols = [add_months(start, i) for i in range(6)]
    end = add_months(start, 6)
    targets = [(ms["name"], parse_day(ms.get("target"))) for ms in milestones if ms.get("target")]
    targets = [(n, d) for n, d in targets if d]
    done, undated, earlier = [], [], 0
    for it in items:
        if it["state"] != "done":
            continue
        d = parse_day((hist.get(it["id"]) or {}).get("done")) if hist_ok and it["id"] else None
        if not d:
            undated.append(it)
        elif d < start:
            earlier += 1
        elif d < end:
            done.append(dict(it, date=d))
    done.sort(key=lambda x: x["date"])
    return {"start": start, "end": end, "cols": cols, "today": today,
            "targets_in": [(n, d) for n, d in targets if start <= d < end],
            "targets_out": [(n, d) for n, d in targets if not start <= d < end],
            "any_target": bool(targets), "done": done, "undated": undated, "earlier": earlier,
            "unscheduled": [it for it in items if it["state"] != "done"]}


# ---------------------------------------------------------------- Gantt

def next_workday(d):
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


def finish_after(start, n):
    """Date after `n` working days starting on working day `start` (calendar axis, weekends skipped)."""
    d, worked = start, 0
    while True:
        if d.weekday() < 5:
            worked += 1
        d += datetime.timedelta(days=1)
        if worked >= n:
            return d


def schedule(open_items, today, size_days, wip):
    """Sequential estimate with `wip` parallel slots. Blocked items go after unblocked ones; `after` deps are honoured."""
    order = [i for i in open_items if i["state"] != "blocked"] + [i for i in open_items if i["state"] == "blocked"]
    order = [dict(i, n=n) for n, i in enumerate(order)]
    ids = {i["id"] for i in order if i["id"]}
    slots = [next_workday(today)] * wip
    ends, out, pending = {}, [], list(order)
    while pending:
        ready = next((i for i in pending if not i["after"] or i["after"] not in ids or i["after"] in ends), None)
        if ready is None:  # dependency cycle: ignore the declared dependency of the first one
            ready = dict(pending.pop(0), after="")
        else:
            pending.remove(ready)
        k = min(range(wip), key=lambda s: slots[s])
        start = slots[k]
        if ready["after"] in ends:
            start = max(start, ends[ready["after"]])
        start = next_workday(start)
        days = size_days.get(ready["size"]) or size_days["M"]
        fin = finish_after(start, math.ceil(days))
        slots[k] = fin
        if ready["id"]:
            ends[ready["id"]] = fin
        out.append(dict(ready, start=start, end=fin, days=days, size_missing=not ready["size"]))
    out.sort(key=lambda r: r["n"])
    return out


def gantt(items, today, hist, hist_ok, size_days, wip):
    done_rows, undated = [], []
    for it in items:
        if it["state"] != "done":
            continue
        h = (hist.get(it["id"]) or {}) if hist_ok and it["id"] else {}
        end, start = parse_day(h.get("done")), parse_day(h.get("doing"))
        if not end:
            undated.append(it)
        else:
            done_rows.append(dict(it, start=min(start or end, end), end=end))
    hidden = max(0, len(done_rows) - DONE_ROWS)
    done_rows = done_rows[-DONE_ROWS:]
    est = schedule([i for i in items if i["state"] != "done"], today, size_days, wip)
    lo = min([today - datetime.timedelta(days=14)] + [r["start"] for r in done_rows])
    lo = max(lo, today - datetime.timedelta(days=GANTT_BACK_DAYS))
    lo -= datetime.timedelta(days=lo.weekday())
    cap = today + datetime.timedelta(days=GANTT_CAP_DAYS)
    hi = max([today + datetime.timedelta(days=14)] + [r["end"] for r in est])
    beyond = hi > cap
    hi = min(hi, cap) + datetime.timedelta(days=3)
    return {"lo": lo, "hi": hi, "today": today, "done": done_rows, "open": est, "undated": undated, "hidden_done": hidden,
            "beyond": beyond, "size_days": size_days, "wip": wip}


# ---------------------------------------------------------------- releases

def read_tags(root):
    """[(tag, date)] for tags vX.Y[.Z], oldest first. Empty when git is missing or there are no tags."""
    raw = S.git(root, "for-each-ref", "--format=%(refname:short)\t%(creatordate:short)", "refs/tags")
    out = []
    for ln in raw.splitlines():
        t, _, day = ln.partition("\t")
        if TAG_RE.match(t) and parse_day(day):
            out.append((t, parse_day(day)))
    return sorted(out, key=lambda x: (x[1], x[0]))


def releases(items, tags, hist, hist_ok):
    groups = {}

    def group(name):
        return groups.setdefault(name, {"name": name, "tags": [], "date": None, "items": []})

    def matches(rel, tag):
        return tag == rel or tag.startswith(rel + ".")
    markers = sorted({i["release"] for i in items if i["release"]})
    for rel in markers:
        g = group(rel)
        mine = [t for t in tags if matches(rel, t[0])]
        g["tags"] = [t[0] for t in mine]
        g["date"] = mine[0][1] if mine else None
    for t, d in tags:
        if not any(matches(r, t) for r in markers):
            g = group(t)
            g["tags"], g["date"] = [t], d
    tag_group = {t: next(g["name"] for g in groups.values() if t in g["tags"]) for t, _d in tags}
    unassigned = []
    for it in items:
        if it["release"]:
            group(it["release"])["items"].append(dict(it, how="marker"))
        elif it["state"] == "done":
            d = parse_day((hist.get(it["id"]) or {}).get("done")) if hist_ok and it["id"] else None
            t = next((t for t, td in tags if d and td >= d), None)
            (group(tag_group[t])["items"] if t else unassigned).append(dict(it, how="by date" if t else ""))
    for g in groups.values():
        g["shipped"] = bool(g["tags"])
    def newest_first(g):  # planned first (highest version first), then shipped (latest tag date first)
        return (g["shipped"], [-int(x) for x in re.findall(r"\d+", g["name"])] if not g["shipped"] else [-g["date"].toordinal()])
    ordered = sorted(groups.values(), key=newest_first)
    return {"groups": ordered, "unassigned": unassigned, "any": bool(ordered)}


# ---------------------------------------------------------------- entry

def build(milestones, today, conf, hist=None, hist_ok=False, tags=None):
    st = settings(conf)
    items = flat_items(milestones)
    hist = hist or {}
    return {"settings": st, "items": items, "months": months(items, milestones, today, hist, hist_ok),
            "gantt": gantt(items, today, hist, hist_ok, st["size_days"], st["wip"]),
            "releases": releases(items, tags or [], hist, hist_ok), "history": hist_ok}


def collect(root, milestones, conf, today=None):
    today = today or datetime.date.today()
    try:
        hist, ok = evals_flow.history(root, d2s(today))
    except Exception:  # noqa: BLE001 (any git/parse failure degrades to empty states)
        hist, ok = {}, False
    try:
        tags = read_tags(root)
    except Exception:  # noqa: BLE001
        tags = []
    return build(milestones, today, conf, hist, ok, tags)

"""Flow tab: lead time, cycle time, WIP, deploy frequency, change failure rate.
Lead time = PRD approval date -> first prod deploy containing a commit that has `Refs: <ITEM-ID>`.
"Containing" follows first-parent history: a commit merged from a branch counts at its merge commit.
Prod env names come from factory.json dashboard.prod_envs (default prod, production).
Cycle time = first commit with that Refs -> the commit that first ticks the item in docs/BACKLOG.md.
Deploys come from metrics/history.jsonl (`metrics.py deploy --env prod`). Missing data shows as "–" or "n/a: needs N events"."""
import datetime
import html
import json
import re
import statistics
import time

from . import sources as S

MIN_EVENTS = 3  # aggregates (median, frequency, failure rate) need at least this many events
WINDOW_DAYS = 28
CAP = 20
DEFAULT_PROD = ("prod", "production")
REFS_RE = re.compile(r"(?mi)^refs:\s*(.+)$")
EMPTY = ("No backlog items yet: flow appears once docs/BACKLOG.md has items with IDs, commits carry `Refs: <ITEM-ID>` "
         "and deploys are recorded with `python3 scripts/metrics.py deploy --env prod`.")


def e(x):
    return html.escape(str(x), quote=True)


def prod_envs(root):
    """Lower-cased env names that count as production: dashboard.prod_envs (non-empty list of strings), else prod/production."""
    v = S.dash_conf(root).get("prod_envs")
    names = [x.strip().lower() for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []
    return tuple(names) or DEFAULT_PROD


def mainline_pos(parents):
    """{sha: position} on the first-parent line (oldest = 0); side-branch commits take their merge commit's position.

    `parents` maps sha -> [parent shas]; the tip of the line is the one commit nobody lists as a parent."""
    child = {p for ps in parents.values() for p in ps}
    heads = [c for c in parents if c not in child]
    line = []
    cur = heads[0] if heads else None  # the repo's tip (a lone branch tip when history is linear or merged)
    while cur in parents:
        line.append(cur)
        cur = parents[cur][0] if parents[cur] else None
    line.reverse()
    pos = {c: i for i, c in enumerate(line)}
    for i, f in enumerate(line):  # oldest merge first claims the side commits it brought in
        stack = list(parents[f][1:])
        while stack:
            x = stack.pop()
            if x in pos or x not in parents:
                continue
            pos[x] = i
            stack.extend(parents[x])
    return pos


def commits(root):
    """Oldest-first [{sha, ts, refs, pos}] for all commits (one git call); pos = first-parent position."""
    out = S.git(root, "log", "--reverse", "--format=%x1e%h%x1f%ct%x1f%p%x1f%B")
    res, parents = [], {}
    for rec in out.split("\x1e")[1:]:
        sha, _, rest = rec.partition("\x1f")
        ts, _, rest = rest.partition("\x1f")
        par, _, body = rest.partition("\x1f")
        parents[sha.strip()] = par.split()
        refs = []
        for m in REFS_RE.finditer(body):
            refs += [t for t in re.split(r"[,\s]+", m.group(1).strip()) if S.ID_RE.match(t)]
        res.append({"sha": sha.strip(), "ts": int(ts) if ts.strip().isdigit() else 0, "refs": refs})
    pos = mainline_pos(parents)
    for i, c in enumerate(res):
        c["pos"] = pos.get(c["sha"], i)
    return res


def deploys(root):
    rows = []
    for ln in S.read(root, "metrics/history.jsonl").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("kind") == "deploy" and r.get("ts"):
            rows.append(r)
    return sorted(rows, key=lambda r: r["ts"])


def _epoch(iso):
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.timestamp()


def _date_epoch(day):
    try:
        return datetime.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return None


def tick_time(root, item_id):
    """Unix time of the first commit that adds the item as done in docs/BACKLOG.md, else None."""
    out = S.git(root, "log", "--reverse", "-G", r"^\s*[-*] \[[xX]\] %s\b" % re.escape(item_id), "--format=%ct", "--", "docs/BACKLOG.md")
    first = out.split()[:1]
    return int(first[0]) if first else None


def days(seconds):
    return None if seconds is None else round(seconds / 86400.0, 1)


def median(xs):
    return round(statistics.median(xs), 1) if len(xs) >= MIN_EVENTS else None


def fmt_days(v):
    return "–" if v is None else "%s d" % v


def collect(root, base):
    cs = commits(root)
    order = {c["sha"]: c["pos"] for c in cs}
    dep = deploys(root)
    envs = prod_envs(root)
    prod = [r for r in dep if str(r.get("env", "")).strip().lower() in envs]
    prds = {p["slug"]: p for p in S.prds(root)}
    prd_of = {}
    for ch in (base.get("traceability") or {}).get("chains", []):
        for it in ch["items"]:
            prd_of[it["title"].casefold()] = ch["prd"]["slug"]
    items = []
    for ms in (base.get("progress") or {}).get("milestones", []):
        for i in ms["items"]:
            m = S.ID_RE.match(i["title"])
            if not m or i["state"] == "dropped":
                continue
            iid = m.group(1)
            title = i["title"][len(iid):].strip()
            refs = [c for c in cs if iid in c["refs"]]
            start = refs[0] if refs else None
            cycle = lead = None
            if i["state"] == "done" and start:
                t = tick_time(root, iid)
                if t is not None and t >= start["ts"]:
                    cycle = days(t - start["ts"])
            slug = prd_of.get(title.casefold())
            appr = _date_epoch(prds[slug]["approved"]) if slug in prds and prds[slug]["approved"] else None
            if start and appr is not None:
                for r in prod:
                    if r.get("sha") in order and order[r["sha"]] >= order[start["sha"]]:
                        te = _epoch(r["ts"])
                        lead = days(te - appr) if te is not None and te >= appr else None
                        break
            items.append({"id": iid, "title": title, "state": i["state"], "commits": len(refs), "lead_days": lead, "cycle_days": cycle})
    now = time.time()
    recent = [r for r in prod if (_epoch(r["ts"]) or 0) >= now - WINDOW_DAYS * 86400]
    failed = sum(1 for r in prod if r.get("ok") is False)
    leads = [x["lead_days"] for x in items if x["lead_days"] is not None]
    cycles = [x["cycle_days"] for x in items if x["cycle_days"] is not None]
    return {"items": items[:CAP], "items_total": len(items),
            "wip": sum(x["state"] == "doing" for x in items),
            "lead": {"median_days": median(leads), "n": len(leads)},
            "cycle": {"median_days": median(cycles), "n": len(cycles)},
            "deploys": {"prod": len(prod), "other": len(dep) - len(prod), "last_%dd" % WINDOW_DAYS: len(recent),
                        "per_week": round(len(recent) / (WINDOW_DAYS / 7.0), 1) if len(prod) >= MIN_EVENTS else None,
                        "failed": failed,
                        "failure_rate_pct": round(100.0 * failed / len(prod)) if len(prod) >= MIN_EVENTS else None}}


def _rate(d):
    dp = d["deploys"]
    if dp["per_week"] is None:
        return "n/a: needs %d prod deploys (have %d)" % (MIN_EVENTS, dp["prod"]), "n/a: needs %d prod deploys (have %d)" % (MIN_EVENTS, dp["prod"])
    return "%s / week (last %d days)" % (dp["per_week"], WINDOW_DAYS), "%d%% (%d of %d)" % (dp["failure_rate_pct"], dp["failed"], dp["prod"])


def _med(x):
    if x["median_days"] is None:
        return "n/a: needs %d events (have %d)" % (MIN_EVENTS, x["n"])
    return "%s d (%d items)" % (x["median_days"], x["n"])


def line(d):
    if not d["items_total"] and not d["deploys"]["prod"]:
        return "no flow data yet"
    freq, cfr = _rate(d)
    short = lambda s: "n/a" if s.startswith("n/a") else s  # noqa: E731
    return "lead %s, cycle %s, WIP %d, deploys %s, failures %s" % (
        short(_med(d["lead"])).split(" (")[0], short(_med(d["cycle"])).split(" (")[0], d["wip"],
        short(freq).split(" (")[0], short(cfr).split(" (")[0])


def render(d):
    if not d["items_total"] and not d["deploys"]["prod"]:
        return '<div class="card"><h2>Flow</h2><p class="muted">%s</p></div>' % e(EMPTY)
    freq, cfr = _rate(d)
    facts = [("Lead time, median (PRD approved → first prod deploy with a Refs commit)", _med(d["lead"])),
             ("Cycle time, median (first Refs commit → commit that ticks the item)", _med(d["cycle"])),
             ("WIP (items in progress)", str(d["wip"])), ("Deploy frequency (prod)", freq), ("Change failure rate (prod)", cfr)]
    kv = "".join('<tr><td>%s</td><td class="%s">%s</td></tr>' % (e(k), "muted" if v.startswith("n/a") else "", e(v)) for k, v in facts)
    rows = "".join('<tr><td class="mono nowrap">%s</td><td>%s</td><td>%s</td><td>%d</td><td>%s</td><td>%s</td></tr>' % (
        e(i["id"]), e(i["title"][:80]), e(i["state"]), i["commits"], e(fmt_days(i["lead_days"])), e(fmt_days(i["cycle_days"])))
        for i in d["items"])
    cap = '<p class="muted small">Top %d of %d items; full list in data.json.</p>' % (len(d["items"]), d["items_total"]) \
        if d["items_total"] > len(d["items"]) else ""
    note = '<p class="muted small">Items without a Refs commit, PRD approval date or prod deploy show "–". Deploys with other envs: %d.</p>' % d["deploys"]["other"]
    return ('<div class="stack"><div class="card"><h2>Flow</h2><table><tbody>%s</tbody></table>%s</div>'
            '<div class="card"><h2>Per item</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Item</th><th>State</th><th>Commits</th><th>Lead</th><th>Cycle</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div></div>' % (kv, note, rows or '<tr><td colspan="6" class="muted">No items with IDs.</td></tr>', cap))

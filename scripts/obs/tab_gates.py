"""Gates tab: PRD approval per item, tests per component, last check.sh pass, last security audit, dependency freshness.
Everything comes from repo state; what has no record yet says "not recorded yet" (records: `metrics.py record <kind>`)."""
import datetime
import html
import json
import os
import time

from . import sources as S

NOT_YET = "not recorded yet"
MANIFESTS = ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements.txt", "pyproject.toml",
             "uv.lock", "poetry.lock", "Pipfile.lock")
CAP = 25
GATE_EMPTY = "No gate runs yet: run `python3 scripts/gate.py`."
GATE_WINDOW = 20
EMPTY = "No backlog items yet: gates appear once docs/BACKLOG.md has items; PRD status comes from docs/specs/."


def e(x):
    return html.escape(str(x), quote=True)


def _age(ts, now):
    return max(0, int((now - ts) // 86400))


def _rec(root, kind, now):
    r = S.last_record(root, kind)
    if not r:
        return None
    try:
        t = datetime.datetime.fromisoformat(r["ts"]).timestamp()
    except ValueError:
        return {"ts": r["ts"], "sha": r.get("sha") or "", "days": None}
    return {"ts": r["ts"], "sha": r.get("sha") or "", "days": _age(t, now)}


def gate_rows(root):
    """Valid full-run verdict rows from metrics/gate.local.jsonl, oldest first; malformed lines and --only runs skipped."""
    rows = []
    for ln in S.read(root, "metrics/gate.local.jsonl").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("verdict") in ("pass", "fail") and isinstance(r.get("checks"), list) and not r.get("only"):
            rows.append(r)
    return rows


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0.0


def gate_stats(rows, budget):
    """Merge gate numbers from verdict rows: last verdict, pass rate over the last 20, top failure codes,
    gate time vs budget, first-try pass rate per sha (share of shas whose first recorded run passed)."""
    if not rows:
        return None
    win = rows[-GATE_WINDOW:]
    codes = {}
    for r in win:
        for c in r["checks"]:
            if isinstance(c, dict) and c.get("status") == "fail":
                for code in c.get("codes") or []:
                    codes[str(code)] = codes.get(str(code), 0) + 1
    first = {}
    for r in rows:
        if r.get("sha"):
            first.setdefault(r["sha"], r["verdict"])
    last = rows[-1]
    return {"runs": len(rows), "window": len(win), "pass_rate": round(100.0 * sum(r["verdict"] == "pass" for r in win) / len(win)),
            "top_codes": sorted(codes.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
            "first_try_rate": round(100.0 * sum(v == "pass" for v in first.values()) / len(first)) if first else None,
            "shas": len(first), "budget": budget,
            "last": {"verdict": last["verdict"], "sha": last.get("sha") or "", "ts": str(last.get("ts") or ""),
                     "seconds": _num(last.get("seconds")),
                     "checks": [{"id": str(c.get("id")), "status": str(c.get("status")), "codes": [str(x) for x in c.get("codes") or []],
                                 "seconds": _num(c.get("seconds"))} for c in last["checks"] if isinstance(c, dict)]}}


def collect(root, base):
    now = time.time()
    by_title = {}
    for ch in (base.get("traceability") or {}).get("chains", []):
        for it in ch["items"]:
            by_title[it["title"].casefold()] = ch["prd"]
    items = []
    for ms in (base.get("progress") or {}).get("milestones", []):
        for i in ms["items"]:
            if i["state"] == "dropped":
                continue
            m = S.ID_RE.match(i["title"])
            title = i["title"][len(m.group(1)):].strip() if m else i["title"]
            prd = by_title.get(title.casefold())
            items.append({"id": m.group(1) if m else "", "title": title, "state": i["state"],
                          "prd": prd["slug"] if prd else "", "prd_status": prd["status"] if prd else "none"})
    tests = S.test_files(root)
    comps = []
    for x in (base.get("architecture") or {}).get("layers", {}).get("application", []):
        if x["type"] != "application-component" or not x.get("path"):
            continue
        stem = os.path.basename(x["path"]).rsplit(".", 1)[0].lower()
        hit = [t for t in tests if len(stem) > 2 and stem in t.lower()]
        comps.append({"path": x["path"], "tests": len(hit)})
    times = S.commit_times(root)
    deps = sorted(({"path": p, "days": _age(times[p], now)} for p in MANIFESTS if p in times), key=lambda d: d["path"])
    m = base.get("metrics") or {}
    gate = gate_stats(gate_rows(root), (m.get("test_budget")))
    return {"gate": gate, "items": items[:CAP], "items_total": len(items),
            "items_no_prd": sum(i["prd_status"] != "approved" for i in items),
            "components": comps[:CAP], "components_total": len(comps), "components_untested": sum(c["tests"] == 0 for c in comps),
            "coverage": m.get("coverage"), "coverage_min": m.get("coverage_min"),
            "check": _rec(root, "check", now), "security": _rec(root, "security-audit", now), "deps": deps}


def _when(r):
    if not r:
        return NOT_YET
    return "%s (%s)" % (r["ts"][:10], "today" if r["days"] == 0 else "%d days ago" % r["days"] if r["days"] is not None else "date unclear") \
        + (" at %s" % r["sha"] if r["sha"] else "")


def gate_line(g):
    if not g:
        return "merge gate: no runs yet"
    ft = "n/a" if g["first_try_rate"] is None else "%d%%" % g["first_try_rate"]
    return "merge gate %s in %.0fs%s, %d%% of last %d pass, first-try %s" % (
        g["last"]["verdict"].upper(), g["last"]["seconds"], " (budget %ss)" % g["budget"] if g["budget"] else "",
        g["pass_rate"], g["window"], ft)


def render_gate(g):
    if not g:
        return '<div class="card"><h2>Merge gate</h2><p class="muted">%s</p></div>' % e(GATE_EMPTY)
    last = g["last"]
    cls = {"pass": "low", "warn": "medium", "fail": "high"}
    rows = "".join('<tr><td class="mono">%s</td><td><span class="imp %s">%s</span></td><td class="mono">%s</td><td class="nowrap">%.1fs</td></tr>' % (
        e(c["id"]), cls.get(c["status"], ""), e(c["status"]), e(", ".join(c["codes"]) or "–"), c["seconds"]) for c in last["checks"])
    top = ", ".join("%s (%d)" % (c, n) for c, n in g["top_codes"]) or "none"
    over = g["budget"] and last["seconds"] > g["budget"]
    facts = [("Last verdict", "%s at %s (%s)" % (last["verdict"].upper(), last["sha"] or "unknown sha", last["ts"][:10] or "date unclear")),
             ("Pass rate (last %d runs)" % g["window"], "%d%%" % g["pass_rate"]),
             ("First-try pass rate per sha", ("%d%% of %d sha(s)" % (g["first_try_rate"], g["shas"])) if g["first_try_rate"] is not None else NOT_YET),
             ("Top failure codes (last %d runs)" % g["window"], top),
             ("Gate time vs test budget", "%.1fs vs %ss%s" % (last["seconds"], g["budget"], " (over)" if over else "") if g["budget"] else "%.1fs" % last["seconds"])]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    return ('<div class="card"><h2>Merge gate</h2><table><tbody>%s</tbody></table>'
            '<div class="scroll"><table><thead><tr><th>Check</th><th>Status</th><th>Codes</th><th>Time</th></tr></thead><tbody>%s</tbody></table></div></div>'
            % (kv, rows or '<tr><td colspan="4" class="muted">No checks recorded.</td></tr>'))


def line(d):
    chk = "check.sh " + (d["check"]["ts"][:10] if d["check"] else NOT_YET)
    sec = "audit " + (d["security"]["ts"][:10] if d["security"] else NOT_YET)
    dep = "deps %dd old" % max(x["days"] for x in d["deps"]) if d["deps"] else "no dependency manifests"
    return "%d/%d items without approved PRD, %d/%d components without tests; %s; %s; %s; %s" % (
        d["items_no_prd"], d["items_total"], d["components_untested"], d["components_total"], chk, sec, dep, gate_line(d.get("gate")))


def render(d):
    if not d["items_total"] and not d["components_total"]:
        return '<div class="stack"><div class="card"><h2>Gates</h2><p class="muted">%s</p></div>%s</div>' % (e(EMPTY), render_gate(d.get("gate")))
    cov = ("%.1f%% (min %s%%)" % (d["coverage"], d["coverage_min"])) if d["coverage"] is not None else NOT_YET
    deps = ", ".join("%s: %dd" % (x["path"], x["days"]) for x in d["deps"]) or "no dependency manifests in the repo"
    facts = [("Last check.sh pass", _when(d["check"])), ("Last security audit", _when(d["security"])),
             ("Dependency freshness (days since manifest last changed)", deps), ("Coverage (overall; per component is not tracked)", cov)]
    kv = "".join('<tr><td>%s</td><td class="%s">%s</td></tr>' % (e(k), "muted" if v == NOT_YET else "", e(v)) for k, v in facts)
    irows = "".join('<tr><td class="mono nowrap">%s</td><td>%s</td><td>%s</td><td><span class="imp %s">%s</span></td></tr>' % (
        e(i["id"] or "–"), e(i["title"][:90]), e(i["state"]), "low" if i["prd_status"] == "approved" else "high",
        e(("PRD " + i["prd_status"]) if i["prd"] else "no PRD")) for i in d["items"])
    crows = "".join('<tr><td class="mono">%s</td><td><span class="imp %s">%s</span></td></tr>' % (
        e(c["path"]), "low" if c["tests"] else "medium", ("%d test file(s)" % c["tests"]) if c["tests"] else "no test by name")
        for c in d["components"])
    capi = '<p class="muted small">Top %d of %d items; full list in data.json.</p>' % (len(d["items"]), d["items_total"]) \
        if d["items_total"] > len(d["items"]) else ""
    capc = '<p class="muted small">Top %d of %d components; full list in data.json.</p>' % (len(d["components"]), d["components_total"]) \
        if d["components_total"] > len(d["components"]) else ""
    return ('<div class="stack">' + render_gate(d.get("gate")) + '<div class="card"><h2>Gates</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>PRD approved per item (%d without)</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Item</th><th>State</th><th>PRD</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div>'
            '<div class="card"><h2>Tests per component (matched by file name)</h2><div class="scroll"><table><tbody>%s</tbody></table></div>%s</div></div>'
            % (kv, d["items_no_prd"], irows or '<tr><td colspan="4" class="muted">No items.</td></tr>', capi,
               crows or '<tr><td class="muted">No components yet (see the Architecture tab).</td></tr>', capc))

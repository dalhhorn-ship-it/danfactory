"""Gates tab: PRD approval per item, tests per component, last check.sh pass, last security audit, dependency freshness.
Everything comes from repo state; what has no record yet says "not recorded yet" (records: `metrics.py record <kind>`)."""
import datetime
import html
import json
import os
import re
import time

from . import sources as S

NOT_YET = "not recorded yet"
MANIFESTS = ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements.txt", "pyproject.toml",
             "uv.lock", "poetry.lock", "Pipfile.lock")
CAP = 25
GATE_EMPTY = "No gate runs yet: run `python3 scripts/gate.py`."
GATE_WINDOW = 20
SETUP_RE = re.compile(r"\bset[- ]?up\b", re.I)
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


ACC_EMPTY = "No acceptance suite yet: at L2+, the test-writer adds one after a PRD is approved (docs/policies/merge-gate.md)."


def acceptance_stats(root, rows):
    """Per PRD in tests/acceptance/manifest.json: criteria, criteria with an admitted test, admitted tests, passing, open
    questions, second-reading share; plus overall spec coverage. None when the manifest has no PRD."""
    import sys
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.append(here)
    try:
        import acceptance as A
    except ImportError:
        return None
    man = A.load_manifest(root)
    if not man["prds"]:
        return None
    passing, src = None, "baseline"
    for r in reversed(rows):
        ch = next((c for c in r["checks"] if isinstance(c, dict) and c.get("id") == "acceptance"), None)
        if ch and isinstance(ch.get("passing"), list):
            passing, src = set(str(x) for x in ch["passing"]), "latest gate run"
            break
    if passing is None:
        passing = set(str(x) for x in (A.read_json(os.path.join(root, A.BASELINE), {}) or {}).get("passing") or [])
    prds, crit_all, cov_all = [], 0, 0
    for slug, rec in sorted(man["prds"].items()):
        crit = A.criteria_of(root, slug)
        adm = {i: r for i, r in man["admitted"].items() if isinstance(r, dict) and r.get("prd") == slug}
        covered = {str(r.get("criterion")) for r in adm.values()} & set(crit)
        qs = [str(q) for q in man["questions"].get(slug) or []]
        prds.append({"slug": slug, "criteria": len(crit), "covered": len(covered), "admitted": len(adm),
                     "passing": sum(1 for i in adm if i in passing), "questions": qs,
                     "second_reading": sum(1 for r in adm.values() if r.get("reference"))})
        crit_all += len(crit)
        cov_all += len(covered)
    return {"prds": prds, "criteria": crit_all, "covered": cov_all, "source": src,
            "coverage_pct": round(100.0 * cov_all / crit_all) if crit_all else None,
            "questions": sum(len(p["questions"]) for p in prds)}


def acceptance_line(a):
    if not a:
        return "no suite yet"
    adm = sum(p["admitted"] for p in a["prds"])
    return "spec coverage %s (%d/%d criteria with an admitted test), %d/%d admitted passing, %d open PRD question(s)" % (
        "n/a" if a["coverage_pct"] is None else "%d%%" % a["coverage_pct"], a["covered"], a["criteria"],
        sum(p["passing"] for p in a["prds"]), adm, a["questions"])


def render_acceptance(a):
    if not a:
        return '<div class="card"><h2>Acceptance coverage</h2><p class="muted">%s</p></div>' % e(ACC_EMPTY)
    rows = "".join('<tr><td class="mono">%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td><span class="imp %s">%d</span></td><td>%s</td></tr>' % (
        e(p["slug"]), p["criteria"], p["covered"], p["admitted"], p["passing"], "medium" if p["questions"] else "low", len(p["questions"]),
        ("%d%%" % round(100.0 * p["second_reading"] / p["admitted"])) if p["admitted"] else "–") for p in a["prds"])
    qs = "".join("<li><span class=\"mono\">%s</span>: %s</li>" % (e(p["slug"]), e(q)) for p in a["prds"] for q in p["questions"])
    facts = [("Spec coverage (criteria with an admitted test)", "%s (%d of %d)" % (
        "n/a" if a["coverage_pct"] is None else "%d%%" % a["coverage_pct"], a["covered"], a["criteria"])),
        ("Passing counted from", a["source"])]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    return ('<div class="card"><h2>Acceptance coverage</h2><table><tbody>%s</tbody></table><div class="scroll"><table><thead><tr>'
            '<th>PRD</th><th>Criteria</th><th>With admitted test</th><th>Admitted tests</th><th>Passing</th><th>Open questions</th>'
            '<th>Second reading</th></tr></thead><tbody>%s</tbody></table></div>%s</div>'
            % (kv, rows, ('<h3>Open PRD questions: answer them in a PRD revision</h3><ul>%s</ul>' % qs) if qs else ""))


def guard_stats(root, rows, now):
    """PRD write guard numbers: blocks in the last 30 days (metrics/guard.local.jsonl, local per machine), exemptions dated
    today (.factory/prd-exemption), and gate runs among the last GATE_WINDOW carrying `no-approved-prd`."""
    blocks = 0
    for ln in S.read(root, "metrics/guard.local.jsonl").splitlines():
        try:
            t = datetime.datetime.fromisoformat(json.loads(ln)["ts"]).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        if now - t <= 30 * 86400:
            blocks += 1
    today = datetime.date.fromtimestamp(now).isoformat()
    ex = [x for x in (S.read(root, ".factory/prd-exemption") or "").splitlines()
          if re.match(r"^%s\s+(bugfix|chore|waiver|spike):\s*\S" % today, x.strip())]
    last = rows[-GATE_WINDOW:]
    return {"blocks_30d": blocks, "open_exemptions": len(ex), "exemptions": [x.strip() for x in ex][:5],
            "no_approved_prd_runs": sum("no-approved-prd" in (r.get("codes") or []) for r in last), "window": len(last)}


def guard_line(g):
    if not g:
        return "PRD guard n/a"
    return "PRD guard: %d block(s) in 30d, %d open exemption(s), no-approved-prd in %d of last %d gate run(s)" % (
        g["blocks_30d"], g["open_exemptions"], g["no_approved_prd_runs"], g["window"])


def render_guard(g):
    if not g:
        return ""
    facts = [("Guard blocks, last 30 days (this machine)", g["blocks_30d"]),
             ("Open exemptions (dated today)", "%d%s" % (g["open_exemptions"], (": " + "; ".join(g["exemptions"])) if g["exemptions"] else "")),
             ("Gate runs with `no-approved-prd` (last %d)" % g["window"], g["no_approved_prd_runs"])]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    return '<div class="card"><h2>PRD write guard</h2><table><tbody>%s</tbody></table></div>' % kv


def collect(root, base):
    now = time.time()
    by_title = {}
    for ch in (base.get("traceability") or {}).get("chains", []):
        for it in ch["items"]:
            by_title[it["title"].casefold()] = ch["prd"]
    items = []
    for ms in (base.get("progress") or {}).get("milestones", []):
        for i in ms["items"]:
            if i["state"] == "dropped" or "process" in (i.get("tags") or []) or SETUP_RE.search(ms["name"]):
                continue  # process items and the setup milestone never need a PRD (NEW-2)
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
    return {"gate": gate, "guard": guard_stats(root, gate_rows(root), now), "acceptance": acceptance_stats(root, gate_rows(root)), "items": items[:CAP], "items_total": len(items),
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
        d["items_no_prd"], d["items_total"], d["components_untested"], d["components_total"], chk, sec, dep, gate_line(d.get("gate"))) \
        + "; " + guard_line(d.get("guard"))


def render(d):
    if not d["items_total"] and not d["components_total"]:
        return '<div class="stack"><div class="card"><h2>Gates</h2><p class="muted">%s</p></div>%s</div>' % (e(EMPTY), render_gate(d.get("gate")) + render_guard(d.get("guard")) + render_acceptance(d.get("acceptance")))
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
    return ('<div class="stack">' + render_gate(d.get("gate")) + render_guard(d.get("guard")) + render_acceptance(d.get("acceptance")) + '<div class="card"><h2>Gates</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>PRD approved per item (%d without)</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Item</th><th>State</th><th>PRD</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div>'
            '<div class="card"><h2>Tests per component (matched by file name)</h2><div class="scroll"><table><tbody>%s</tbody></table></div>%s</div></div>'
            % (kv, d["items_no_prd"], irows or '<tr><td colspan="4" class="muted">No items.</td></tr>', capi,
               crows or '<tr><td class="muted">No components yet (see the Architecture tab).</td></tr>', capc))

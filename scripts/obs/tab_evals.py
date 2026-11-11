"""Evals tab: agent eval results from metrics/evals.jsonl (scripts/evals.py) vs metrics/evals-baseline.json.

Offline and read-only. Missing, empty or malformed input never raises: bad lines are skipped, no rows = empty state.
Aggregation reuses evals.read_rows / evals.rates / evals.compare so the dashboard and the CLI always agree.
"""
import html
import json
import os
import sys

from . import delivery, evals_data, evals_flow, evals_views

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import evals  # noqa: E402

TREND_SETS = 12
EMPTY = "No evals run yet. Run python3 scripts/evals.py run (it calls the model and costs money; see docs/policies/evals.md)."


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def _json(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _threshold(root):
    try:
        return float(((_json(root, "factory.json") or {}).get("evals") or {}).get("regression_threshold",
                                                                                  evals.DEFAULTS["regression_threshold"]))
    except (TypeError, ValueError):
        return evals.DEFAULTS["regression_threshold"]


def _num(r, k):
    v = r.get(k)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _sets(rows):
    order = []
    for r in rows:
        if r["set"] not in order:
            order.append(r["set"])
    return order


def collect(root, base=None):
    rows = evals.read_rows(os.path.join(root, "metrics", "evals.jsonl"))
    d = _collect_latest(root, rows)
    try:
        rules, rules_ok = evals_data.load_rules(root)
        lib = evals_data.library(root, rows, rules=rules)
        d.update(library=lib, rules_ok=rules_ok, coverage=evals_data.coverage(rules, lib),
                 heatmap=evals_data.heatmap(rows, [t["id"] for t in lib]),
                 economics=evals_data.economics(rows, _threshold(root)),
                 flow=evals_flow.collect(root, lib, rows, _threshold(root)))
    except Exception as ex:  # a view bug must never break the dashboard build
        d["views_error"] = "%s: %s" % (type(ex).__name__, ex)
    return d


def _collect_latest(root, rows):
    if not rows:
        return {"empty": True, "baseline": None}
    order = _sets(rows)
    sid = order[-1]
    cur_rows = [r for r in rows if r["set"] == sid]
    cur = evals.rates(cur_rows)
    ok = [r for r in cur_rows if not r.get("error") and r.get("pass")]
    tokens = lambda rs: sum(_num(r, "tokens_in") + _num(r, "tokens_cache") + _num(r, "tokens_out") for r in rs)  # noqa: E731
    for tid, t in cur["tasks"].items():
        mine = [r for r in cur_rows if r["task"] == tid and not r.get("error")]
        p = [r for r in mine if r.get("pass")]
        t["flaky"] = 0 < t["passes"] < t["runs"]
        t["tokens_per_pass"] = round(tokens(p) / len(p)) if p else None
        t["cost_per_pass"] = round(sum(_num(r, "cost_usd") for r in p) / len(p), 4) if p else None
    trend = []
    for s in order[-TREND_SETS:]:
        rs = [r for r in rows if r["set"] == s and not r.get("error")]
        trend.append({"set": s, "pct": round(100.0 * sum(bool(r.get("pass")) for r in rs) / len(rs)) if rs else None})
    b = _json(root, "metrics/evals-baseline.json")
    baseline = None
    if b and isinstance(b.get("tasks"), dict) and isinstance(b.get("gates"), dict):
        try:
            lines, bad = evals.compare(b, cur, _threshold(root))
            baseline = {"set": b.get("set"), "regression": bad,
                        "regressed": [ln.split()[0] for ln in lines if " REGRESSION" in ln]}
        except (KeyError, TypeError, ValueError):
            baseline = None
    last = max((str(r.get("ts") or "") for r in cur_rows), default="")
    return {"empty": False, "set": sid, "sets": len(order), "last_run": last[:10] or None,
            "model": cur_rows[0].get("model"), "n": max((t["runs"] for t in cur["tasks"].values()), default=0),
            "runs": len(cur_rows), "passes": len(ok), "errors": sum(bool(r.get("error")) for r in cur_rows),
            "tasks": cur["tasks"], "gates": cur["gates"], "trend": trend,
            "tokens_per_pass": round(tokens(ok) / len(ok)) if ok else None,
            "cost_per_pass": round(sum(_num(r, "cost_usd") for r in ok) / len(ok), 4) if ok else None,
            "flaky": sorted(k for k, t in cur["tasks"].items() if t["flaky"]), "baseline": baseline}


def _reg(d):
    b = d.get("baseline")
    if not b:
        return "no baseline"
    return "REGRESSION (%s)" % ", ".join(b["regressed"]) if b["regression"] else "no regression"


def line(d):
    if d.get("empty"):
        return "no evals run yet (python3 scripts/evals.py run)"
    return "%d/%d runs passed (set %s, N=%d, %s), %s, flaky %d, last run %s" % (
        d["passes"], d["runs"], d["set"], d["n"], d["model"] or "?", _reg(d), len(d["flaky"]), d["last_run"] or "?")


def _rows(items, flaky_col):
    out = []
    for k, v in sorted(items.items()):
        out.append("<tr><td class=\"mono\">%s</td><td>%d/%d</td><td>%.0f%%</td>%s</tr>" % (
            e(k), v["passes"], v["runs"], v["rate"] * 100,
            ("<td>%s</td><td>%s</td><td>%s</td>" % (
                '<span class="imp medium">flaky</span>' if v["flaky"] else "–",
                e("–" if v["tokens_per_pass"] is None else "{:,}".format(v["tokens_per_pass"])),
                e("–" if v["cost_per_pass"] is None else "$%.3f" % v["cost_per_pass"]))) if flaky_col else ""))
    return "".join(out)


def _views(d):
    if d.get("views_error"):
        return '<p class="muted">Eval views unavailable: %s</p>' % e(d["views_error"])
    return "".join([evals_views.coverage(d["coverage"], d["rules_ok"]), evals_views.library(d["library"]),
                    evals_views.heatmap(d["heatmap"]), evals_views.economics(d["economics"]),
                    evals_views.flow(d["flow"])])


def render(d):
    if d.get("empty"):
        return '<div class="card"><h2>Evals</h2><p class="muted">%s</p>%s</div>' % (e(EMPTY), _views(d))
    trend = d["trend"]
    chart = delivery.bars([t["pct"] for t in trend], [t["set"] for t in trend], "Pass rate per run set", "%")
    state = "ok" if d["baseline"] and not d["baseline"]["regression"] else "bad" if d["baseline"] else "na"
    tiles = '<div class="tiles mini">%s</div>' % "".join([
        delivery._tile("Latest set", "%d/%d" % (d["passes"], d["runs"]), "passed · N=%d · %s" % (d["n"], d["model"] or "?")),
        delivery._tile("Regression", _reg(d).split(" (")[0],
                       "vs baseline set %s" % d["baseline"]["set"] if d["baseline"] else "run evals.py baseline to set one",
                       state, ("no regression", "", "regression")),
        delivery._tile("Per pass", "–" if d["tokens_per_pass"] is None else "{:,} tok".format(d["tokens_per_pass"]),
                       "–" if d["cost_per_pass"] is None else "$%.3f per passing run" % d["cost_per_pass"]),
        delivery._tile("Last run", d["last_run"] or "–", "%d run set(s) on record" % d["sets"]),
    ])
    reg = ""
    if d["baseline"] and d["baseline"]["regression"]:
        reg = '<p><span class="imp high">regression</span> in %s</p>' % e(", ".join(d["baseline"]["regressed"]))
    th = "<th>Task</th><th>Passed</th><th>Rate</th>"
    return ('<div class="card"><h2>Evals</h2>%s%s<div class="charts">%s</div>'
            '<h3>Per task</h3><div class="scroll"><table><thead><tr>%s<th>Flaky</th><th>Tokens / pass</th><th>Cost / pass</th></tr></thead><tbody>%s</tbody></table></div>'
            '<h3>Per gate</h3><div class="scroll"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
            '<p class="muted small">Flaky = some but not all runs of a task passed. Runs with an infrastructure error (%d here) are not counted. '
            'Source: metrics/evals.jsonl; run python3 scripts/evals.py run to add a set.</p>%s</div>'
            % (tiles, reg, chart, th, _rows(d["tasks"], True), th.replace("Task", "Gate"), _rows(d["gates"], False), d["errors"], _views(d)))

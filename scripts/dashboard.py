#!/usr/bin/env python3
"""Build the project dashboard: versions, progress, backlog, tech debt, key metrics.

  python3 scripts/dashboard.py            # write dashboard/index.html, data.json, SUMMARY.md
  python3 scripts/dashboard.py --open     # ...and open it in a browser
  python3 scripts/dashboard.py --print    # print SUMMARY.md (cheap status for agents)

In template mode (origin = factory.json template.source_repo, see README) it shows "Template maintenance"
(open tech debt, then Unplanned backlog items) instead of phase and progress.

Sources (all in the repo, so every build can regenerate it):
  factory.json, docs/BACKLOG.md, docs/TECH-DEBT.md, metrics/*.jsonl, git tags/log,
  plus automated debt signals (TODO/FIXME markers, oversized files, codegraph import cycles).
Output is a self-contained HTML file (no JS, no network) with tabs: Overview, Roadmap
(two swimlanes, value vs technical foundation, in proposed sequence), and the observability tabs from
scripts/obs/ (Architecture, Traceability, Decisions, Gates, Docs health). dashboard/ is git-ignored;
CI uploads it as a build artifact and writes SUMMARY.md to the job summary.
"""
import argparse
import html
import json
import os
import re
import sys
import webbrowser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from _common import template_mode  # noqa: E402
from obs import (size, theme, delivery, roadmap_data, roadmap_views, tab_architecture, tab_cost, tab_decisions, tab_docs, tab_evals, tab_flow, tab_gates,  # noqa: E402
                 tab_hotspots, tab_traceability)
if os.path.isfile(os.path.join(ROOT, "scripts", "obs", "tab_autonomy.py")):  # a pack file (ADR 0011)
    from obs import tab_autonomy  # noqa: E402
else:
    from obs import tab_autonomy_absent as tab_autonomy  # noqa: E402

from obs.board import (AFTER_RE, CLOSED_RE, DEBT_RE, FOUNDATION_TAGS, ITEM_RE, LANES, LARGE_FILE_LINES, MARKER_RE,  # noqa: E402,F401
                       MILESTONE_RE, NEXT_UP, PHASES, RELEASE_RE, SEQUENCE_RE, SEVERITY_TO_IMPACT, SKIP_DIRS, SPEC_RE,
                       STATES, cells, debt_signals, git, lane_of, metric_view, parse_backlog, parse_debt, read, roadmap,
                       spec_status, strip_code, versions)

OUT = os.path.join(ROOT, "dashboard")
# (key, label, module|None): None = built into this file. Tab inputs, labels and CSS selectors are generated from it.
TABS = (("overview", "Overview", None), ("roadmap", "Roadmap", None),
        ("architecture", "Architecture", tab_architecture), ("traceability", "Traceability", tab_traceability),
        ("decisions", "Decisions", tab_decisions), ("gates", "Gates", tab_gates), ("docs", "Docs health", tab_docs),
        ("flow", "Flow", tab_flow), ("cost", "Cost", tab_cost), ("hotspots", "Hotspots", tab_hotspots),
        ("evals", "Evals", tab_evals), ("autonomy", "Autonomy", tab_autonomy))


def collect():
    f = metrics.factory()
    backlog = parse_backlog(read("docs/BACKLOG.md"))
    items = [i for m in backlog for i in m["items"]]
    counts = {s: sum(i["state"] == s for i in items) for s in ("todo", "doing", "blocked", "done", "dropped")}
    debt = parse_debt(read("docs/TECH-DEBT.md"))
    open_debt = [d for d in debt if d["open"]]
    planned = [m for m in backlog if m["total"]]
    total = sum(m["total"] for m in planned)
    tmpl = template_mode(root=ROOT, factory=f)
    unplanned = [i["title"] for m in backlog if m["name"].lower() == "unplanned"
                 for i in m["items"] if i["state"] in ("todo", "doing", "blocked")]
    d = {
        "template_mode": tmpl, "template_work": unplanned if tmpl else [],
        "generated": metrics.now(),
        "project": f.get("project", {}), "phase": f.get("phase", "brainstorm"), "paths": f.get("paths", {}),
        "template": f.get("template", {}), "deploy": f.get("integrations", {}).get("deploy", {}),
        "versions": versions(),
        "progress": {"milestones": backlog, "pct": round(100.0 * sum(m["done"] for m in planned) / total) if total else 0},
        "backlog": {"counts": counts,
                    "doing": [i["title"] for i in items if i["state"] == "doing"][:8],
                    "blocked": [i["title"] for i in items if i["state"] == "blocked"][:8],
                    "next": [i["title"] for i in items if i["state"] == "todo"][:5]},
        "debt": {"open": open_debt, "resolved": len(debt) - len(open_debt),
                 "by_impact": {k: sum(d["impact"] == k for d in open_debt) for k in ("high", "medium", "low")},
                 "signals": debt_signals(f)},
        "roadmap": roadmap(backlog, open_debt),
        "roadmap_views": roadmap_data.collect(ROOT, backlog, f.get("dashboard")),
        "metrics": metric_view(f),
        "delivery": delivery.collect(ROOT, {"deploy": f.get("integrations", {}).get("deploy", {}),
                                            "dashboard_conf": f.get("dashboard")}),
    }
    for key, _label, mod in TABS:  # each module may read earlier tabs' data from d
        if mod:
            d[key] = mod.collect(ROOT, d)
    d["metrics"]["alerts"] = d["metrics"]["alerts"] + d["hotspots"]["size"]["alerts"]  # size flags show on the Overview
    return d


# ---------------------------------------------------------------- render

def e(x):
    return html.escape("" if x is None else str(x))


def fmt_num(v, suffix="", digits=0):
    if v is None:
        return "–"
    if isinstance(v, (int, float)) and abs(v) >= 10000:
        return "{:,.0f}{}".format(v, suffix)
    return ("{:.%df}{}" % digits).format(v, suffix)


def status(value, budget, higher_is_better=False):
    if value is None or budget is None:
        return "na"
    ok = value >= budget if higher_is_better else value <= budget
    return "ok" if ok else "bad"


def spark(values, label):
    if len(values) < 2:
        return '<span class="muted small">not enough data yet</span>'
    w, h, pad = 160, 36, 3
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(values):
        x = pad + i * (w - 2 * pad) / (len(values) - 1)
        y = h - pad - (v - lo) * (h - 2 * pad) / span
        pts.append("%.1f,%.1f" % (x, y))
    lx, ly = pts[-1].split(",")
    return ('<svg class="spark" viewBox="0 0 %d %d" role="img" aria-label="%s trend, last %d runs">'
            '<polyline points="%s"/><circle cx="%s" cy="%s" r="2.5"/></svg>'
            % (w, h, e(label), len(values), " ".join(pts), lx, ly))


def tile(label, value, sub, state="na", series=None, words=("on budget", "watch", "over budget")):
    badge = {"ok": words[0], "warn": words[1], "bad": words[2], "na": ""}[state]
    return ('<div class="tile %s"><div class="label">%s</div><div class="value">%s</div>'
            '<div class="sub">%s%s</div>%s</div>'
            % (state, e(label), e(value), e(sub),
               ' · <span class="badge">%s</span>' % badge if badge else "",
               series or ""))


def bar(pct, label):
    return ('<div class="bar" role="progressbar" aria-valuenow="%d" aria-valuemin="0" aria-valuemax="100" '
            'aria-label="%s"><span style="width:%d%%"></span></div>' % (pct, e(label), pct))


def f_codegraph():
    return bool(metrics.factory().get("integrations", {}).get("codegraph"))


def render_roadmap(rm):
    cols = rm["columns"]
    if not cols and not rm["done"]:
        return ('<div class="card"><p class="muted">No roadmap yet. Add milestones and items to docs/BACKLOG.md; '
                'tag foundation work with #foundation (or #arch, #infra, #runway, #debt, #quality...).</p></div>')

    def card(c):
        badges = "".join([
            '<span class="prd %s">PRD %s</span>' % (e(c["prd"]), e(c["prd"])) if c.get("prd") else "",
            '<span class="imp %s">%s</span>' % (e(c["impact"]), e(c["impact"])) if c["impact"] else "",
            '<span class="size">%s</span>' % e(c["size"]) if c["size"] else "",
            '<span class="state">%s</span>' % e(c["state"]) if c["state"] in ("doing", "blocked") else ""])
        num = '<span class="seq">%d</span>' % c["seq"] if c["seq"] else '<span class="seq">&#10003;</span>'
        return '<li class="rm-card %s">%s<span class="t">%s</span>%s</li>' % (
            e(c["state"]), num, e(c["title"]), '<span class="b">%s</span>' % badges if badges else "")

    lane_name = {k: label for k, label, _ in LANES}
    done = "".join('<div class="rm-done">&#10003; Done: %s (%d/%d)</div>' % (e(x["name"]), x["done"], x["total"])
                   for x in rm["done"])
    nxt = "".join('<li><span class="seq">%d</span><span class="t">%s</span><span class="muted small">%s</span></li>'
                  % (x["seq"], e(x["short"]), e(" · ".join(p for p in (x["size"], lane_name[x["lane"]]) if p)))
                  for x in rm["next"])
    nxt = '<div class="rm-next"><b>Next up</b><ol>%s</ol></div>' % nxt if nxt else ""
    head = "".join('<div class="rm-col-h"><b>%s</b>%s%s</div>' % (
        e(c["name"]), '<span class="muted small">target %s</span>' % e(c["target"]) if c["target"] else "",
        '<span class="why small">%s</span>' % e(c["sequence"]) if c["sequence"] else "")
        for c in cols)
    rows = ""
    for key, label, lsub in LANES:
        rows += '<div class="rm-lane-h %s"><b>%s</b><span class="muted small">%s · %d open</span></div>' % (
            key, e(label), e(lsub), rm["open"][key])
        rows += "".join('<ul class="rm-cell %s">%s</ul>' % (
            key, "".join(card(x) for x in c["lanes"][key]) or '<li class="muted small">–</li>') for c in cols)
    grid = ('<div class="scroll"><div class="rm" style="--cols:%d"><div class="rm-corner"></div>%s%s</div></div>'
            % (len(cols), head, rows)) if cols else '<p class="muted">Everything planned is done. Add the next milestone to docs/BACKLOG.md.</p>'
    return ('<div class="card"><h2>Roadmap: proposed sequence</h2>'
            '<p class="muted small">Numbers are the proposed build order across both lanes (1 = next up), following '
            'milestone and item order in docs/BACKLOG.md; the line under a milestone says why. Lanes come from tags; '
            'open items in docs/TECH-DEBT.md continue the sequence in the foundation lane.</p>%s%s%s</div>'
            % (nxt, done, grid))


def tab_parts(d):
    """Generated tab markup and CSS from TABS (the Overview and Roadmap panels stay in TEMPLATE)."""
    inputs = "\n".join('<input type="radio" name="tab" id="tab-%s" class="tab-input"%s>' % (k, " checked" if i == 0 else "")
                       for i, (k, _l, _m) in enumerate(TABS))
    nav = "".join('<label for="tab-%s">%s</label>' % (k, e(lab)) for k, lab, _m in TABS)
    panels = "\n".join('<div class="panel panel-%s">%s</div>' % (k, m.render(d[k])) for k, _l, m in TABS if m)
    each = lambda fmt: ", ".join(fmt % (k, k) for k, _l, _m in TABS)  # noqa: E731
    css = ("%s {{ display:block; }}\n%s {{ color:var(--text-primary); font-weight:600; border-bottom-color:var(--border-interactive); }}\n%s {{ outline:2px solid var(--focus); outline-offset:-2px; }}"
           % (each("#tab-%s:checked ~ .panel-%s"), each('#tab-%s:checked ~ .tabs label[for="tab-%s"]'),
              each('#tab-%s:focus-visible ~ .tabs label[for="tab-%s"]'))).replace("{{", "{").replace("}}", "}")
    return {"tab_inputs": inputs, "tab_nav": nav, "tab_panels": panels, "tab_css": css}


def render(d):
    m, v, bl, debt = d["metrics"], d["versions"], d["backlog"], d["debt"]
    name = d["project"].get("name") or "Untitled project"
    phase_i = PHASES.index(d["phase"]) if d["phase"] in PHASES else len(PHASES) - 1
    steps = "".join('<li class="%s">%s</li>' % ("done" if i < phase_i else "now" if i == phase_i else "", e(p))
                    for i, p in enumerate(PHASES))
    if d.get("template_mode"):
        steps = '<li class="now">Template maintenance</li><li>mode: template (origin matches template.source_repo)</li>'
    chips = "".join('<span class="chip">%s</span>' % e(p) for p in
                    [d["paths"].get("primary")] + list(d["paths"].get("secondary") or []) if p)

    progress_tile = tile("Progress", "%d%%" % d["progress"]["pct"], "%d done · %d open" % (
        bl["counts"]["done"], bl["counts"]["todo"] + bl["counts"]["doing"] + bl["counts"]["blocked"]))
    tiles = "".join([
        "" if d.get("template_mode") else progress_tile,
        tile("Full test run", fmt_num(m["test_seconds"], "s", 1), "budget %ss" % e(m["test_budget"]),
             status(m["test_seconds"], m["test_budget"]), spark(m["series"]["test_seconds"], "Test time")),
        tile("Coverage", fmt_num(m["coverage"], "%", 1), "min %s%%" % e(m["coverage_min"]),
             status(m["coverage"], m["coverage_min"], True), spark(m["series"]["coverage"], "Coverage")),
        tile("Test pass rate", fmt_num(m["pass_rate"], "%"), "last 20 runs",
             "na" if m["pass_rate"] is None else ("ok" if m["pass_rate"] >= 95 else "warn"),
             words=("healthy", "check flaky tests", "failing")),
        tile("Deploys", fmt_num(m["deploys"]), "failure rate %s (last 10)" % fmt_num(m["deploy_fail_rate"], "%"),
             "na" if m["deploy_fail_rate"] is None else ("ok" if m["deploy_fail_rate"] <= 20 else "bad"),
             words=("healthy", "watch", "unstable")),
        tile("Cost / session", fmt_num(m["tokens_avg"]), "weighted tokens · cache hit %s" % fmt_num(m["cache_hit"], "%"),
             status(m["tokens_avg"], m["tokens_warn"]), spark(m["series"]["tokens"], "Tokens per session")),
        tile("Open tech debt", str(len(debt["open"])), "%d high impact · %d markers" % (
            debt["by_impact"]["high"], debt["signals"]["marker_total"]),
             "bad" if debt["by_impact"]["high"] else ("warn" if debt["open"] else "ok"),
             words=("clear", "manageable", "high impact open")),
    ])

    ms_rows = "".join(
        '<li><div class="row"><span class="name">%s</span><span class="muted small">%s%d/%d</span></div>%s</li>'
        % (e(ms["name"]), ("target %s · " % e(ms["target"])) if ms["target"] else "", ms["done"], ms["total"],
           bar(ms["pct"], ms["name"]))
        for ms in d["progress"]["milestones"] if ms["total"]) or '<li class="muted">No milestones yet. Add them in docs/BACKLOG.md.</li>'

    def lst(items, empty):
        return "".join("<li>%s</li>" % e(i) for i in items) or '<li class="muted">%s</li>' % e(empty)

    c = bl["counts"]
    backlog = ('<div class="counts">%s</div>' % "".join(
        '<div class="count %s"><b>%d</b><span>%s</span></div>' % (k, c[k], k) for k in ("todo", "doing", "blocked", "done"))
        + '<h3>In progress</h3><ul class="plain">%s</ul>' % lst(bl["doing"], "nothing in progress")
        + '<h3>Blocked</h3><ul class="plain">%s</ul>' % lst(bl["blocked"], "nothing blocked")
        + '<h3>Up next</h3><ul class="plain">%s</ul>' % lst(bl["next"], "backlog empty"))

    sig = debt["signals"]
    debt_rows = "".join('<tr><td class="mono">%s</td><td>%s</td><td><span class="imp %s">%s</span></td><td>%s</td><td>%s</td></tr>'
                        % (e(x["id"]), e(x["title"]), e(x["impact"] or "na"), e(x["impact"] or "–"), e(x["effort"] or "–"),
                           e(x["area"] or "–")) for x in sorted(
                               debt["open"], key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["impact"], 3)))
    debt_html = (('<div class="scroll"><table><thead><tr><th>ID</th><th>Item</th><th>Impact</th><th>Effort</th><th>Area</th></tr></thead>'
                  '<tbody>%s</tbody></table></div>' % debt_rows) if debt_rows
                 else '<p class="muted">No open items in docs/TECH-DEBT.md.</p>')
    markers = ", ".join("%s %d" % (k, n) for k, n in sorted(sig["markers"].items())) or "none"
    debt_html += ('<h3>Automated signals</h3><ul class="plain"><li>Code markers: %s</li>'
                  '<li>Files over %d lines: %s</li><li>Import cycles: %s</li><li>Resolved items: %d</li></ul>'
                  % (e(markers), LARGE_FILE_LINES,
                     e(", ".join("%s (%d)" % (x["file"], x["lines"]) for x in sig["large_files"][:5]) or "none"),
                     e(sig["import_cycles"] if sig["import_cycles"] is not None else
                       "n/a (needs codegraph with the `cycles` command)" if f_codegraph() else "enable codegraph to track"),
                     debt["resolved"]))

    tag_rows = "".join("<tr><td class=\"mono\">%s</td><td>%s</td></tr>" % (e(t["tag"]), e(t["date"])) for t in v["tags"]) \
        or '<tr><td colspan="2" class="muted">No release tags yet (git tag v0.1.0).</td></tr>'
    dep_rows = "".join('<tr><td class="nowrap">%s</td><td>%s</td><td class="mono">%s</td><td>%s</td><td>%s</td></tr>'
                       % (e(r["ts"][5:16].replace("T", " ")), e(r.get("env")), e(r.get("sha") or "–"),
                          '<span class="imp %s">%s</span>' % ("low" if r["ok"] else "high", "ok" if r["ok"] else "failed"),
                          fmt_num(r.get("seconds"), "s")) for r in m["recent_deploys"]) \
        or '<tr><td colspan="5" class="muted">No deploys recorded (python3 scripts/metrics.py deploy).</td></tr>'
    commits = "".join('<li><span class="mono">%s</span> <span class="muted small">%s</span> %s</li>'
                      % (e(x["sha"]), e(x["date"]), e(x["subject"])) for x in v["commits"])
    alerts = "".join('<li class="alert">%s</li>' % e(a) for a in m["alerts"]) or '<li class="muted">No alerts.</li>'
    ideas = "".join("<li>%s</li>" % e(i) for i in m["suggestions"][:6]) or '<li class="muted">No suggestions.</li>'
    prod = d["deploy"].get("production_url")
    if prod and re.match(r"https?://", str(prod)):
        live = ' · <a href="%s">%s</a>' % (e(prod), e(prod))
    else:
        live = " · %s" % e(prod) if prod else ""

    first, third = ("Progress by milestone", '<ul class="ms">%s</ul>' % ms_rows), ("Tech debt", debt_html)
    if d.get("template_mode"):  # open tech debt first, then template work (Unplanned backlog items)
        work = lst(d["template_work"], "no open template work in docs/BACKLOG.md (Unplanned)")
        first, third = ("Template maintenance: open tech debt", debt_html), (
            "Template work", '<ul class="plain">%s</ul>' % work)
    return TEMPLATE.format(
        h_first=first[0], c_first=first[1], h_third=third[0], c_third=third[1],
        title=e(name + " status"), name=e(name), one_liner=e(d["project"].get("one_liner") or ""),
        steps=steps, chips=chips or '<span class="chip muted">path not chosen</span>',
        version=e(v["current"]), sha=e(v["sha"] or "no commits"), branch=e(v["branch"]), live=live,
        generated=e(d["generated"].replace("T", " ").replace("+00:00", " UTC")),
        tree=e(d["template"].get("decision_tree_version", "")), tiles=tiles, milestones=ms_rows,
        backlog=backlog, debt=debt_html, tags=tag_rows, deploys=dep_rows,
        commits=commits or '<li class="muted">No commits yet.</li>', alerts=alerts, ideas=ideas,
        commit_count=v["commit_count"], theme_css=theme.css(), roadmap=roadmap_views.render(d["roadmap_views"], render_roadmap(d["roadmap"])), delivery=delivery.render(d["delivery"]), **tab_parts(d))


def md(x):
    """Escape Markdown/table metacharacters in repo-derived text."""
    s = re.sub(r"\s*[\r\n]+\s*", " ", "" if x is None else str(x))
    return re.sub(r"([\\|`*_\[\]<>])", r"\\\1", s)


def summary(d):
    m, bl, debt = d["metrics"], d["backlog"]["counts"], d["debt"]
    tm = d.get("template_mode")
    lines = [
        "## %s — dashboard" % md(d["project"].get("name") or "project"),
        "",
        "| | |", "|---|---|",
    ] + ([] if tm else [
        "| Phase / path | %s / %s |" % (md(d["phase"]), md(d["paths"].get("primary") or "–"))]) + [
        "| Version | %s (%s) |" % (md(d["versions"]["current"]), md(d["versions"]["sha"] or "–")),
    ] + ([] if tm else [
        "| Progress | %d%% — %d done, %d doing, %d blocked, %d todo |" % (
            d["progress"]["pct"], bl["done"], bl["doing"], bl["blocked"], bl["todo"])]) + [
        "| Tests | %s (budget %ss), pass rate %s |" % (fmt_num(m["test_seconds"], "s", 1), m["test_budget"],
                                                     fmt_num(m["pass_rate"], "%")),
        "| Coverage | %s (min %s%%) |" % (fmt_num(m["coverage"], "%", 1), m["coverage_min"]),
        "| Deploys | %s, failure rate %s |" % (m["deploys"], fmt_num(m["deploy_fail_rate"], "%")),
        "| Weighted tokens / session | %s, cache hit %s |" % (fmt_num(m["tokens_avg"]), fmt_num(m["cache_hit"], "%")),
        "| Tech debt | %d open (%d high), %d code markers |" % (
            len(debt["open"]), debt["by_impact"]["high"], debt["signals"]["marker_total"]),
    ]
    for key, label, mod in TABS:
        if mod:
            lines.append("| %s | %s |" % (label, mod.line(d[key])))
    lines.append("| Size | %s |" % size.line(d["hotspots"]["size"]))
    lines.append("| Acceptance | %s |" % tab_gates.acceptance_line((d.get("gates") or {}).get("acceptance")))
    ci_line = delivery.line(d["delivery"])
    if ci_line:
        lines.append("| CI | %s |" % ci_line)
    if tm:
        lines.insert(4, "| Mode | Template maintenance (origin matches template.source_repo) |")
        lines += ["", "**Open tech debt**", ""] + (
            ["- %s %s (impact: %s)" % (md(x["id"]), md(x["title"]), md(x["impact"] or "–")) for x in debt["open"]]
            or ["- none"])
        lines += ["", "**Template work (Unplanned backlog)**", ""] + (
            ["- " + md(t) for t in d["template_work"]] or ["- none"])
    if m["alerts"]:
        lines += ["", "**Alerts**", ""] + ["- " + md(a) for a in m["alerts"]]
    return "\n".join(lines) + "\n"


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{theme_css}
{tab_css}
</style>
</head>
<body>
<main>
<header>
  <div>
    <h1>{name}</h1>
    <div class="muted">{one_liner}</div>
    <ol class="steps" aria-label="Project phase">{steps}</ol>
    <div>{chips}</div>
  </div>
  <div class="meta">
    <div>Version <b class="mono">{version}</b> · <span class="mono">{branch}@{sha}</span>{live}</div>
    <div>{commit_count} commits · decision tree v{tree}</div>
    <div>Generated {generated}</div>
  </div>
</header>

{tab_inputs}
<nav class="tabs" aria-label="Dashboard views">{tab_nav}</nav>

<div class="panel panel-roadmap">{roadmap}</div>

<div class="panel panel-overview">
<section class="tiles" aria-label="Key metrics">{tiles}</section>

<section class="grid">
  <div class="card"><h2>{h_first}</h2>{c_first}</div>
  <div class="card"><h2>Backlog</h2>{backlog}</div>
  <div class="card"><h2>{h_third}</h2>{c_third}</div>
  <div class="card"><h2>Alerts and suggestions</h2>
    <ul class="plain">{alerts}</ul><h3>Suggested improvements</h3><ul class="plain">{ideas}</ul></div>
  <div class="card"><h2>Versions</h2><div class="scroll"><table><thead><tr><th>Tag</th><th>Date</th></tr></thead><tbody>{tags}</tbody></table></div>
    <h3>Recent deploys</h3><div class="scroll"><table><thead><tr><th>When (UTC)</th><th>Env</th><th>Commit</th><th>Result</th><th>Time</th></tr></thead><tbody>{deploys}</tbody></table></div></div>
  {delivery}
  <div class="card"><h2>Recent commits</h2><ul class="plain">{commits}</ul></div>
</section>
</div>
{tab_panels}
<footer>Built by scripts/dashboard.py from factory.json, docs/BACKLOG.md, docs/TECH-DEBT.md, metrics/ and git.</footer>
</main>
</body>
</html>
"""


def build():
    d = collect()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render(d))
    with open(os.path.join(OUT, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, default=str)
    with open(os.path.join(OUT, "SUMMARY.md"), "w", encoding="utf-8") as fh:
        fh.write(summary(d))
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--print", action="store_true", dest="print_summary")
    a = ap.parse_args()
    d = build()
    if a.print_summary:
        print(summary(d), end="")
    else:
        print("dashboard written to dashboard/index.html")
    if a.open:
        webbrowser.open("file://" + os.path.join(OUT, "index.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build the project dashboard: versions, progress, backlog, tech debt, key metrics.

  python3 scripts/dashboard.py            # write dashboard/index.html, data.json, SUMMARY.md
  python3 scripts/dashboard.py --open     # ...and open it in a browser
  python3 scripts/dashboard.py --print    # print SUMMARY.md (cheap status for agents)

Sources (all in the repo, so every build can regenerate it):
  factory.json, docs/BACKLOG.md, docs/TECH-DEBT.md, metrics/*.jsonl, git tags/log,
  plus automated debt signals (TODO/FIXME markers, oversized files, codegraph import cycles).
Output is a self-contained HTML file (no JS, no network) with two tabs: Overview and Roadmap
(two swimlanes, value vs technical foundation, in proposed sequence). dashboard/ is git-ignored;
CI uploads it as a build artifact and writes SUMMARY.md to the job summary.
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402

OUT = os.path.join(ROOT, "dashboard")
PHASES = ["brainstorm", "operating-model", "build"]
STATES = {" ": "todo", "~": "doing", "x": "done", "X": "done", "!": "blocked", "-": "dropped"}
ITEM_RE = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(.*)$")
MILESTONE_RE = re.compile(r"^##\s+(?:Milestone:\s*)?(.+?)\s*(?:\(target:\s*([0-9-]*)\s*\))?\s*$")
DEBT_RE = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(TD-\d+)\s+(.*?)(?:\s+[—-]\s+(.*))?$")
MARKER_RE = r"\b(TODO|FIXME|HACK|XXX)\b"
SKIP_DIRS = ("docs/", ".claude/", ".factory/", "dashboard/", "metrics/", "templates/",
             "scripts/dashboard.py", "README.md", "CLAUDE.md")
LARGE_FILE_LINES = 500
# Roadmap swimlanes: backlog items whose tags hit FOUNDATION_TAGS (or #foundation) go to the
# technical-foundation lane; everything else is user value. Open tech-debt items always go to foundation.
FOUNDATION_TAGS = {"foundation", "tech", "arch", "architecture", "infra", "runway", "debt", "tech-debt",
                   "refactor", "quality", "ci", "process", "security", "perf", "ops", "platform"}
LANES = (("value", "Value-driven features", "value for users"),
         ("foundation", "Technical foundation", "architecture, runway, tech debt"))


# ---------------------------------------------------------------- sources

def git(*args):
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return p.stdout.strip() if p.returncode == 0 else ""
    except OSError:
        return ""


def read(path):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def strip_code(text):
    return re.sub(r"```.*?```", "", text, flags=re.S)


def parse_backlog(text):
    milestones, current = [], None
    for line in strip_code(text).splitlines():
        m = MILESTONE_RE.match(line)
        if line.startswith("## ") and m:
            current = {"name": m.group(1).strip(), "target": m.group(2) or "", "items": []}
            milestones.append(current)
            continue
        im = ITEM_RE.match(line)
        if im and current is not None:
            title = im.group(2).strip()
            size = re.search(r"\((S|M|L)\)", title)
            current["items"].append({
                "state": STATES.get(im.group(1), "todo"),
                "title": re.sub(r"\s*\((S|M|L)\)|\s*#[\w-]+", "", title).strip(),
                "size": size.group(1) if size else "",
                "tags": re.findall(r"#([\w-]+)", title),
            })
    for ms in milestones:
        live = [i for i in ms["items"] if i["state"] != "dropped"]
        done = sum(i["state"] == "done" for i in live)
        ms["total"], ms["done"] = len(live), done
        ms["pct"] = round(100.0 * done / len(live)) if live else 0
    return milestones


def parse_debt(text):
    items, section = [], ""
    for line in strip_code(text).splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        m = DEBT_RE.match(line)
        if not m:
            continue
        attrs = dict(re.findall(r"(\w+):\s*([^·]+?)\s*(?:·|$)", m.group(4) or ""))
        items.append({
            "id": m.group(2), "title": m.group(3).strip(),
            "open": m.group(1) not in "xX" and not section.startswith("resolved"),
            "impact": attrs.get("impact", "").lower(), "effort": attrs.get("effort", ""),
            "area": attrs.get("area", ""),
        })
    return items


def debt_signals(f):
    files = [p for p in git("ls-files").splitlines() if p and not p.startswith(SKIP_DIRS)]
    markers = {}
    out = git("grep", "-I", "-o", "-E", MARKER_RE, "--", *files) if files else ""
    for line in out.splitlines():
        kind = line.rsplit(":", 1)[-1]
        markers[kind] = markers.get(kind, 0) + 1
    large = []
    for p in files:
        full = os.path.join(ROOT, p)
        if os.path.isfile(full) and not p.endswith((".json", ".lock", ".md", ".svg", ".csv")):
            try:
                with open(full, "rb") as fh:
                    n = sum(1 for _ in fh)
            except OSError:
                continue
            if n > LARGE_FILE_LINES:
                large.append({"file": p, "lines": n})
    cycles = None
    if f.get("integrations", {}).get("codegraph") and shutil.which("codegraph"):
        try:
            p = subprocess.run(["codegraph", "cycles", "--json"], cwd=ROOT, capture_output=True, text=True,
                               timeout=60, check=False)
            if p.returncode not in (0, 1):  # 1 = cycles found; anything else = unsupported/failed
                raise ValueError(p.stderr[:200])
            data = json.loads(p.stdout or "[]")
            cycles = len(data if isinstance(data, list) else data.get("cycles", []))
        except (OSError, ValueError, subprocess.SubprocessError):
            cycles = None
    return {"markers": markers, "marker_total": sum(markers.values()),
            "large_files": sorted(large, key=lambda x: -x["lines"])[:10], "import_cycles": cycles}


def versions():
    current = read("VERSION").strip()
    if not current:
        for path, pat in (("package.json", r'"version"\s*:\s*"([^"]+)"'),
                          ("pyproject.toml", r'(?m)^version\s*=\s*"([^"]+)"'),
                          ("Cargo.toml", r'(?m)^version\s*=\s*"([^"]+)"')):
            m = re.search(pat, read(path))
            if m:
                current = m.group(1)
                break
    tags = []
    for line in git("for-each-ref", "refs/tags", "--sort=-creatordate", "--count=8",
                    "--format=%(refname:short)|%(creatordate:short)").splitlines():
        name, _, date = line.partition("|")
        tags.append({"tag": name, "date": date})
    if not current and tags:
        current = tags[0]["tag"]
    commits = []
    for line in git("log", "-8", "--format=%h|%cs|%s").splitlines():
        sha, date, subj = (line.split("|", 2) + ["", ""])[:3]
        commits.append({"sha": sha, "date": date, "subject": subj})
    return {"current": current or "unreleased", "tags": tags, "commits": commits,
            "sha": git("rev-parse", "--short", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "commit_count": int(git("rev-list", "--count", "HEAD") or 0)}


def metric_view(f):
    hist, toks = metrics.load(metrics.HISTORY), metrics.load(metrics.TOKENS)
    alerts, ideas, _ = metrics.analyse(f, hist, toks)
    full = [r for r in hist if r["kind"] == "test" and r.get("scope") == "full"]
    deps = [r for r in hist if r["kind"] == "deploy"]
    b = f.get("budgets", {})
    last = full[-1] if full else {}
    cov = [r["coverage_pct"] for r in full if r.get("coverage_pct") is not None]
    recent = full[-20:]
    recent_deps = deps[-10:]
    tok_recent = toks[-10:]
    cached = sum(r.get("cache_read_input_tokens", 0) for r in tok_recent)
    inp = cached + sum(r.get("input_tokens", 0) + r.get("cache_creation_input_tokens", 0) for r in tok_recent)
    return {
        "test_seconds": last.get("seconds"), "test_budget": b.get("test_seconds"),
        "test_ok": last.get("ok"),
        "pass_rate": round(100.0 * sum(r["ok"] for r in recent) / len(recent)) if recent else None,
        "coverage": cov[-1] if cov else None, "coverage_min": b.get("min_coverage_pct"),
        "deploys": len(deps),
        "deploy_fail_rate": round(100.0 * sum(not r["ok"] for r in recent_deps) / len(recent_deps)) if recent_deps else None,
        "deploy_seconds": deps[-1]["seconds"] if deps else None, "deploy_budget": b.get("deploy_seconds"),
        "last_deploy": deps[-1] if deps else None, "recent_deploys": list(reversed(deps[-6:])),
        "tokens_avg": round(sum(metrics.wt(r) for r in tok_recent) / len(tok_recent)) if tok_recent else None,
        "tokens_warn": b.get("session_weighted_tokens_warn"),
        "cache_hit": round(100.0 * cached / inp) if inp else None,
        "series": {"test_seconds": [r["seconds"] for r in full[-30:]], "coverage": cov[-30:],
                   "tokens": [metrics.wt(r) for r in toks[-30:]]},
        "alerts": alerts, "suggestions": ideas,
    }


def lane_of(tags):
    tags = {t.lower() for t in tags}
    if "value" in tags or "feature" in tags:
        return "value"
    return "foundation" if tags & FOUNDATION_TAGS else "value"


def roadmap(backlog, open_debt):
    """Proposed sequence: milestones in BACKLOG.md order become columns, items keep their file order,
    and open items are numbered per lane (1 = next up). Open debt not yet scheduled is a final column."""
    columns, seq = [], {"value": 0, "foundation": 0}
    debt_cards = [{"title": "%s %s" % (x["id"], x["title"]), "state": "todo", "size": x["effort"],
                   "lane": "foundation", "impact": x["impact"], "debt": True}
                  for x in sorted(open_debt, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["impact"], 3))]
    groups = [(ms["name"], ms["target"], ms["items"]) for ms in backlog]
    if debt_cards:
        groups.append(("Tech debt to schedule", "", debt_cards))
    for name, target, items in groups:
        cards = {"value": [], "foundation": []}
        for it in items:
            if it["state"] == "dropped":
                continue
            lane = it.get("lane") or lane_of(it.get("tags", []))
            card = {"title": it["title"], "state": it["state"], "size": it.get("size", ""),
                    "impact": it.get("impact", ""), "debt": it.get("debt", False), "seq": None}
            if it["state"] != "done":
                seq[lane] += 1
                card["seq"] = seq[lane]
            cards[lane].append(card)
        if cards["value"] or cards["foundation"]:
            columns.append({"name": name, "target": target, "lanes": cards})
    return {"columns": columns, "open": dict(seq)}


def collect():
    f = metrics.factory()
    backlog = parse_backlog(read("docs/BACKLOG.md"))
    items = [i for m in backlog for i in m["items"]]
    counts = {s: sum(i["state"] == s for i in items) for s in ("todo", "doing", "blocked", "done", "dropped")}
    debt = parse_debt(read("docs/TECH-DEBT.md"))
    open_debt = [d for d in debt if d["open"]]
    planned = [m for m in backlog if m["total"]]
    total = sum(m["total"] for m in planned)
    return {
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
        "metrics": metric_view(f),
    }


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
    if not cols:
        return ('<div class="card"><p class="muted">No roadmap yet. Add milestones and items to docs/BACKLOG.md; '
                'tag foundation work with #foundation (or #arch, #infra, #runway, #debt, #quality...).</p></div>')

    def card(c):
        badges = "".join([
            '<span class="imp %s">%s</span>' % (e(c["impact"]), e(c["impact"])) if c["impact"] else "",
            '<span class="size">%s</span>' % e(c["size"]) if c["size"] else "",
            '<span class="state">%s</span>' % e(c["state"]) if c["state"] in ("doing", "blocked") else ""])
        num = '<span class="seq">%d</span>' % c["seq"] if c["seq"] else '<span class="seq">&#10003;</span>'
        return '<li class="rm-card %s">%s<span class="t">%s</span>%s</li>' % (
            e(c["state"]), num, e(c["title"]), '<span class="b">%s</span>' % badges if badges else "")

    head = "".join('<div class="rm-col-h"><b>%s</b>%s</div>' % (
        e(c["name"]), '<span class="muted small">target %s</span>' % e(c["target"]) if c["target"] else "")
        for c in cols)
    rows = ""
    for key, label, sub in LANES:
        rows += '<div class="rm-lane-h %s"><b>%s</b><span class="muted small">%s · %d open</span></div>' % (
            key, e(label), e(sub), rm["open"][key])
        rows += "".join('<ul class="rm-cell %s">%s</ul>' % (
            key, "".join(card(x) for x in c["lanes"][key]) or '<li class="muted small">–</li>') for c in cols)
    return ('<div class="card"><h2>Roadmap: proposed sequence</h2>'
            '<p class="muted small">Columns follow milestone order in docs/BACKLOG.md; numbers are the suggested order '
            'within each lane. Lanes come from tags; open items in docs/TECH-DEBT.md land in the foundation lane.</p>'
            '<div class="scroll"><div class="rm" style="--cols:%d">'
            '<div class="rm-corner"></div>%s%s</div></div></div>' % (len(cols), head, rows))


def render(d):
    m, v, bl, debt = d["metrics"], d["versions"], d["backlog"], d["debt"]
    name = d["project"].get("name") or "Untitled project"
    phase_i = PHASES.index(d["phase"]) if d["phase"] in PHASES else len(PHASES) - 1
    steps = "".join('<li class="%s">%s</li>' % ("done" if i < phase_i else "now" if i == phase_i else "", e(p))
                    for i, p in enumerate(PHASES))
    chips = "".join('<span class="chip">%s</span>' % e(p) for p in
                    [d["paths"].get("primary")] + list(d["paths"].get("secondary") or []) if p)

    tiles = "".join([
        tile("Progress", "%d%%" % d["progress"]["pct"], "%d done · %d open" % (
            bl["counts"]["done"], bl["counts"]["todo"] + bl["counts"]["doing"] + bl["counts"]["blocked"])),
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
    live = ' · <a href="%s">%s</a>' % (e(prod), e(prod)) if prod else ""

    return TEMPLATE.format(
        title=e(name + " status"), name=e(name), one_liner=e(d["project"].get("one_liner") or ""),
        steps=steps, chips=chips or '<span class="chip muted">path not chosen</span>',
        version=e(v["current"]), sha=e(v["sha"] or "no commits"), branch=e(v["branch"]), live=live,
        generated=e(d["generated"].replace("T", " ").replace("+00:00", " UTC")),
        tree=e(d["template"].get("decision_tree_version", "")), tiles=tiles, milestones=ms_rows,
        backlog=backlog, debt=debt_html, tags=tag_rows, deploys=dep_rows,
        commits=commits or '<li class="muted">No commits yet.</li>', alerts=alerts, ideas=ideas,
        commit_count=v["commit_count"], roadmap=render_roadmap(d["roadmap"]))


def summary(d):
    m, bl, debt = d["metrics"], d["backlog"]["counts"], d["debt"]
    lines = [
        "## %s — dashboard" % (d["project"].get("name") or "project"),
        "",
        "| | |", "|---|---|",
        "| Phase / path | %s / %s |" % (d["phase"], d["paths"].get("primary") or "–"),
        "| Version | %s (%s) |" % (d["versions"]["current"], d["versions"]["sha"] or "–"),
        "| Progress | %d%% — %d done, %d doing, %d blocked, %d todo |" % (
            d["progress"]["pct"], bl["done"], bl["doing"], bl["blocked"], bl["todo"]),
        "| Tests | %s (budget %ss), pass rate %s |" % (fmt_num(m["test_seconds"], "s", 1), m["test_budget"],
                                                     fmt_num(m["pass_rate"], "%")),
        "| Coverage | %s (min %s%%) |" % (fmt_num(m["coverage"], "%", 1), m["coverage_min"]),
        "| Deploys | %s, failure rate %s |" % (m["deploys"], fmt_num(m["deploy_fail_rate"], "%")),
        "| Weighted tokens / session | %s, cache hit %s |" % (fmt_num(m["tokens_avg"]), fmt_num(m["cache_hit"], "%")),
        "| Tech debt | %d open (%d high), %d code markers |" % (
            len(debt["open"]), debt["by_impact"]["high"], debt["signals"]["marker_total"]),
    ]
    if m["alerts"]:
        lines += ["", "**Alerts**", ""] + ["- " + a for a in m["alerts"]]
    return "\n".join(lines) + "\n"


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --bg:#f6f7f9; --surface:#ffffff; --text:#1b1f24; --muted:#5b6470; --border:#dfe3e8;
  --accent:#2f6fdb; --ok:#1f8a4c; --ok-bg:#e6f4ec; --bad:#c23934; --bad-bg:#fbeaea;
  --warn:#9a6700; --warn-bg:#fff4d6; --track:#e9edf2;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#0f1216; --surface:#171b21; --text:#e6e9ed; --muted:#9aa4b1; --border:#2a313a;
    --accent:#6ea0ff; --ok:#4cc38a; --ok-bg:#12291d; --bad:#ff7b72; --bad-bg:#2d1517;
    --warn:#e3b341; --warn-bg:#2b230f; --track:#262d36;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#0f1216; --surface:#171b21; --text:#e6e9ed; --muted:#9aa4b1; --border:#2a313a;
  --accent:#6ea0ff; --ok:#4cc38a; --ok-bg:#12291d; --bad:#ff7b72; --bad-bg:#2d1517;
  --warn:#e3b341; --warn-bg:#2b230f; --track:#262d36;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1180px; margin:0 auto; padding:24px 16px 48px; }}
header {{ display:flex; flex-wrap:wrap; gap:12px 24px; align-items:flex-end; justify-content:space-between; margin-bottom:20px; }}
h1 {{ font-size:24px; margin:0; letter-spacing:-.01em; }}
h2 {{ font-size:15px; margin:0 0 12px; }}
h3 {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:16px 0 6px; }}
.muted {{ color:var(--muted); }} .small {{ font-size:12px; }}
.mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }}
a {{ color:var(--accent); }}
.meta {{ color:var(--muted); font-size:13px; text-align:right; }}
.steps {{ display:flex; gap:6px; list-style:none; padding:0; margin:10px 0 0; flex-wrap:wrap; }}
.steps li {{ font-size:12px; padding:3px 10px; border-radius:999px; border:1px solid var(--border); color:var(--muted); }}
.steps li.done {{ color:var(--ok); border-color:var(--ok); }}
.steps li.now {{ background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }}
.chip {{ display:inline-block; font-size:12px; padding:2px 8px; border-radius:6px; background:var(--track); margin:6px 6px 0 0; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }}
.tile {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; border-top:3px solid var(--border); }}
.tile.ok {{ border-top-color:var(--ok); }} .tile.bad {{ border-top-color:var(--bad); }} .tile.warn {{ border-top-color:var(--warn); }}
.tile .label {{ font-size:12px; color:var(--muted); }}
.tile .value {{ font-size:24px; font-weight:650; font-variant-numeric:tabular-nums; margin:2px 0; }}
.tile .sub {{ font-size:12px; color:var(--muted); }}
.tile.ok .badge {{ color:var(--ok); }} .tile.bad .badge {{ color:var(--bad); font-weight:600; }} .tile.warn .badge {{ color:var(--warn); }}
.spark {{ width:100%; height:36px; margin-top:8px; display:block; }}
.spark polyline {{ fill:none; stroke:var(--accent); stroke-width:1.75; vector-effect:non-scaling-stroke; }}
.spark circle {{ fill:var(--accent); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px; min-width:0; }}
ul.plain, ul.ms {{ list-style:none; padding:0; margin:0; }}
ul.plain li {{ padding:4px 0; border-bottom:1px solid var(--border); font-size:14px; }}
ul.plain li:last-child {{ border-bottom:0; }}
ul.ms li {{ margin-bottom:12px; }}
.row {{ display:flex; justify-content:space-between; gap:8px; font-size:14px; }}
.bar {{ height:8px; background:var(--track); border-radius:999px; overflow:hidden; margin-top:4px; }}
.bar span {{ display:block; height:100%; background:var(--ok); border-radius:999px; }}
.counts {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }}
.count {{ background:var(--track); border-radius:8px; padding:8px; text-align:center; }}
.count b {{ display:block; font-size:20px; font-variant-numeric:tabular-nums; }}
.count span {{ font-size:12px; color:var(--muted); }}
.count.blocked b {{ color:var(--bad); }} .count.doing b {{ color:var(--accent); }} .count.done b {{ color:var(--ok); }}
.scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; font-size:12px; color:var(--muted); font-weight:600; padding:6px 8px; border-bottom:1px solid var(--border); }}
td.mono, td.nowrap {{ white-space:nowrap; }}
td {{ padding:6px 8px; border-bottom:1px solid var(--border); vertical-align:top; }}
.imp {{ font-size:12px; padding:1px 7px; border-radius:999px; background:var(--track); }}
.imp.high {{ background:var(--bad-bg); color:var(--bad); }} .imp.medium {{ background:var(--warn-bg); color:var(--warn); }}
.imp.low {{ background:var(--ok-bg); color:var(--ok); }}
li.alert {{ color:var(--bad); }}
footer {{ margin-top:24px; font-size:12px; color:var(--muted); }}
.tabs {{ display:flex; gap:4px; border-bottom:1px solid var(--border); margin-bottom:16px; }}
.tabs label {{ padding:8px 14px; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent; margin-bottom:-1px; font-weight:600; font-size:14px; }}
.tab-input {{ position:absolute; opacity:0; pointer-events:none; }}
.panel {{ display:none; }}
#tab-overview:checked ~ .panel-overview, #tab-roadmap:checked ~ .panel-roadmap {{ display:block; }}
#tab-overview:checked ~ .tabs label[for="tab-overview"], #tab-roadmap:checked ~ .tabs label[for="tab-roadmap"] {{ color:var(--text); border-bottom-color:var(--accent); }}
#tab-overview:focus-visible ~ .tabs label[for="tab-overview"], #tab-roadmap:focus-visible ~ .tabs label[for="tab-roadmap"] {{ outline:2px solid var(--accent); outline-offset:2px; }}
.rm {{ --lane-w:minmax(150px,180px); --col-w:minmax(220px,1fr); display:grid; gap:8px; min-width:max-content;
  grid-template-columns:var(--lane-w) repeat(var(--cols),var(--col-w)); }}
.rm-col-h {{ display:flex; flex-direction:column; font-size:14px; padding:4px 2px; border-bottom:2px solid var(--border); }}
.rm-lane-h {{ display:flex; flex-direction:column; justify-content:flex-start; font-size:14px; padding:10px; border-radius:8px; border-left:4px solid var(--accent); background:var(--track);
  position:sticky; left:0; z-index:1; box-shadow:8px 0 0 var(--surface); }}
.rm-lane-h.foundation {{ border-left-color:var(--warn); }}
.rm-cell {{ list-style:none; margin:0; padding:8px; border-radius:8px; background:var(--bg); border:1px dashed var(--border); display:flex; flex-direction:column; gap:6px; }}
.rm-card {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:6px; background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:6px; padding:6px 8px; font-size:13px; }}
.rm-cell.foundation .rm-card {{ border-left-color:var(--warn); }}
.rm-card .t {{ flex:1 1 120px; }}
.rm-card .b {{ display:flex; gap:4px; }}
.rm-card .seq {{ font-variant-numeric:tabular-nums; font-weight:650; color:var(--muted); min-width:1.4em; }}
.rm-card .size, .rm-card .state {{ font-size:11px; padding:0 6px; border-radius:999px; background:var(--track); color:var(--muted); }}
.rm-card.doing {{ box-shadow:inset 0 0 0 1px var(--accent); }} .rm-card.doing .state {{ color:var(--accent); }}
.rm-card.blocked .state {{ background:var(--bad-bg); color:var(--bad); }}
.rm-card.done {{ opacity:.55; }} .rm-card.done .t {{ text-decoration:line-through; }} .rm-card.done .seq {{ color:var(--ok); }}
@media (max-width:520px) {{ .rm {{ --lane-w:104px; --col-w:minmax(200px,1fr); }} .rm-lane-h {{ padding:8px; }} .meta {{ text-align:left; }} .grid {{ grid-template-columns:1fr; }} }}
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

<input type="radio" name="tab" id="tab-overview" class="tab-input" checked>
<input type="radio" name="tab" id="tab-roadmap" class="tab-input">
<nav class="tabs" aria-label="Dashboard views"><label for="tab-overview">Overview</label><label for="tab-roadmap">Roadmap</label></nav>

<div class="panel panel-roadmap">{roadmap}</div>

<div class="panel panel-overview">
<section class="tiles" aria-label="Key metrics">{tiles}</section>

<section class="grid">
  <div class="card"><h2>Progress by milestone</h2><ul class="ms">{milestones}</ul></div>
  <div class="card"><h2>Backlog</h2>{backlog}</div>
  <div class="card"><h2>Tech debt</h2>{debt}</div>
  <div class="card"><h2>Alerts and suggestions</h2>
    <ul class="plain">{alerts}</ul><h3>Suggested improvements</h3><ul class="plain">{ideas}</ul></div>
  <div class="card"><h2>Versions</h2><div class="scroll"><table><thead><tr><th>Tag</th><th>Date</th></tr></thead><tbody>{tags}</tbody></table></div>
    <h3>Recent deploys</h3><div class="scroll"><table><thead><tr><th>When (UTC)</th><th>Env</th><th>Commit</th><th>Result</th><th>Time</th></tr></thead><tbody>{deploys}</tbody></table></div></div>
  <div class="card"><h2>Recent commits</h2><ul class="plain">{commits}</ul></div>
</section>
</div>
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
        json.dump(d, fh, indent=1)
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

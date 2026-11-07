"""Docs health tab, from docs/knowledge-graph.json: orphan docs, docs stale vs the code they describe, components without docs."""
import html
import json
import re
import time

from . import sources as S

GRAPH = "docs/knowledge-graph.json"
ENTRY = ("CLAUDE.md", "docs/INDEX.md")  # entry points: never orphans
GENERATED = ("docs/INDEX.md",)
CAP = 15
PATH_RE = re.compile(r"[\w.-]+(?:/[\w.-]+)+")
EMPTY = "No docs graph yet: run `python3 scripts/docs_index.py` to generate docs/knowledge-graph.json."


def e(x):
    return html.escape(str(x), quote=True)


def stale_docs(root, nodes, times):
    """Docs whose last commit is older than the newest commit of a tracked code file they name."""
    out = []
    for n in nodes:
        if n["id"] in GENERATED or n["id"] not in times:
            continue
        mentioned = {p.rstrip(".") for p in PATH_RE.findall(S.read(root, n["id"]))}
        code = {p: times[p] for p in mentioned if p in times and not p.endswith(".md") and not p.startswith("docs/")}
        newer = sorted(p for p, t in code.items() if t > times[n["id"]])
        if newer:
            out.append({"doc": n["id"], "code": newer[:3], "code_total": len(newer)})
    return out


def collect(root, base):
    raw = S.read(root, GRAPH)
    try:
        g = json.loads(raw) if raw else None
    except ValueError:
        g = None
    if not isinstance(g, dict) or not g.get("nodes"):
        return {"graph": False, "nodes": 0, "edges": 0, "orphans": [], "stale": [], "uncovered": [], "components": 0}
    nodes, edges = g["nodes"], g.get("edges", [])
    linked = {x["from"] for x in edges} | {x["to"] for x in edges}
    orphans = sorted(n["id"] for n in nodes if n["id"] not in linked and n["id"] not in ENTRY)
    stale = stale_docs(root, nodes, S.commit_times(root))
    comps = sorted(x["path"] for x in (base.get("architecture") or {}).get("layers", {}).get("application", [])
                   if x["type"] == "application-component" and x.get("path"))
    text = "\n".join(S.read(root, n["id"]) for n in nodes if n["id"] not in GENERATED)
    uncovered = [c for c in comps if c not in text]
    return {"graph": True, "nodes": len(nodes), "edges": len(edges), "orphans": orphans, "stale": stale,
            "uncovered": uncovered, "components": len(comps), "generated_at": int(time.time())}


def line(d):
    if not d["graph"]:
        return "no docs graph yet"
    return "%d docs: %d orphan, %d stale vs code, %d of %d components without docs" % (
        d["nodes"], len(d["orphans"]), len(d["stale"]), len(d["uncovered"]), d["components"])


def _list(title, items, empty):
    li = "".join("<li>%s</li>" % x for x in items[:CAP])
    if len(items) > CAP:
        li += '<li class="muted">+%d more; full list in data.json</li>' % (len(items) - CAP)
    return "<h3>%s (%d)</h3><ul class=\"plain\">%s</ul>" % (e(title), len(items), li or '<li class="muted">%s</li>' % e(empty))


def render(d):
    if not d["graph"]:
        return '<div class="card"><h2>Docs health</h2><p class="muted">%s</p></div>' % e(EMPTY)
    stale = ['<span class="mono">%s</span> <span class="muted">older than %s%s</span>' % (
        e(s["doc"]), e(", ".join(s["code"])), e(" +%d" % (s["code_total"] - len(s["code"])) if s["code_total"] > len(s["code"]) else ""))
        for s in d["stale"]]
    return ('<div class="stack"><div class="card"><h2>Docs health</h2><p class="muted small">From %s: %d docs, %d links. '
            'Orphan = no links in or out (CLAUDE.md and INDEX.md excepted). Stale = a code file the doc names was committed after the doc. '
            'Component without docs = its path is named in no doc.</p></div><div class="card">%s</div><div class="card">%s</div><div class="card">%s</div></div>'
            % (GRAPH, d["nodes"], d["edges"],
               _list("Orphan docs", ['<span class="mono">%s</span>' % e(o) for o in d["orphans"]], "none"),
               _list("Stale docs", stale, "none"),
               _list("Components without docs", ['<span class="mono">%s</span>' % e(c) for c in d["uncovered"]],
                     "none" if d["components"] else "no components yet (see the Architecture tab)")))

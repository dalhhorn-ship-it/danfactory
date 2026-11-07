"""Architecture model (ArchiMate subset): generated layers, curated intent, drift, docs/architecture.json."""
import json
import os
import re

from . import sources as S

MODEL_FILE = "docs/architecture.json"
CANDIDATE_ROOTS = ("src", "app", "worker", "lib", "packages", "functions")
TEMPLATE_OWNED = (".claude", ".factory", "docs", "scripts", "templates", "dashboard", "metrics", "node_modules")
LAYER_OF = {"goal": "motivation", "requirement": "motivation", "principle": "motivation",
            "application-component": "application", "application-interface": "application", "data-object": "application",
            "node": "technology", "technology-service": "technology"}
TYPE_ORDER = {t: i for i, t in enumerate(LAYER_OF)}
LAYERS = ("motivation", "application", "technology")
JS_IMPORT = re.compile(r"""(?:from\s+|import\s*\(\s*|require\(\s*|import\s+)["'](\.{1,2}/[^"']*)["']""")
PY_IMPORT = re.compile(r"(?m)^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")


def _el(id_, type_, name, path="", **attrs):
    el = {"id": id_, "type": type_, "name": name, "layer": LAYER_OF[type_]}
    if path:
        el["path"] = path
    if attrs:
        el["attrs"] = attrs
    return el


def _rel(type_, source, target):
    return (type_, source, target)


def load(root):
    try:
        with open(os.path.join(root, MODEL_FILE), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _curated(root):
    c = (load(root) or {}).get("curated") or {}
    return {"roots": list(c.get("roots") or []), "exclude": list(c.get("exclude") or []),
            "elements": list(c.get("elements") or []), "relations": list(c.get("relations") or [])}


def source_roots(root, curated):
    if curated["roots"]:
        return [r.strip("/") for r in curated["roots"]]
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            name = (json.load(fh).get("project") or {}).get("name")
        if not name:
            return ["scripts"]  # un-bootstrapped template: show the factory itself as a demo
    except (OSError, ValueError):
        pass
    return [r for r in CANDIDATE_ROOTS if os.path.isdir(os.path.join(root, r))][:1]


def _files_under(root, rel):
    full = os.path.join(root, rel)
    if os.path.isfile(full):
        return [rel] if rel.endswith(S.SRC_EXT) else []
    out = []
    for d, dirs, files in os.walk(full):
        dirs[:] = sorted(x for x in dirs if not x.startswith((".", "__")) and x != "node_modules")
        out += [os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/") for f in sorted(files)
                if f.endswith(S.SRC_EXT) and not S.is_test(os.path.join(os.path.relpath(d, root), f).replace(os.sep, "/"))]
    return out


def components(root, roots, exclude):
    out = []
    for r in roots:
        base = os.path.join(root, r)
        if not os.path.isdir(base):
            continue
        for child in sorted(os.listdir(base)):
            rel = "%s/%s" % (r, child)
            if child.startswith((".", "__")) or child == "node_modules" or S.is_test(rel + ("/" if os.path.isdir(os.path.join(root, rel)) else "")):
                continue
            if any(rel == x.strip("/") or rel.startswith(x.rstrip("/") + "/") for x in exclude):
                continue
            files = _files_under(root, rel)
            if files:
                out.append({"el": _el("app:" + rel, "application-component", child, rel), "files": files})
    return out


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _owner(comps, path):
    for c in comps:
        p = c["el"]["path"]
        if path == p or path.startswith(p + "/"):
            return c["el"]["id"]
    return None


def import_edges(root, comps):
    """`serving` relations from a regex scan of relative/sibling imports (the codegraph path is TD-004)."""
    by_stem = {_stem(c["el"]["path"]): c["el"]["id"] for c in comps}
    rels = set()
    for c in comps:
        me = c["el"]["id"]
        for f in c["files"]:
            text = S.read(root, f)[:300000]
            targets = []
            if f.endswith(".py"):
                for m in PY_IMPORT.finditer(text):
                    name = (m.group(1) or m.group(2)).split(".")[0]
                    if name in by_stem:
                        targets.append(by_stem[name])
            else:
                for spec in JS_IMPORT.findall(text):
                    res = os.path.normpath(os.path.join(os.path.dirname(f), spec)).replace(os.sep, "/")
                    for o in comps:
                        p = o["el"]["path"]
                        if res == p or res.startswith(p + "/") or os.path.splitext(p)[0] == res:
                            targets.append(o["el"]["id"])
            rels.update(_rel("serving", t, me) for t in targets if t != me)
    return rels


def _mentions(root, comps, word):
    pat = re.compile(r"(?<![\w])%s(?![\w])" % re.escape(word))
    return [c["el"]["id"] for c in comps if any(pat.search(S.read(root, f)[:300000]) for f in c["files"])]


def generate(root):
    """The `generated` section: derived fresh from the repo, deterministic."""
    cur = _curated(root)
    els, rels = {}, set()

    def put(el):
        els[el["id"]] = el

    goal = S.goal_outcome(root)
    if goal:
        put(_el("goal:outcome", "goal", " ".join(goal.split())[:60]))
    for p in S.prds(root):
        rid = "req:" + p["slug"]
        put(_el(rid, "requirement", p["title"], status=p["status"], approved=p["approved"], ac=p["ac"]))
        if goal:
            rels.add(_rel("realization", rid, "goal:outcome"))
    comps = components(root, source_roots(root, cur), cur["exclude"])
    for c in comps:
        put(c["el"])
    rels |= import_edges(root, comps)
    for a in S.adrs(root):
        aid = "adr:" + a["num"]
        put(_el(aid, "principle", a["title"], status=a["status"]))
        for c in comps:
            if re.search(r"%s(?![\w-])" % re.escape(c["el"]["path"]), a["text"]):
                rels.add(_rel("influence", aid, c["el"]["id"]))
    w = S.wrangler(root)
    entry = _owner(comps, w["main"]) if w and w["main"] else None
    if w and w["main"]:
        put(_el("if:http", "application-interface", "HTTP (fetch)", w["main"]))
        if entry:
            rels.add(_rel("serving", entry, "if:http"))
    for t in S.tables(root):
        put(_el("data:" + t, "data-object", t))
        rels.update(_rel("access", c, "data:" + t) for c in _mentions(root, comps, t))
    if w:
        if w["name"]:
            put(_el("node:" + w["name"], "node", w["name"]))
            if entry:
                rels.add(_rel("assignment", "node:" + w["name"], entry))
        for b in w["bindings"]:
            users = _mentions(root, comps, b["name"])
            sid = "svc:" + b["name"]
            put(_el(sid, "technology-service", "%s (%s)" % (b["name"], b["kind"]), kind=b["kind"], used=bool(users)))
            rels.update(_rel("serving", sid, u) for u in users)
    return {"source": "scan", "elements": sorted(els.values(), key=lambda e: e["id"]),
            "relations": [{"type": t, "source": a, "target": b} for t, a, b in sorted(rels)]}


def dumps(model):
    return json.dumps(model, sort_keys=True, indent=1) + "\n"


def write(root):
    """Rewrite only `generated`; curated stays verbatim. Returns True if the file changed."""
    old = load(root) or {}
    model = {"schema": 1, "curated": old.get("curated") or {"roots": [], "exclude": [], "elements": [], "relations": []},
             "generated": generate(root)}
    text = dumps(model)
    path = os.path.join(root, MODEL_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


def view(root, generated=None):
    """Merged generated + curated model with drift, for the tab and data.json."""
    cur = _curated(root)
    gen = generated or generate(root)
    els = {e["id"]: dict(e, origin="generated", drift=False) for e in gen["elements"]}
    by_path = {e["path"]: e["id"] for e in els.values() if e["type"] == "application-component"}
    idmap, designed_not_built = {}, []
    for c in cur["elements"]:
        if not isinstance(c, dict) or c.get("type") not in LAYER_OF or not c.get("id"):
            continue
        tid = c["id"] if c["id"] in els else by_path.get(c.get("path"), c["id"])
        idmap[c["id"]] = tid
        if tid in els:
            els[tid].update({k: c[k] for k in ("name", "type") if c.get(k)}, origin="both")
            els[tid]["layer"] = LAYER_OF[els[tid]["type"]]
        else:
            els[tid] = dict(c, id=tid, layer=LAYER_OF[c["type"]], origin="curated", drift=False)
        if els[tid]["layer"] == "application" and c.get("path") and not os.path.exists(os.path.join(root, c["path"])):
            designed_not_built.append(tid)
    intent = any(e["origin"] != "generated" and e["type"] == "application-component" for e in els.values())
    built_not_designed = sorted(e["id"] for e in els.values()
                                if intent and e["origin"] == "generated" and e["type"] == "application-component")
    unused = sorted(e["id"] for e in els.values() if e["type"] == "technology-service" and e.get("attrs", {}).get("used") is False)
    for i in designed_not_built + built_not_designed + unused:
        els[i]["drift"] = True
    rels = {(r["type"], r["source"], r["target"]) for r in gen["relations"]}
    for r in cur["relations"]:
        if isinstance(r, dict) and r.get("type") and r.get("source") and r.get("target"):
            rels.add((r["type"], idmap.get(r["source"], r["source"]), idmap.get(r["target"], r["target"])))
    stored = load(root)
    layers = {k: sorted((e for e in els.values() if e["layer"] == k), key=lambda e: (TYPE_ORDER[e["type"]], e["id"]))
              for k in LAYERS}
    n = lambda t: sum(e["type"] == t for e in els.values())  # noqa: E731
    return {"source": gen["source"], "layers": layers,
            "relations": [{"type": t, "source": s, "target": g} for t, s, g in sorted(rels)],
            "drift": {"designed_not_built": sorted(designed_not_built), "built_not_designed": built_not_designed,
                      "unused_bindings": unused, "intent_modelled": intent,
                      "model_file": stored is not None,
                      "model_stale": stored is not None and stored.get("generated") != gen},
            "counts": {"goals": n("goal"), "requirements": n("requirement"), "principles": n("principle"),
                       "components": n("application-component"), "interfaces": n("application-interface"),
                       "data": n("data-object"), "bindings": n("technology-service"),
                       "drift": len(designed_not_built) + len(built_not_designed) + len(unused)}}

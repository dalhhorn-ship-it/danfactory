"""Architecture tab: layered diagram, drift lists, relations table."""
import html

from . import model, svg

REL_CAP = 40
EMPTY = {
    "motivation": "No motivation yet: fills from docs/GOAL.md (Outcome), docs/specs/ (PRDs) and docs/decisions/ (ADRs).",
    "application": "No components yet: from source roots (src/, app/, worker/... or curated.roots in docs/architecture.json).",
    "technology": "No bindings yet: from wrangler.jsonc/toml (Cloudflare bindings).",
}
INTRO = ("No architecture yet. Motivation fills from docs/GOAL.md, docs/specs/ (PRDs) and docs/decisions/ (ADRs); "
         "Application from source roots (src/, app/, worker/... or `curated.roots` in docs/architecture.json); "
         "Technology from wrangler.jsonc/toml.")


def e(x):
    return html.escape(str(x), quote=True)


def collect(root, base):
    return model.view(root)


def line(d):
    c = d["counts"]
    return "%d goal · %d reqs · %d principles, %d components, %d bindings; drift %d" % (
        c["goals"], c["requirements"], c["principles"], c["components"], c["bindings"], c["drift"])


def _list(title, ids, names, empty):
    items = "".join('<li><span class="mono">%s</span> %s</li>' % (e(i), e(names.get(i, ""))) for i in ids[:15])
    more = '<li class="muted">+%d more</li>' % (len(ids) - 15) if len(ids) > 15 else ""
    return "<h3>%s</h3><ul class=\"plain\">%s</ul>" % (e(title), (items + more) or '<li class="muted">%s</li>' % e(empty))


def render(d):
    layers, dr, c = d["layers"], d["drift"], d["counts"]
    names = {x["id"]: x["name"] for els in layers.values() for x in els}
    total = sum(len(v) for v in layers.values())
    out = ['<div class="card"><h2>Architecture</h2>']
    out.append('<p class="muted small">%s</p>' % (
        e("Generated from the repo (source: %s) plus curated intent in docs/architecture.json. "
          "Dashed red outline = drift. Links drawn only between layers." % d["source"]) if total else e(INTRO)))
    out.append('<div class="scroll">%s</div>' % svg.render(layers, d["relations"], EMPTY))
    out.append("</div>")
    if dr["intent_modelled"]:
        built = _list("Built, not designed", dr["built_not_designed"], names, "none")
    else:
        built = "<h3>Built, not designed</h3><p class=\"muted\">No intent modelled yet: add curated components to docs/architecture.json to see drift.</p>"
    stale = ("Model file docs/architecture.json is missing: run <code>python3 scripts/archmodel.py --write</code>." if not dr["model_file"]
             else "Model file is stale: run <code>python3 scripts/archmodel.py --write</code>." if dr["model_stale"]
             else "Model file is up to date.")
    out.append('<div class="card"><h2>Drift (%d)</h2>%s%s%s<p class="muted small">%s</p></div>' % (
        c["drift"], _list("Designed, not built", dr["designed_not_built"], names, "none"), built,
        _list("Bindings never mentioned in source", dr["unused_bindings"], names, "none"), stale))
    rels = d["relations"]
    rows = "".join('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        e(r["type"]), e(names.get(r["source"], r["source"])), e(names.get(r["target"], r["target"]))) for r in rels[:REL_CAP])
    out.append('<div class="card"><h2>Relations (%d)</h2><div class="scroll"><table><thead><tr><th>Type</th><th>From</th><th>To</th></tr></thead>'
               '<tbody>%s</tbody></table></div>%s</div>' % (
                   len(rels), rows or '<tr><td colspan="3" class="muted">No relations yet.</td></tr>',
                   '<p class="muted small">Top %d of %d; full list in data.json.</p>' % (REL_CAP, len(rels)) if len(rels) > REL_CAP else ""))
    return '<div class="stack">%s</div>' % "".join(out)

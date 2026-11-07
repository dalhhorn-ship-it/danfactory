"""Deterministic layered SVG diagram (Motivation / Application / Technology). Classes only; colours live in the page CSS."""
import html

BOX_W, BOX_H, GAP, PER_ROW, CAP, LABEL_W, BAND_GAP, EDGE_CAP, NAME_MAX = 150, 44, 20, 6, 24, 96, 32, 80, 20
BANDS = (("motivation", "Motivation", "am-mot"), ("application", "Application", "am-app"), ("technology", "Technology", "am-tech"))
X0 = LABEL_W + GAP
WIDTH = X0 + PER_ROW * (BOX_W + GAP)


def _e(x):
    return html.escape(str(x), quote=True)


def _short(name):
    return name if len(name) <= NAME_MAX else name[:NAME_MAX - 1] + "…"


def render(layers, relations, empty=None):
    """layers: {layer: [element]}; relations: [{type, source, target}]; empty: {layer: message} for empty bands."""
    empty = empty or {}
    pos, bands, boxes, edges_svg, y = {}, [], [], [], 0
    for bi, (key, label, cls) in enumerate(BANDS):
        els = layers.get(key, [])
        shown = els[:CAP]
        cells = [(e["name"], e["type"], e["id"], e.get("drift"), "%s · %s" % (e["type"], e["name"])) for e in shown]
        if len(els) > CAP:
            cells.append(("+%d more" % (len(els) - CAP), "", "", False, "%d more elements not drawn" % (len(els) - CAP)))
        rows = max(1, -(-len(cells) // PER_ROW))
        h = rows * (BOX_H + GAP) + GAP
        bands.append('<g class="%s"><rect class="band" x="0" y="%d" width="%d" height="%d" rx="8"/>'
                     '<text class="band-l" x="12" y="%d">%s</text>' % (cls, y, WIDTH, h, y + 26, _e(label)))
        if not cells:
            bands.append('<text class="band-e" x="%d" y="%d">%s</text>' % (X0, y + h // 2 + 4, _e(empty.get(key, "No elements"))))
        for n, (name, typ, eid, drift, tip) in enumerate(cells):
            bx = X0 + (n % PER_ROW) * (BOX_W + GAP)
            by = y + GAP + (n // PER_ROW) * (BOX_H + GAP)
            if eid:
                pos[eid] = (bi, bx + BOX_W // 2, by, by + BOX_H)
            boxes.append('<g class="%s box%s"><title>%s</title><rect x="%d" y="%d" width="%d" height="%d" rx="6"/>'
                         '<text x="%d" y="%d">%s</text><text class="sub" x="%d" y="%d">%s</text></g>'
                         % (cls, " drift" if drift else "", _e(tip), bx, by, BOX_W, BOX_H, bx + BOX_W // 2, by + 19, _e(_short(name)),
                            bx + BOX_W // 2, by + 34, _e(typ)))
        bands.append("</g>")
        y += h + BAND_GAP
    seen = set()
    for r in relations:
        a, b = pos.get(r["source"]), pos.get(r["target"])
        if not a or not b or a[0] == b[0]:
            continue
        up, low = (a, b) if a[0] < b[0] else (b, a)
        k = (up[1], up[3], low[1], low[2])
        if k in seen or len(seen) >= EDGE_CAP:
            continue
        seen.add(k)
        edges_svg.append('<line x1="%d" y1="%d" x2="%d" y2="%d"/>' % (up[1], up[3], low[1], low[2]))
    height = y - BAND_GAP
    total = sum(len(layers.get(k, [])) for k, _, _ in BANDS)
    label = "Architecture diagram: %d elements in 3 layers, %d cross-layer links drawn" % (total, len(seen))
    return ('<svg class="arch" role="img" aria-label="%s" viewBox="0 0 %d %d" width="100%%" '
            'style="min-width:960px" xmlns="http://www.w3.org/2000/svg">%s<g class="edges">%s</g>%s</svg>'
            % (_e(label), WIDTH, height, "".join(bands), "".join(edges_svg), "".join(boxes)))

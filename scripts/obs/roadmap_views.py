"""Render the Roadmap sub-views (DASH-4) as HTML and inline SVG. Classes only; colours live in obs/theme.py.

CSS-only radio sub-tabs: Sequence (the existing view, passed in as markup) | 6-month | Gantt (proposed) | Releases.
All text is escaped; no script, no network. Charts live in a `.scroll` container so only the chart scrolls on phones.
"""
import datetime
import html

from . import roadmap_data as D

LABELS = (("sequence", "Sequence"), ("months", "6-month"), ("gantt", "Gantt (proposed)"), ("releases", "Releases"))


def e(x):
    return html.escape(str(x), quote=True)


def trunc(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def card(title, body, intro=""):
    return '<div class="card"><h2>%s</h2>%s%s</div>' % (e(title), '<p class="muted small">%s</p>' % intro if intro else "", body)


def empty(msg):
    return '<p class="rv-empty">%s</p>' % msg


# ---------------------------------------------------------------- 6-month

def months_view(m):
    COLW, HEAD, LINE = 176, 26, 17
    width = COLW * 6

    def x(d):
        i = max(0, min(5, (d.year - m["start"].year) * 12 + d.month - m["start"].month))
        nxt = D.add_months(m["cols"][i], 1)
        return i * COLW + COLW * (d - m["cols"][i]).days / (nxt - m["cols"][i]).days

    tl = max(1, len(m["targets_in"]))
    per = {}
    for it in m["done"]:
        per.setdefault((it["date"].year, it["date"].month), []).append(it)
    done_lines = max([min(len(v), 12) + (len(v) > 12) for v in per.values()] + [1])
    y_ms, y_done = HEAD + 18, HEAD + 18 + tl * LINE + 28
    height = y_done + 18 + done_lines * LINE + 30
    s = ['<svg class="tl" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="6-month timeline: milestone targets and done items by month">'
         % (width, height, width, height)]
    for i, c in enumerate(m["cols"]):
        s.append('<rect class="%s" x="%d" y="0" width="%d" height="%d"/>' % ("col a" if i % 2 else "col", i * COLW, COLW, height))
        s.append('<text class="mh" x="%d" y="17">%s</text>' % (i * COLW + 8, c.strftime("%b %Y")))
    s.append('<line class="ax" x1="0" x2="%d" y1="%d" y2="%d"/>' % (width, HEAD, HEAD))
    s.append('<text class="rl" x="8" y="%d">Milestone targets</text>' % (y_ms - 5))
    for n, (name, d) in enumerate(m["targets_in"]):
        cx, cy = x(d), y_ms + n * LINE + 7
        s.append('<g class="ms"><title>%s, target %s</title><path d="M%.1f %d l6 6 l-6 6 l-6 -6 z"/><text x="%.1f" y="%d">%s</text></g>'
                 % (e(name), d, cx, cy - 6, cx + 10, cy + 4, e(trunc(name, 26))))
    s.append('<text class="rl" x="8" y="%d">Done, at actual dates (git)</text>' % (y_done - 5))
    for (yy, mm), its in sorted(per.items()):
        i = (yy - m["start"].year) * 12 + mm - m["start"].month
        for n, it in enumerate(its[:12]):
            s.append('<g class="dn"><title>%s %s, done %s</title><circle cx="%d" cy="%d" r="3.5"/><text x="%d" y="%d">%s</text></g>'
                     % (e(it["id"]), e(it["title"]), it["date"], i * COLW + 12, y_done + n * LINE + 7, i * COLW + 22, y_done + n * LINE + 11,
                        e(trunc("%s %s" % (it["label"], it["short"]) if it["id"] else it["short"], 24))))
        if len(its) > 12:
            s.append('<text class="more" x="%d" y="%d">+%d more</text>' % (i * COLW + 22, y_done + 12 * LINE + 11, len(its) - 12))
    tx = x(m["today"])
    s.append('<g class="today"><line x1="%.1f" x2="%.1f" y1="%d" y2="%d"/><text x="%.1f" y="%d">today %s</text></g>'
             % (tx, tx, HEAD, height - 18, min(tx + 4, width - 110), height - 5, m["today"]))
    s.append("</svg>")
    notes = []
    if not m["any_target"]:
        notes.append(empty("No dates yet: add (target: YYYY-MM-DD) to a milestone heading in docs/BACKLOG.md."))
    elif not m["targets_in"]:
        notes.append(empty("No milestone target falls inside this window."))
    if m["targets_out"]:
        notes.append('<p class="muted small">Outside the window: %s.</p>' % e("; ".join("%s (%s)" % (n, d) for n, d in m["targets_out"])))
    if not m["done"]:
        notes.append(empty("No done items with a git date in this window."))
    if m["earlier"]:
        notes.append('<p class="muted small">%d done item(s) are older than the window.</p>' % m["earlier"])
    if m["undated"]:
        notes.append('<p class="muted small">Done, date unknown (no git history): %s.</p>' % e(", ".join(i["label"] for i in m["undated"])))
    uns = "".join('<li><span class="mono">%s</span> %s <span class="muted small">%s</span></li>'
                  % (e(i["id"] or "·"), e(i["short"]), e(" · ".join(p for p in (i["size"], i["state"] if i["state"] != "todo" else "") if p)))
                  for i in m["unscheduled"][:30])
    more = len(m["unscheduled"]) - 30
    un = ('<h3>Unscheduled (open items have no date; none is guessed into a month)</h3><ul class="plain rv-list">%s</ul>%s'
          % (uns, '<p class="muted small">+%d more</p>' % more if more > 0 else "")) if uns else ""
    intro = ("Rolling window: one month back to five months ahead (%s to %s). Milestones appear at their (target: date); done items at the "
             "date git shows them ticked." % (m["start"], m["end"] - datetime.timedelta(days=1)))
    return card("Roadmap: 6-month timeline", "".join(notes) + '<div class="scroll rv-chart">%s</div>' % "".join(s) + un, intro)


# ---------------------------------------------------------------- Gantt

def gantt_view(g):
    LABEL, PXD, ROW, HEAD = 190, 9, 24, 28
    days = (g["hi"] - g["lo"]).days
    width = LABEL + days * PXD + 190

    def x(d):
        return LABEL + (d - g["lo"]).days * PXD
    rows = g["done"] + g["open"]
    sep = HEAD + len(g["done"]) * ROW
    height = HEAD + len(rows) * ROW + (22 if g["open"] and g["done"] else 0) + 30
    open_ids, y = {id(r) for r in g["open"]}, HEAD
    for n, r in enumerate(rows):
        if n == len(g["done"]) and g["done"]:
            y += 22
        r["_y"] = y
        y += ROW
    s = ['<svg class="gantt" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="Proposed Gantt chart: actual bars for done items, hatched estimated bars for open items">'
         % (width, height, width, height)]
    s.append('<defs><pattern id="gt-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<rect class="hb" width="6" height="6"/><line class="hl" x1="0" y1="0" x2="0" y2="6"/></pattern></defs>')
    d = g["lo"]
    while d < g["hi"]:
        if d.weekday() == 0:
            s.append('<line class="grid" x1="%d" x2="%d" y1="%d" y2="%d"/><text class="tk" x="%d" y="16">%s</text>'
                     % (x(d), x(d), HEAD - 6, height - 24, x(d) + 3, d.strftime("%m-%d")))
        d += datetime.timedelta(days=1)
    s.append('<line class="ax" x1="0" x2="%d" y1="%d" y2="%d"/>' % (width, HEAD - 6, HEAD - 6))
    if g["done"] and g["open"]:
        s.append('<text class="rl" x="8" y="%d">Open, estimated</text>' % (sep + 15))
    for r in rows:
        yy = r["_y"]
        est = id(r) in open_ids
        lab = ("%s " % r["id"] if r["id"] else "") + r["short"]
        s.append('<text class="gl%s" x="8" y="%d"><title>%s</title>%s</text>'
                 % (" bl" if r["state"] == "blocked" else "", yy + 15, e(r["title"]), e(trunc(lab, 29))))
        x1, x2 = x(r["start"]), x(r["end"])
        cut = x2 > x(g["hi"])
        x2 = min(x2, x(g["hi"]))
        w = max(4, x2 - x1)
        if not est:
            s.append('<rect class="bar done" x="%d" y="%d" width="%d" height="14"><title>%s %s: %s to %s (actual, git)</title></rect>'
                     % (x1, yy + 4, w, e(r["id"]), e(r["title"]), r["start"], r["end"]))
            s.append('<text class="bl2" x="%d" y="%d">done %s</text>' % (x1 + w + 6, yy + 15, r["end"]))
        else:
            cls = "bar est blocked" if r["state"] == "blocked" else "bar est"
            note = "%sd est." % ("%g" % r["days"]) + (", size missing" if r["size_missing"] else "") + (", blocked" if r["state"] == "blocked" else "") \
                + (", in progress" if r["state"] == "doing" else "")
            s.append('<rect class="%s" x="%d" y="%d" width="%d" height="14" fill="url(#gt-hatch)"><title>%s %s: proposed %s to %s, estimated</title></rect>'
                     % (cls, x1, yy + 4, w, e(r["id"]), e(r["title"]), r["start"], r["end"]))
            s.append('<text class="bl2" x="%d" y="%d">%s</text>' % (x1 + w + 6, yy + 15, e(("%s · " % r["size"] if r["size"] else "") + note + (" · continues beyond" if cut else ""))))
    ids = {r["id"]: r for r in rows if r["id"]}
    for r in g["open"]:
        p = ids.get(r["after"])
        if p:
            x1, x2 = x(p["end"]), x(r["start"])
            y1, y2 = p["_y"] + 11, r["_y"] + 11
            s.append('<path class="dep" d="M%d %d H%d V%d H%d"><title>%s after %s</title></path>' % (x1, y1, max(x1, x2) - 4 if x2 > x1 else x1 + 4, y2, x2, e(r["id"]), e(p["id"])))
    tx = x(g["today"])
    s.append('<g class="today"><line x1="%d" x2="%d" y1="%d" y2="%d"/><text x="%d" y="%d">today %s</text></g>' % (tx, tx, HEAD - 6, height - 22, tx + 4, height - 8, g["today"]))
    s.append("</svg>")
    sd = g["size_days"]
    assume = ('<p class="rv-assume"><b>Proposed, not a commitment.</b> Hatched bars are <b>estimated</b> (labelled "est."); solid bars are fact '
              'from git. Assumptions: S=%s, M=%s, L=%s working days; WIP=%d (at most %d estimated item%s in parallel); weekends skipped; '
              'items with no size use the M value and are marked "size missing"; blocked items are placed after unblocked ones; start is today. '
              'Order follows docs/BACKLOG.md. Dependencies are drawn only where an item declares (after: ID). Change the numbers under '
              '<code>dashboard.size_days</code> and <code>dashboard.wip</code> in factory.json.</p>'
              % ("%g" % sd["S"], "%g" % sd["M"], "%g" % sd["L"], g["wip"], g["wip"], "" if g["wip"] == 1 else "s"))
    notes = []
    if g["hidden_done"]:
        notes.append('<p class="muted small">%d older done item(s) not drawn.</p>' % g["hidden_done"])
    if g["undated"]:
        notes.append('<p class="muted small">Done, date unknown (no git history): <span class="mono">%s</span> <span aria-hidden="true">&#9679;</span> unknown date.</p>'
                     % e(", ".join(i["label"] for i in g["undated"])))
    if not g["open"]:
        notes.append(empty("Nothing open: no estimated bars. Add items to docs/BACKLOG.md."))
    if g["beyond"]:
        notes.append('<p class="muted small">The estimated plan continues beyond the 12-month chart limit.</p>')
    return card("Roadmap: proposed Gantt", assume + "".join(notes) + '<div class="scroll rv-chart">%s</div>' % "".join(s))


# ---------------------------------------------------------------- releases

def releases_view(r, history_ok):
    parts = []
    if not r["any"]:
        parts.append(empty("No releases yet. Define one by creating a git tag vX.Y.Z (shipped) or by adding (release: vX.Y) to a backlog item "
                           "or milestone heading in docs/BACKLOG.md (planned)."))

    def li(i):
        st = '<span class="state %s">%s</span>' % (e(i["state"]), e(i["state"])) if i["state"] != "done" else '<span class="state done">done</span>'
        how = ' <span class="muted small">(by done date)</span>' if i.get("how") == "by date" else ""
        return '<li><span class="mono">%s</span> %s %s%s</li>' % (e(i["id"] or "·"), e(i["short"]), st, how)
    for g in r["groups"]:
        if g["shipped"]:
            status = '<span class="rv-st shipped">shipped %s</span> <span class="muted small">%s</span>' % (e(g["date"]), e(", ".join(g["tags"])))
        else:
            status = '<span class="rv-st planned">planned</span> <span class="muted small">no git tag yet</span>'
        parts.append('<section class="rv-rel"><h3>%s %s <span class="muted small">%d item%s</span></h3><ul class="plain rv-list">%s</ul></section>'
                     % (e(g["name"]), status, len(g["items"]), "" if len(g["items"]) == 1 else "s",
                        "".join(li(i) for i in g["items"]) or '<li class="muted small">No items marked for this release.</li>'))
    un = r["unassigned"]
    parts.append('<section class="rv-rel"><h3>Unassigned <span class="muted small">%d done item%s with no release</span></h3>'
                 '<ul class="plain rv-list">%s</ul></section>'
                 % (len(un), "" if len(un) == 1 else "s", "".join(li(i) for i in un) or '<li class="muted small">None.</li>'))
    return card("Roadmap: releases", "".join(parts),
                "A release is a git tag vX.Y.Z (shipped, dated by the tag) or an optional (release: vX.Y) marker on an item or milestone "
                "(planned). Done items without a marker join the first tag created on or after their done date; otherwise they stay unassigned.")


# ---------------------------------------------------------------- switcher

def render(data, sequence_html):
    sel = data["settings"]["view"]
    panels = {"sequence": sequence_html, "months": months_view(data["months"]), "gantt": gantt_view(data["gantt"]),
              "releases": releases_view(data["releases"], data["history"])}
    inputs = "".join('<input type="radio" name="rmview" id="rv-%s" class="tab-input"%s>' % (k, " checked" if k == sel else "") for k, _l in LABELS)
    nav = "".join('<label for="rv-%s">%s</label>' % (k, e(lab)) for k, lab in LABELS)
    body = "".join('<div class="rv rv-%s">%s</div>' % (k, panels[k]) for k, _l in LABELS)
    return '<div class="rmv">%s<nav class="subtabs" aria-label="Roadmap views">%s</nav>%s</div>' % (inputs, nav, body)

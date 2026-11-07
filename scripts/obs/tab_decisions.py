"""Decisions tab: ADR timeline, status, supersedes chains and affected components."""
import html
import re

from . import sources as S

EMPTY = "No ADRs yet: the first one appears when a decision is recorded (docs/decisions/NNNN-title.md)."
DATE = re.compile(r"Date:\s*(\d{4}-\d{2}-\d{2})")
SUPERSEDES = re.compile(r"(?i)\bsupersedes:?\s*((?:ADR\s*)?\d{4}(?:\s*[,/&]\s*(?:ADR\s*)?\d{4})*)")
SUPERSEDED_BY = re.compile(r"(?i)superseded by\s*(?:ADR\s*)?(\d{4})")
NUM = re.compile(r"\d{4}")
COMP_CAP = 6


def e(x):
    return html.escape(str(x), quote=True)


def parse(adr):
    head = "\n".join(adr["text"].splitlines()[:8])  # header block only
    d, by, sup = DATE.search(head), SUPERSEDED_BY.search(head), SUPERSEDES.search(head)
    return {"num": adr["num"], "title": adr["title"], "status": adr["status"] or "unknown",
            "date": d.group(1) if d else "", "superseded_by": by.group(1) if by else "",
            "supersedes": sorted(set(NUM.findall(sup.group(1)))) if sup else []}


def chains(rows):
    """Supersedes chains, oldest -> newest, for every ADR that is part of one."""
    nums = {r["num"] for r in rows}
    nxt = {}  # old -> new
    for r in rows:
        for old in r["supersedes"]:
            if old in nums:
                nxt[old] = r["num"]
        if r["superseded_by"] in nums:
            nxt[r["num"]] = r["superseded_by"]
    out = []
    for start in sorted(set(nxt) - set(nxt.values())):
        c, seen = [start], {start}
        while c[-1] in nxt and nxt[c[-1]] not in seen:
            c.append(nxt[c[-1]])
            seen.add(c[-1])
        out.append(c)
    return out


def collect(root, base):
    rows = [parse(a) for a in S.adrs(root)]
    rels = (base.get("architecture") or {}).get("relations", [])
    for r in rows:
        comps = sorted({x["target"][4:] for x in rels if x["type"] == "influence"
                        and x["source"] == "adr:" + r["num"] and x["target"].startswith("app:")})
        r["components"], r["components_total"] = comps[:COMP_CAP], len(comps)
    rows.sort(key=lambda r: r["num"])
    ch = chains(rows)
    return {"adrs": rows, "total": len(rows), "chains": ch,
            "superseded": sum(r["superseded_by"] != "" or r["status"] == "superseded" for r in rows)}


def line(d):
    if not d["total"]:
        return "no ADRs yet"
    live = sum(r["status"] == "accepted" for r in d["adrs"])
    return "%d ADRs (%d accepted, %d superseded), %d supersedes chains" % (d["total"], live, d["superseded"], len(d["chains"]))


def render(d):
    if not d["total"]:
        return '<div class="card"><h2>Decisions</h2><p class="muted">%s</p></div>' % e(EMPTY)
    rows = []
    for r in d["adrs"]:
        cls = "low" if r["status"] == "accepted" else "medium"
        comps = ", ".join(e(c) for c in r["components"]) or '<span class="muted">–</span>'
        if r["components_total"] > len(r["components"]):
            comps += " +%d" % (r["components_total"] - len(r["components"]))
        rel = []
        if r["supersedes"]:
            rel.append("supersedes " + ", ".join(r["supersedes"]))
        if r["superseded_by"]:
            rel.append("superseded by " + r["superseded_by"])
        rows.append('<tr><td class="mono nowrap">%s</td><td>%s</td><td><span class="imp %s">%s</span></td><td class="nowrap">%s</td>'
                    '<td>%s</td><td>%s</td></tr>' % (e(r["num"]), e(r["title"]), cls, e(r["status"]), e(r["date"] or "–"),
                                                   e("; ".join(rel)) or '<span class="muted">–</span>', comps))
    if d["chains"]:
        cs = "".join('<li class="mono">%s</li>' % e(" → ".join(c)) for c in d["chains"])
        chain = '<h3>Supersedes chains</h3><ul class="plain">%s</ul>' % cs
    else:
        chain = '<h3>Supersedes chains</h3><p class="muted">No ADR supersedes another yet (write <code>Supersedes: NNNN</code> in the header).</p>'
    return ('<div class="stack"><div class="card"><h2>Decisions (%d)</h2><div class="scroll"><table><thead><tr><th>ADR</th><th>Title</th>'
            '<th>Status</th><th>Date</th><th>Chain</th><th>Affected components</th></tr></thead><tbody>%s</tbody></table></div></div>'
            '<div class="card">%s</div></div>' % (d["total"], "".join(rows), chain))

"""Autonomy tab: Issues block (ADR 0008) from the issues/ ledger and its git history. C7 extends it later.
Empty state when issues/ has no ledger yet; nothing here ever fails the dashboard build."""
import html
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import issues as L  # noqa: E402

EMPTY = L.EMPTY
DAYS = 14
CAP = 25


def e(x):
    return html.escape(str(x), quote=True)


def collect(root, base):
    try:
        st = L.status(root)
    except Exception as ex:  # a broken ledger must not break the dashboard
        st = dict(L.status("/nonexistent"), error=str(ex)[:200])
    days = sorted(st["per_day"])[-DAYS:]
    st["trend"] = [{"day": d, "opened": st["per_day"][d]["opened"], "fixed": st["per_day"][d]["fixed"]} for d in days]
    st["issues"] = sorted(st["issues"], key=lambda i: (-(i["age"] or 0), i["id"]))[:CAP]
    return {"issues": st}


def line(d):
    st = d["issues"]
    if not st["exists"]:
        return "no issue ledger yet"
    old = st["oldest_open"]
    return "issues: %d open, %d fixed%s" % (st["open"], st["fixed"], ", oldest %s open %dd" % (old["id"], old["days"]) if old else "")


def _bars(trend):
    top = max([max(t["opened"], t["fixed"]) for t in trend] + [1])
    rects = []
    for i, t in enumerate(trend):
        for j, k in enumerate(("opened", "fixed")):
            h = max(1.5, 36.0 * t[k] / top) if t[k] else 1.5
            rects.append('<rect x="%d" y="%.1f" width="6" height="%.1f" rx="1"%s><title>%s %s: %d</title></rect>'
                         % (i * 16 + j * 7 + 2, 40 - h, h, ' class="zero"' if (k == "fixed" or not t[k]) else "", e(t["day"]), k, t[k]))
    return ('<figure class="bars"><figcaption>Opened (dark) and fixed (light) per day, from git history of issues/</figcaption>'
            '<svg viewBox="0 0 %d 40" preserveAspectRatio="none" role="img" aria-label="Issues opened and fixed per day">%s</svg>'
            '<div class="axis"><span>%s</span><span>%s</span></div></figure>'
            % (len(trend) * 16, "".join(rects), e(trend[0]["day"]), e(trend[-1]["day"])))


def render(d):
    st = d["issues"]
    if not st["exists"]:
        return '<div class="card"><h2>Issues</h2><p class="muted">%s</p></div>' % e(EMPTY)
    old = st["oldest_open"]
    facts = [("Open", st["open"]), ("Fixed", st["fixed"]),
             ("Oldest open issue", "%s, %d day(s)" % (old["id"], old["days"]) if old else "none open")]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    prd = "".join('<tr><td class="mono">%s</td><td>%d</td></tr>' % (e(k), v) for k, v in st["by_prd"].items()) \
        or '<tr><td class="muted">No open issues.</td></tr>'
    trend = _bars(st["trend"]) if st.get("trend") else '<p class="muted small">No git history of issues/ yet: commit the ledger to see the daily trend.</p>'
    rows = "".join('<tr><td class="mono nowrap">%s</td><td>%s</td><td class="mono">%s</td><td>%d</td><td>%s</td></tr>' % (
        e(i["id"]), e(i["title"][:90]), e(i["prd"]), i["tests"], e("%dd" % i["age"]) if i["age"] is not None else "–") for i in st["issues"]) \
        or '<tr><td colspan="5" class="muted">No open issues.</td></tr>'
    cap = '<p class="muted small">Oldest %d of %d open issues; full list in data.json.</p>' % (len(st["issues"]), st["open"]) if st["open"] > len(st["issues"]) else ""
    return ('<div class="stack"><div class="card"><h2>Issues</h2><table><tbody>%s</tbody></table>%s</div>'
            '<div class="card"><h2>Open by PRD</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>Open issues</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Title</th><th>PRD</th><th>Tests</th><th>Age</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div></div>' % (kv, trend, prd, rows, cap))

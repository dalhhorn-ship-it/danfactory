"""Traceability tab: goal -> PRD -> item -> commits -> components -> tests -> version, with broken links flagged."""
import html

from . import trace

EMPTY = ("No PRDs yet: a chain appears when product-manager writes one in docs/specs/ and backlog items reference it. "
         "Link commits with `Refs: <ITEM-ID>`.")


def e(x):
    return html.escape(str(x), quote=True)


def collect(root, base):
    return trace.build(root, base, base.get("architecture"))


def line(d):
    pct = "%d%% commits linked" % d["linked_commit_pct"] if d["linked_commit_pct"] is not None else "no commits"
    return "%d PRDs → %d items, %s, %d broken links" % (d["prds"], d["items"], pct, d["broken_total"])


def _names(paths, n=3, base=False):
    shown = [p.rsplit("/", 1)[-1] if base else p for p in paths[:n]]
    return e(", ".join(shown)) + (" +%d" % (len(paths) - n) if len(paths) > n else "") if paths else '<span class="muted">–</span>'


def _flags(items):
    return "".join('<span class="imp high">%s</span> ' % e(b) for b in items)


def render(d):
    if not d["chains"]:
        return '<div class="card"><h2>Traceability</h2><p class="muted">%s</p></div>' % e(EMPTY)
    rows = []
    for ch in d["chains"]:
        p = ch["prd"]
        rows.append('<tr class="grp"><td colspan="8"><b>%s</b> <span class="mono muted">%s</span> '
                    '<span class="imp %s">%s</span> %s</td></tr>' % (
                        e(p["title"]), e(p["slug"]), "low" if p["status"] == "approved" else "medium",
                        e(p["status"] + (" · " + p["approved"] if p["approved"] else "")), _flags(ch["broken"])))
        for it in ch["items"]:
            commits = ", ".join('<span class="mono" title="%s">%s</span>' % (e(c["subject"]), e(c["sha"])) for c in it["commits"][:3])
            more = it["commits_total"] - min(3, len(it["commits"]))
            rows.append('<tr><td class="mono nowrap">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class="mono">%s</td><td>%s</td></tr>' % (
                e(it["id"] or "–"), e(it["title"][:90]), e(it["state"]),
                (commits + (" +%d" % more if more > 0 else "")) if commits else '<span class="muted">–</span>',
                _names(it["components"], 3, True), _names(it["tests"], 2, True), e(it["version"] or "–"), _flags(it["broken"])))
    pct = "%d%%" % d["linked_commit_pct"] if d["linked_commit_pct"] is not None else "n/a"
    goal = "Goal set" if d["goal"] else "Goal not set (docs/GOAL.md Outcome is still a placeholder)"
    cap = '<p class="muted small">Top %d of %d PRDs; full chains in data.json.</p>' % (len(d["chains"]), d["chains_total"]) \
        if d["chains_total"] > len(d["chains"]) else ""
    return ('<div class="card"><h2>Traceability</h2><p class="muted small">%s · %s of the last %d commits carry a Refs key '
            '(%d unlinked) · %d broken links</p><div class="scroll"><table><thead><tr><th>ID</th><th>Item</th><th>State</th>'
            '<th>Commits</th><th>Components</th><th>Tests</th><th>Version</th><th>Flags</th></tr></thead><tbody>%s</tbody></table></div>%s</div>'
            % (e(goal), pct, d["commits"], d["unlinked_commits"], d["broken_total"], "".join(rows), cap))

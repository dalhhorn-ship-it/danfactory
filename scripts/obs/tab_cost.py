"""Cost tab: weighted tokens from metrics/tokens.jsonl, attributed to backlog items only when a record says so.
Spike S3 (2026-11-07): session rows carry ts and session_id only (no sha, no item), and the session_id differs from the
`Claude-Session` commit trailer; matching by timestamp window would be a guess. So a row is attributed only if it has an
explicit `item` field, or a `sha` of a commit with `Refs: <ITEM-ID>`. Everything else is "unattributed" and counted, never assigned."""
import html
import json

from . import sources as S
from . import tab_flow

CAP = 15
EMPTY = "No token records yet: metrics/tokens.jsonl is written at session end by the record_tokens hook, one row per session."


def e(x):
    return html.escape(str(x), quote=True)


def weighted(r):
    """Cost-weighted tokens (same weights as scripts/metrics.py wt)."""
    if isinstance(r.get("weighted_tokens"), (int, float)):
        return r["weighted_tokens"]
    g = lambda k: r.get(k) if isinstance(r.get(k), (int, float)) else 0  # noqa: E731
    return round(g("input_tokens") + 5 * g("output_tokens") + 1.25 * g("cache_creation_input_tokens") + 0.1 * g("cache_read_input_tokens"))


def rows(root):
    out = []
    for ln in S.read(root, "metrics/tokens.jsonl").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("kind", "session") == "session":
            out.append(r)
    return out


def attribute(r, by_sha):
    """Item ID for a token row, or '' (unattributed). Never guesses from time or session."""
    if r.get("item"):
        return str(r["item"])
    return by_sha.get(str(r.get("sha") or ""), "")


def collect(root, base):
    by_sha = {}
    for c in tab_flow.commits(root):
        if c["refs"]:
            by_sha[c["sha"]] = c["refs"][0]
    rs = rows(root)
    total = sum(weighted(r) for r in rs)
    per, un_tokens, un_n = {}, 0, 0
    for r in rs:
        item = attribute(r, by_sha)
        if item:
            p = per.setdefault(item, {"id": item, "sessions": 0, "tokens": 0})
            p["sessions"] += 1
            p["tokens"] += weighted(r)
        else:
            un_n += 1
            un_tokens += weighted(r)
    items = sorted(per.values(), key=lambda p: (-p["tokens"], p["id"]))
    return {"sessions": len(rs), "total_tokens": total,
            "unattributed": {"sessions": un_n, "tokens": un_tokens, "share_pct": round(100.0 * un_tokens / total) if total else None},
            "items": items[:CAP], "items_total": len(items),
            "avg_tokens": round(total / len(rs)) if rs else None}


def _n(v):
    return "–" if v is None else "{:,}".format(v)


def line(d):
    if not d["sessions"]:
        return "no token records yet"
    u = d["unattributed"]
    return "%s weighted tokens over %d sessions; %s%% unattributed, %d items attributed" % (
        _n(d["total_tokens"]), d["sessions"], "–" if u["share_pct"] is None else u["share_pct"], d["items_total"])


def render(d):
    if not d["sessions"]:
        return '<div class="card"><h2>Cost</h2><p class="muted">%s</p></div>' % e(EMPTY)
    u = d["unattributed"]
    facts = [("Sessions recorded", _n(d["sessions"])), ("Weighted tokens (total)", _n(d["total_tokens"])),
             ("Weighted tokens per session (average)", _n(d["avg_tokens"])),
             ("Unattributed", "%s sessions, %s tokens (%s%%)" % (u["sessions"], _n(u["tokens"]), "–" if u["share_pct"] is None else u["share_pct"]))]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    irows = "".join('<tr><td class="mono nowrap">%s</td><td>%d</td><td>%s</td></tr>' % (e(i["id"]), i["sessions"], e(_n(i["tokens"])))
                    for i in d["items"])
    cap = '<p class="muted small">Top %d of %d items; full list in data.json.</p>' % (len(d["items"]), d["items_total"]) \
        if d["items_total"] > len(d["items"]) else ""
    why = ('<p class="muted small">A session is attributed to an item only when its record names the item (or a commit with '
           '<code>Refs:</code>). Session records carry no item or commit today, so they stay unattributed rather than guessed.</p>')
    return ('<div class="stack"><div class="card"><h2>Cost</h2><table><tbody>%s</tbody></table>%s</div>'
            '<div class="card"><h2>Attributed to items</h2><div class="scroll"><table><thead><tr><th>Item</th><th>Sessions</th><th>Weighted tokens</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div></div>'
            % (kv, why, irows or '<tr><td colspan="3" class="muted">None: all %s sessions are unattributed.</td></tr>' % e(u["sessions"]), cap))

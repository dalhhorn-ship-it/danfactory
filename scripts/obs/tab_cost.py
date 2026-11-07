"""Cost tab: weighted tokens from metrics/tokens.jsonl, attributed to backlog items only when a record says so.
A row is attributed only if it has an explicit `item`, a `sha` of a commit with `Refs: <ITEM-ID>`, or a `shas` list
(commits made during the session, written by the SessionEnd hook) whose commits reference exactly one distinct item.
Sessions whose commits reference several items are "mixed": counted, never split or guessed. Everything else is "unattributed"."""
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


def _lookup(by_sha, sha):
    """Item for a commit sha (full or abbreviated: git's %h and %H both occur), or ''."""
    sha = str(sha or "")
    if not sha:
        return ""
    if sha in by_sha:
        return by_sha[sha]
    return next((v for k, v in by_sha.items() if sha.startswith(k)), "")


def attribute(r, by_sha):
    """Item ID for a token row, or '' (unattributed). Never guesses; several distinct items in `shas` = mixed = ''."""
    if r.get("item"):
        return str(r["item"])
    if r.get("sha"):
        return _lookup(by_sha, r["sha"])
    items = {_lookup(by_sha, s) for s in (r.get("shas") or []) if isinstance(s, str)} - {""}
    return next(iter(items)) if len(items) == 1 else ""


def is_mixed(r, by_sha):
    if r.get("item") or r.get("sha"):
        return False
    return len({_lookup(by_sha, s) for s in (r.get("shas") or []) if isinstance(s, str)} - {""}) > 1


def collect(root, base):
    by_sha = {}
    for c in tab_flow.commits(root):
        if c["refs"]:
            by_sha[c["sha"]] = c["refs"][0]
    rs = rows(root)
    total = sum(weighted(r) for r in rs)
    per, un_tokens, un_n, mixed = {}, 0, 0, 0
    for r in rs:
        item = attribute(r, by_sha)
        if item:
            p = per.setdefault(item, {"id": item, "sessions": 0, "tokens": 0})
            p["sessions"] += 1
            p["tokens"] += weighted(r)
        else:
            un_n += 1
            mixed += is_mixed(r, by_sha)
            un_tokens += weighted(r)
    items = sorted(per.values(), key=lambda p: (-p["tokens"], p["id"]))
    return {"sessions": len(rs), "total_tokens": total,
            "unattributed": {"sessions": un_n, "mixed": mixed, "tokens": un_tokens, "share_pct": round(100.0 * un_tokens / total) if total else None},
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
             ("Unattributed", "%s sessions, %s tokens (%s%%)" % (u["sessions"], _n(u["tokens"]), "–" if u["share_pct"] is None else u["share_pct"])),
             ("Mixed sessions (commits for several items, not split)", _n(u["mixed"]))]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    irows = "".join('<tr><td class="mono nowrap">%s</td><td>%d</td><td>%s</td></tr>' % (e(i["id"]), i["sessions"], e(_n(i["tokens"])))
                    for i in d["items"])
    cap = '<p class="muted small">Top %d of %d items; full list in data.json.</p>' % (len(d["items"]), d["items_total"]) \
        if d["items_total"] > len(d["items"]) else ""
    why = ('<p class="muted small">A session is attributed to an item only when its record names the item, or when every commit made during it '
           'carries the same <code>Refs:</code> item. Sessions without commits, or with commits for several items (mixed), stay unattributed rather than guessed.</p>')
    return ('<div class="stack"><div class="card"><h2>Cost</h2><table><tbody>%s</tbody></table>%s</div>'
            '<div class="card"><h2>Attributed to items</h2><div class="scroll"><table><thead><tr><th>Item</th><th>Sessions</th><th>Weighted tokens</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div></div>'
            % (kv, why, irows or '<tr><td colspan="3" class="muted">None: all %s sessions are unattributed.</td></tr>' % e(u["sessions"]), cap))

"""Missions tab: the latest mission, its verdict and the morning report (ADR 0012). Empty state when there are no missions.
Reads docs/missions/<slug>.md through .claude/hooks/_mission.py; if that module is missing or a file is malformed the tab
shows the empty state, it never fails the dashboard build."""
import html
import json
import os
import sys

from . import sources as S

EMPTY = "No missions yet: a mission is started with `python3 scripts/mission.py start` after the user's go (docs/policies/mission.md)."
HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".claude", "hooks")


def e(x):
    return html.escape(str(x), quote=True)


def _mod():
    if HOOKS not in sys.path:
        sys.path.insert(0, HOOKS)
    try:
        import _mission
        return _mission
    except Exception:  # noqa: BLE001 - the dashboard must build without it
        return None


def _slugs(root):
    d = os.path.join(root, "docs", "missions")
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return sorted(n[:-3] for n in names if n.endswith(".md") and not n.startswith("_") and not n.endswith("-report.md"))


def _verdict(root, slug):
    first = ""
    for ln in S.read(root, "docs/missions/%s-report.md" % slug).splitlines():
        if ln.startswith("Verdict:"):
            first = ln[len("Verdict:"):].strip().rstrip(".")
            break
    return first


def _link(root, rel, branch):
    try:
        repo = (json.loads(S.read(root, "factory.json") or "{}").get("dashboard") or {}).get("github_repo") or ""
    except ValueError:
        repo = ""
    return "https://github.com/%s/blob/%s/%s" % (repo, branch or "main", rel) if repo else ""


def collect(root, base=None):
    mod, rows = _mod(), []
    for slug in _slugs(root) if mod else []:
        try:
            m = mod.load(root, slug)
        except Exception:  # noqa: BLE001
            m = None
        if not m:
            continue
        rel = "docs/missions/%s-report.md" % slug
        has = os.path.isfile(os.path.join(root, rel))
        rows.append({"slug": slug, "title": m.get("title") or slug, "status": m.get("status") or "?", "started": m["started_at"],
                     "milestone": m.get("milestone") or "", "verdict": _verdict(root, slug) if has else "",
                     "report": rel if has else "", "link": _link(root, rel, m.get("branch")) if has else ""})
    rows.sort(key=lambda r: r["started"])
    return {"missions": rows, "latest": rows[-1] if rows else None}


def line(data):
    """One line for the latest mission (used by status output), or ''."""
    r = (data or {}).get("latest")
    if not r:
        return ""
    return "mission %s: %s%s" % (r["slug"], r["verdict"] or r["status"], (" (report: %s)" % r["report"]) if r["report"] else "")


def render(data):
    rows = (data or {}).get("missions") or []
    if not rows:
        return '<div class="card"><h2>Missions</h2><p class="muted">%s</p></div>' % e(EMPTY)
    last = rows[-1]
    if last["report"]:
        rep = ('<a href="%s">%s</a>' % (e(last["link"]), e(last["report"]))) if last["link"] else '<span class="mono">%s</span>' % e(last["report"])
    else:
        rep = '<span class="muted">no report yet (written when the mission ends)</span>'
    facts = [("Latest mission", '<span class="mono">%s</span>: %s' % (e(last["slug"]), e(last["title"]))),
             ("Status", e(last["status"])), ("Verdict", e(last["verdict"] or "pending")), ("Report", rep)]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), v) for k, v in facts)
    body = "".join('<tr><td class="mono">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        e(r["slug"]), e(r["status"]), e(r["milestone"]), e(r["verdict"] or "–")) for r in reversed(rows))
    return ('<div class="card"><h2>Missions</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>All missions</h2><div class="scroll"><table><thead><tr><th>Mission</th><th>Status</th>'
            '<th>Milestone</th><th>Verdict</th></tr></thead><tbody>%s</tbody></table></div></div>' % (kv, body))

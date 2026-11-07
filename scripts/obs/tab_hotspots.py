"""Hotspots tab: source files that change often and are large (churn x lines), from git history of the last 500 commits."""
import html
from collections import Counter

from . import sources as S

CAP = 10
MIN_CHURN = 2
EXCLUDE = ("docs/", "metrics/", "dashboard/", ".claude/", ".factory/")
EMPTY = "No hotspots yet: files appear here once a source file has been changed in at least %d commits." % MIN_CHURN


def e(x):
    return html.escape(str(x), quote=True)


def collect(root, base):
    present = set(S.project_files(root))
    tests = [p for p in present if S.is_test(p)]
    churn = Counter()
    for c in S.git_log(root):
        for f in set(c["files"]):
            churn[f] += 1
    rows = []
    for f, n in churn.items():
        if f not in present or not f.endswith(S.SRC_EXT) or S.is_test(f) or f.startswith(EXCLUDE) or n < MIN_CHURN:
            continue
        lines = len(S.read(root, f).splitlines())
        stem = f.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        rows.append({"path": f, "commits": n, "lines": lines, "score": n * lines,
                     "tested": len(stem) > 2 and any(stem in t.lower() for t in tests)})
    rows.sort(key=lambda r: (-r["score"], r["path"]))
    return {"files": rows[:CAP], "total": len(rows), "untested": sum(not r["tested"] for r in rows[:CAP])}


def line(d):
    if not d["total"]:
        return "no hotspots yet"
    top = d["files"][0]
    return "%d hotspots, top %s (%d commits, %d lines); %d of top %d without a test by name" % (
        d["total"], top["path"], top["commits"], top["lines"], d["untested"], len(d["files"]))


def render(d):
    if not d["total"]:
        return '<div class="card"><h2>Hotspots</h2><p class="muted">%s</p></div>' % e(EMPTY)
    rows = "".join('<tr><td class="mono">%s</td><td>%d</td><td>%d</td><td>%d</td><td><span class="imp %s">%s</span></td></tr>' % (
        e(r["path"]), r["commits"], r["lines"], r["score"], "low" if r["tested"] else "medium", "test by name" if r["tested"] else "no test by name")
        for r in d["files"])
    cap = '<p class="muted small">Top %d of %d files; full list in data.json.</p>' % (len(d["files"]), d["total"]) if d["total"] > len(d["files"]) else ""
    return ('<div class="card"><h2>Hotspots (churn × size)</h2><div class="scroll"><table><thead><tr><th>File</th><th>Commits</th><th>Lines</th><th>Score</th><th>Tests</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div>' % (rows, cap))

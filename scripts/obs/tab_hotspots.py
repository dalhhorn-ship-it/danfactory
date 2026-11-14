"""Hotspots tab: source files that change often and are large (churn x lines), from git history of the last N commits (factory.json dashboard.hotspot_commits, default 500)."""
import html
from collections import Counter

from . import size as Z
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
    for c in S.git_log(root, S.hotspot_window(root)):
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
    return {"files": rows[:CAP], "total": len(rows), "untested": sum(not r["tested"] for r in rows[:CAP]),
            "size": Z.collect(root)}


def line(d):
    return _line_hotspots(d)


def _line_hotspots(d):
    if not d["total"]:
        return "no hotspots yet"
    top = d["files"][0]
    return "%d hotspots, top %s (%d commits, %d lines); %d of top %d without a test by name" % (
        d["total"], top["path"], top["commits"], top["lines"], d["untested"], len(d["files"]))


def render(d):
    return _render_hotspots(d) + render_size(d["size"])


def _render_hotspots(d):
    if not d["total"]:
        return '<div class="card"><h2>Hotspots</h2><p class="muted">%s</p></div>' % e(EMPTY)
    rows = "".join('<tr><td class="mono">%s</td><td>%d</td><td>%d</td><td>%d</td><td><span class="imp %s">%s</span></td></tr>' % (
        e(r["path"]), r["commits"], r["lines"], r["score"], "low" if r["tested"] else "medium", "test by name" if r["tested"] else "no test by name")
        for r in d["files"])
    cap = '<p class="muted small">Top %d of %d files; full list in data.json.</p>' % (len(d["files"]), d["total"]) if d["total"] > len(d["files"]) else ""
    return ('<div class="card"><h2>Hotspots (churn × size)</h2><div class="scroll"><table><thead><tr><th>File</th><th>Commits</th><th>Lines</th><th>Score</th><th>Tests</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div>' % (rows, cap))


def render_size(z):
    b, ac = z["budgets"], z["always_loaded"]
    action = {f["subject"]: f for f in z["flags"]}
    rows = "".join('<tr><td class="mono">%s</td><td>%d</td><td>%d</td><td><span class="imp %s">%s</span></td><td>%s</td></tr>' % (
        e(r["path"]), r["lines"], b["file_lines_max"] if r["lines"] > b["file_lines_max"] else b["file_lines_warn"],
        action[r["path"]]["level"] if r["path"] in action else "low", e(action[r["path"]]["kind"]) if r["path"] in action else "ok",
        e(action[r["path"]]["action"]) if r["path"] in action else "") for r in z["files"][:Z.TOP])
    files = ('<div class="scroll"><table><thead><tr><th>File</th><th>Lines</th><th>Budget</th><th>Flag</th><th>Suggested action</th></tr></thead><tbody>%s</tbody></table></div>' % rows
             if rows else '<p class="muted">No product file is over %d lines.</p>' % b["file_lines_warn"])
    more = '<p class="muted small">Top %d of %d flagged files; full list in data.json.</p>' % (Z.TOP, len(z["files"])) if len(z["files"]) > Z.TOP else ""
    g7, g30 = z["growth"].get("7"), z["growth"].get("30")
    arows = "".join("<tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(Z.LABELS[a]), z["areas"][a]["files"], format(z["areas"][a]["lines"], ","),
        e(Z.growth_text(g7, a) if g7 else Z.NO_HISTORY), e(Z.growth_text(g30, a) if g30 else Z.NO_HISTORY)) for a in Z.AREAS)
    other = [f for f in z["flags"] if not f["kind"].startswith("file")]
    flag_rows = "".join('<li class="alert">%s</li>' % e(Z.text(f)) for f in other)
    ratio = "test-to-code ratio %s" % z["test_ratio"] if z["test_ratio"] is not None else "no product code yet"
    ctx = ("Always loaded: ~%d tokens (CLAUDE.md %d, session start note %d; budget %d). %d agents (max %d), %d skills, %d hooks, %d scripts; %s." % (
        ac["total"], ac["claude_md"], ac["session_start"], b["always_loaded_tokens_max"], z["counts"]["agents"], b["agents_max"],
        z["counts"]["skills"], z["counts"]["hooks"], z["counts"]["scripts"], ratio))
    return ('<div class="card"><h2>Size (budgets in factory.json budgets.size)</h2><p class="muted">%s</p>%s%s<ul class="plain">%s</ul>'
            '<h3>Areas and growth</h3><div class="scroll"><table><thead><tr><th>Area</th><th>Files</th><th>Lines</th><th>Growth 7 days</th><th>Growth 30 days</th></tr></thead>'
            '<tbody>%s</tbody></table></div></div>' % (e(ctx), files, more, flag_rows, arows))

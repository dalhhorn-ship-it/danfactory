"""Autonomy tab: Issues block (ADR 0008) from the issues/ ledger and its git history, Runner block (ADR 0009) from
metrics/runner.jsonl and the staging branch, Learning block (ADR 0010 C7, scripts/learn.py) from the same rows and the gate rows.
Empty state when there is no ledger or runner activity yet; nothing here ever fails the dashboard build."""
import html
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import issues as L  # noqa: E402
try:  # a project copy without runner.py (or gate.py) still gets the Issues block
    import runner as R  # noqa: E402
except Exception:  # noqa: BLE001
    R = None
try:  # release train block (AUTO-5)
    import release as REL  # noqa: E402
except Exception:  # noqa: BLE001
    REL = None
try:  # C7 learning block (ADR 0010); optional like the runner
    import learn as LN  # noqa: E402
except Exception:  # noqa: BLE001
    LN = None

EMPTY = L.EMPTY
RUNNER_EMPTY = ("No runner activity yet: `python3 scripts/runner.py run --next` after setting factory.json autonomy.enabled "
                "(docs/policies/runner.md).")
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
    try:
        rn = R.summary(root) if R else {"exists": False}
    except Exception as ex:  # noqa: BLE001 - no git, no staging, a broken row: the block is empty, the dashboard still builds
        rn = {"exists": False, "error": str(ex)[:200]}
    return {"issues": st, "runner": rn, "release": collect_release(root), "learning": collect_learning(root)}


def collect_learning(root):
    try:
        return LN.analyze(root) if LN else {"exists": False}
    except Exception as ex:  # noqa: BLE001 - a bad row file must not fail the dashboard build
        return {"exists": False, "error": str(ex)[:200]}


def line(d):
    st, rn = d["issues"], d.get("runner") or {}
    run = ""
    if rn.get("exists"):
        run = "; runner: %d fixed in %d attempt(s), $%.2f today of $%.2f%s" % (
            rn["fixed"], rn["attempts"], rn["spend_today"], rn["daily_cap"], ", %d parked" % len(rn["parked"]) if rn["parked"] else "")
    run += release_line(d.get("release"))
    lrn = d.get("learning") or {}
    if lrn.get("exists"):
        run += "; learning: %d candidate rule(s)%s" % (len(lrn["candidates"]), (" (" + ", ".join(c["code"] for c in lrn["candidates"][:3]) + ")") if lrn["candidates"] else "")
    if not st["exists"]:
        return "no issue ledger yet" + run
    old = st["oldest_open"]
    return "issues: %d open, %d fixed%s%s%s" % (st["open"], st["fixed"], ", %d blocked" % st["blocked"] if st.get("blocked") else "",
                                              ", oldest %s open %dd" % (old["id"], old["days"]) if old else "", run)


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


def _par(p):
    if not p.get("runs"):
        return "none yet (runner.py run --next --parallel N)"
    return "%d run(s), max concurrency %d, %d stale-after-merge" % (p["runs"], p["max_concurrent"], p["stale_after_merge"])


def render_runner(rn):
    if not rn.get("exists"):
        return '<div class="card"><h2>Runner</h2><p class="muted">%s</p></div>' % e(RUNNER_EMPTY)
    pct = lambda v: "n/a" if v is None else "%d%%" % round(100 * v)  # noqa: E731
    num = lambda v, f: "n/a" if v is None else f % v  # noqa: E731
    facts = [("Runs / attempts", "%d / %d" % (rn["runs"], rn["attempts"])), ("Issues fixed", rn["fixed"]),
             ("First-try pass rate", pct(rn["first_try_rate"])), ("Rework per fixed issue", num(rn["rework_per_fixed"], "%.1f")),
             ("Cost per fixed issue", num(rn["cost_per_fixed"], "$%.2f")),
             ("Spend today / daily cap", "$%.2f / $%.2f" % (rn["spend_today"], rn["daily_cap"])),
             ("%s ahead of %s" % (rn["staging"], rn["prod"]), "n/a" if rn["staging_lead"] is None else "%d commit(s), not promoted" % rn["staging_lead"]),
             ("Parallel runs", _par(rn.get("parallel") or {})),
             ("Autonomy", "enabled" if rn["enabled"] else "disabled")]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    parked = "".join('<tr><td class="mono nowrap">%s</td><td>%s</td><td class="mono">%s</td></tr>' % (
        e(p["id"]), e(p["title"]), e(", ".join(p["codes"]) or "no codes")) for p in rn["parked"]) \
        or '<tr><td colspan="3" class="muted">No parked issues.</td></tr>'
    return ('<div class="card"><h2>Runner</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>Parked issues</h2><table><thead><tr><th>ID</th><th>Issue</th><th>Last codes</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % (kv, parked))


LEARN_EMPTY = ("No rejection data yet: `python3 scripts/learn.py report` lists recurring failure codes once the runner or the gate "
               "has recorded rejections (docs/policies/runner-release.md, Learning).")
WEEKS = 6


def render_learning(ln):
    """Learning block (C7): codes over time, rework and cost per fixed issue, candidate rules, first-try trend."""
    if not ln or not ln.get("exists"):
        return '<div class="card"><h2>Learning</h2><p class="muted">%s</p></div>' % e(LEARN_EMPTY)
    pct = lambda v: "n/a" if v is None else "%d%%" % round(100 * v)  # noqa: E731
    num = lambda v, f: "n/a" if v is None else f % v  # noqa: E731
    facts = [("Rejection codes recorded", ln["rejections"]), ("First-try pass rate", pct(ln["first_try_rate"])),
             ("Rework per fixed issue", num(ln["rework_per_fixed"], "%.1f")), ("Cost per fixed issue", num(ln["cost_per_fixed"], "$%.2f"))]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    weeks = list(ln["per_week"])[-WEEKS:]
    tot = {}
    for w in weeks:
        for c, n in ln["per_week"][w].items():
            tot[c] = tot.get(c, 0) + n
    codes = sorted(tot, key=lambda c: (-tot[c], c))[:8]
    codes_t = ('<div class="scroll"><table><thead><tr><th>Week</th>%s</tr></thead><tbody>%s</tbody></table></div>' % (
        "".join('<th class="mono">%s</th>' % e(c) for c in codes),
        "".join("<tr><td>%s</td>%s</tr>" % (e(w), "".join("<td>%d</td>" % ln["per_week"][w].get(c, 0) for c in codes)) for w in weeks))
        if codes else '<p class="muted small">No rejection codes.</p>')
    trend = "".join("<tr><td>%s</td><td>%d of %d</td><td>%s</td></tr>" % (e(t["week"]), t["passed"], t["issues"], pct(t["rate"]))
                    for t in ln["first_try"][-WEEKS:]) or '<tr><td colspan="3" class="muted">No attempts yet.</td></tr>'
    cand = "".join('<tr><td class="mono">%s</td><td>%s</td><td>%d in %d days (%d total)</td><td class="small">%s</td></tr>' % (
        e(c["code"]), e(c["source"]), c["in_window"], ln["window"], c["total"], e(c["examples"][-1] if c["examples"] else ""))
        for c in ln["candidates"]) or '<tr><td colspan="4" class="muted">No code recurs %d times in %d days.</td></tr>' % (ln["threshold"], ln["window"])
    return ('<div class="card"><h2>Learning</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>Failure codes over time</h2>%s</div>'
            '<div class="card"><h2>First-try pass trend</h2><table><thead><tr><th>Week</th><th>Passed first try</th><th>Rate</th></tr></thead>'
            '<tbody>%s</tbody></table></div>'
            '<div class="card"><h2>Candidate rules</h2><table><thead><tr><th>Code</th><th>Source</th><th>Recurrence</th><th>Latest example</th></tr></thead>'
            '<tbody>%s</tbody></table><p class="muted small">Suggestions only: a rule needs a PRD (metrics/LEARN.md has the examples).</p></div>'
            % (kv, codes_t, trend, cand))


def render(d):
    return '<div class="stack">%s%s%s%s</div>' % (render_issues(d["issues"]), render_runner(d.get("runner") or {"exists": False}),
                                                render_release(d.get("release") or {"exists": False}),
                                                render_learning(d.get("learning")))


def render_issues(st):
    if not st["exists"]:
        return '<div class="card"><h2>Issues</h2><p class="muted">%s</p></div>' % e(EMPTY)
    old = st["oldest_open"]
    facts = [("Open", st["open"]), ("Fixed", st["fixed"]), ("Blocked (parked by the runner)", st.get("blocked", 0)),
             ("Oldest open issue", "%s, %d day(s)" % (old["id"], old["days"]) if old else "none open")]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    prd = "".join('<tr><td class="mono">%s</td><td>%d</td></tr>' % (e(k), v) for k, v in st["by_prd"].items()) \
        or '<tr><td class="muted">No open issues.</td></tr>'
    trend = _bars(st["trend"]) if st.get("trend") else '<p class="muted small">No git history of issues/ yet: commit the ledger to see the daily trend.</p>'
    rows = "".join('<tr><td class="mono nowrap">%s</td><td>%s</td><td class="mono">%s</td><td>%d</td><td>%s</td></tr>' % (
        e(i["id"]), e(i["title"][:90]), e(i["prd"]), i["tests"], e("%dd" % i["age"]) if i["age"] is not None else "–") for i in st["issues"]) \
        or '<tr><td colspan="5" class="muted">No open issues.</td></tr>'
    cap = '<p class="muted small">Oldest %d of %d open issues; full list in data.json.</p>' % (len(st["issues"]), st["open"]) if st["open"] > len(st["issues"]) else ""
    return ('<div class="card"><h2>Issues</h2><table><tbody>%s</tbody></table>%s</div>'
            '<div class="card"><h2>Open by PRD</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>Open issues</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Title</th><th>PRD</th><th>Tests</th><th>Age</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s</div>' % (kv, trend, prd, rows, cap))


# ---- Release train block (AUTO-5, ADR 0010): staging lead, last verify, days since promotion, open revert branches
RELEASE_EMPTY = "No release verification yet: `python3 scripts/release.py verify` (docs/policies/runner-release.md)."


def collect_release(root):
    try:
        return REL.summary(root) if REL else {"exists": False}
    except Exception as ex:  # noqa: BLE001 - no git, no staging, a broken row: the block is empty, the dashboard still builds
        return {"exists": False, "error": str(ex)[:200]}


def release_line(rl):
    if not rl or not rl.get("exists"):
        return ""
    days = rl["days_since_promotion"]
    return "; release: %s ahead %s, verify %s, promoted %s%s" % (
        rl["staging"], "?" if rl["lead"] is None else rl["lead"], rl["verdict"] or "none",
        "never" if days is None else "%dd ago" % days, ", %d revert branch(es)" % len(rl["reverts"]) if rl["reverts"] else "")


def render_release(rl):
    if not rl.get("exists"):
        return '<div class="card"><h2>Release train</h2><p class="muted">%s</p></div>' % e(RELEASE_EMPTY)
    days = rl["days_since_promotion"]
    verdict = "none yet" if not rl["verdict"] else "%s%s%s" % (
        rl["verdict"], " [%s]" % ", ".join(rl["codes"]) if rl["codes"] else "", " (stale: %s moved since)" % rl["staging"] if rl["fresh"] is False else "")
    facts = [("%s ahead of %s" % (rl["staging"], rl["prod"]), "n/a" if rl["lead"] is None else "%d commit(s), not promoted" % rl["lead"]),
             ("Last verify verdict", verdict), ("Last verified", rl["verified_at"] or "never"),
             ("Days since last promotion", "never promoted" if days is None else days)]
    kv = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(k), e(v)) for k, v in facts)
    rev = "".join('<tr><td class="mono">%s</td><td>review it and push it yourself</td></tr>' % e(b) for b in rl["reverts"]) \
        or '<tr><td colspan="2" class="muted">No open revert branches.</td></tr>'
    return ('<div class="card"><h2>Release train</h2><table><tbody>%s</tbody></table></div>'
            '<div class="card"><h2>Open revert branches</h2><table><tbody>%s</tbody></table></div>' % (kv, rev))

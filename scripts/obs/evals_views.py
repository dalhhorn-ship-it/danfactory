"""HTML/SVG for the Evals tab additions (EVAL-4): gate coverage, library, heatmap, economics. No JS, no external URLs.

Colour is never the only carrier: every status, strength and cell also carries its words or number.
"""
import html

CMD = "python3 scripts/evals.py run"
LEGEND = ("Proof strength: <b>strong</b> = a guard or hook blocked a call in the run; <b>weak</b> = the agent never reached the guard "
          "(it declined first), so a pass says little about the guard; <b>n/a</b> = no hook can fire for this task (an instruction, "
          "not a hook); <b>unknown</b> = runs recorded before hook evidence existed.")


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def _badge(label, cls):
    return '<span class="pf %s">%s</span>' % (cls, e(label))


def _strength(label, why):
    return '<span class="pf s-%s" title="%s">%s</span>' % (label.replace("/", ""), e(why), e(label))


def coverage(cov, rules_ok):
    if not rules_ok:
        return ('<h3>Gate coverage</h3><p class="muted">No rule inventory (evals/rules.json missing or unreadable). '
                'Add one rule per CLAUDE.md rule, hook and policy; see docs/policies/evals.md.</p>')
    if not cov:
        return '<h3>Gate coverage</h3><p class="muted">evals/rules.json lists no rules yet.</p>'
    unc = [c for c in cov if c["status"] == "uncovered"]
    rows = "".join('<tr><td>%s</td><td>%s</td><td class="mono">%s</td><td>%s</td><td>%s</td></tr>' % (
        e(c["title"]), e(c["kind"]), e(c["source"]), _badge(c["status"], "c-" + c["status"].replace("covered (", "covered-").replace(" proof)", "").replace(")", "")),
        e(", ".join("%s (%s)" % (t, c["strengths"][t]) for t in c["tasks"]) or "none")) for c in cov)
    head = ('<p><b>%d of %d rules have no eval</b>: they are the eval backlog, listed first.</p>' % (len(unc), len(cov))
            if unc else '<p>Every listed rule is covered by at least one eval.</p>')
    return ('<h3>Gate coverage</h3>%s<div class="scroll"><table><thead><tr><th>Rule</th><th>Kind</th><th>Source</th><th>Status</th>'
            '<th>Covered by (proof)</th></tr></thead><tbody>%s</tbody></table></div>'
            '<p class="muted small">uncovered = no task lists a gate of this rule; covered (weak) = only tasks whose guard never acted; '
            'covered (unknown proof) = only tasks without hook evidence. Inventory: evals/rules.json (curated).</p>' % (head, rows))


def _dots(dots):
    if not dots:
        return '<span class="muted">no runs</span>'
    return '<span class="dots" title="oldest to newest: %s">%s</span>' % (
        e(" ".join("pass" if d else "fail" for d in dots)), "".join("●" if d else "○" for d in dots))


def library(lib):
    if not lib:
        return '<h3>Eval library</h3><p class="muted">No tasks in evals/tasks/. See docs/policies/evals.md (adding a task).</p>'
    rows = []
    for t in lib:
        summary = t["prompt"][:110] + ("…" if len(t["prompt"]) > 110 else "")
        rows.append('<tr><td><b>%s</b><div class="muted small">%s</div><div class="mono small">%s</div></td><td>%s</td><td>%s</td><td>%s</td>'
                    '<td>%s</td><td class="nowrap">%s</td><td>%s</td><td class="nowrap">%s</td><td>%s</td></tr>' % (
                        e(t["title"]), e(summary), e(t["id"]), e(", ".join(t["gates"]) or "–"), e(", ".join(t["covers"]) or "–"),
                        e(", ".join(t["graders"]) or "–"), e(t["fixture"] or "–"), e(t["added"]), _dots(t["dots"]),
                        "–" if t["cost_per_run"] is None else "$%.3f" % t["cost_per_run"], _strength(t["strength"], t["strength_why"])))
    return ('<h3>Eval library</h3><div class="scroll"><table><thead><tr><th>Tests</th><th>Gates</th><th>Covers</th><th>Graders</th>'
            '<th>Fixture</th><th>Added</th><th>Last %d runs</th><th>Cost / run (USD)</th><th>Proof</th></tr></thead><tbody>%s</tbody></table></div>'
            '<p class="muted small">%s Dots: ● pass, ○ fail, oldest first. Added = first git commit of task.json (derived; "unknown" without history).</p>'
            % (10, "".join(rows), LEGEND))


def _band(pct):
    return "h0" if pct == 0 else "h1" if pct < 50 else "h2" if pct < 100 else "h3"


def heatmap(h):
    if not h["cols"] or not h["tasks"]:
        return '<h3>Results by run set</h3><p class="muted">No run sets yet. Run %s.</p>' % e(CMD)
    head = "".join('<th title="%s">%s<div class="muted small">%s · N=%d</div></th>' % (
        e(c["set"]), e(c["set"][:12]), e(c["date"]), c["n"]) for c in h["cols"])
    body = []
    for tid in h["tasks"]:
        cells = []
        for c, col in zip(h["grid"][tid], h["cols"]):
            if not c:
                cells.append('<td class="hm" title="%s not in set %s"></td>' % (e(tid), e(col["set"])))
                continue
            pct = round(100.0 * c["passes"] / c["runs"])
            cells.append('<td class="hm %s" title="%s in %s: %d of %d runs passed">%d%%</td>' % (
                _band(pct), e(tid), e(col["set"]), c["passes"], c["runs"], pct))
        body.append('<tr><td class="mono">%s</td>%s</tr>' % (e(tid), "".join(cells)))
    return ('<h3>Results by run set</h3><div class="scroll"><table class="heat"><thead><tr><th>Task</th>%s</tr></thead><tbody>%s</tbody></table></div>'
            '<p class="muted small">Cell = pass rate of the task in that set (number and shade: 0%% / under 50%% / under 100%% / 100%%). '
            'Empty = task not in the set. Columns oldest to newest, last %d sets.</p>' % (head, "".join(body), len(h["cols"])))


def _scatter(pts):
    W, H, L, B, T, R = 360, 200, 44, 28, 12, 16
    top = max(max(p["cost_per_run"] for p in pts), 0.001) * 1.15
    x = lambda v: L + (W - L - R) * v / top  # noqa: E731
    y = lambda v: T + (H - T - B) * (1 - v)  # noqa: E731
    g = ['<line class="ax" x1="%d" y1="%d" x2="%d" y2="%d"/><line class="ax" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (L, H - B, W - R, H - B, L, T, L, H - B)]
    for v in (0, 0.5, 1):
        g.append('<text class="tk" x="%d" y="%d" text-anchor="end">%d%%</text>' % (L - 4, y(v) + 4, v * 100))
    g.append('<text class="tk" x="%d" y="%d" text-anchor="end">$%.3f</text><text class="tk" x="%d" y="%d">$0</text>' % (W - R, H - B + 14, top, L, H - B + 14))
    g.append('<text class="tk" x="%d" y="%d" text-anchor="middle">mean cost per run (USD)</text>' % ((L + W - R) // 2, H - 4))
    for p in pts:
        cls = "pt best" if p["cheapest_ok"] else "pt"
        g.append('<g class="%s"><title>%s: %.0f%% pass, $%.4f per run%s</title><circle cx="%.1f" cy="%.1f" r="6"/>'
                 '<text x="%.1f" y="%.1f">%s</text></g>' % (cls, e(p["model"]), p["pass_rate"] * 100, p["cost_per_run"],
                                                             ", cheapest at or above the threshold" if p["cheapest_ok"] else "",
                                                             x(p["cost_per_run"]), y(p["pass_rate"]), x(p["cost_per_run"]) + 9,
                                                             y(p["pass_rate"]) - 8, e(p["model"])))
    return ('<svg class="scatter" role="img" aria-label="Pass rate against mean cost per run, one point per model" '
            'viewBox="0 0 %d %d" width="100%%" style="max-width:420px" xmlns="http://www.w3.org/2000/svg">%s</svg>' % (W, H, "".join(g)))


def economics(ec):
    pts = ec["points"]
    if not pts:
        return '<h3>Eval economics</h3><p class="muted">No runs yet. Run %s --model &lt;m&gt; to add a model.</p>' % e(CMD)
    rows = "".join('<tr%s><td class="mono">%s%s</td><td>%.0f%%</td><td>$%.4f</td><td>%s</td><td>{:,}</td><td>%.1f</td><td>%d</td></tr>'.replace(
        "{:,}", "%s") % (' class="best"' if p["cheapest_ok"] else "", e(p["model"]), " (cheapest at or above threshold)" if p["cheapest_ok"] else "",
                        p["pass_rate"] * 100, p["cost_per_run"], "–" if p["cost_per_pass"] is None else "$%.4f" % p["cost_per_pass"],
                        "{:,}".format(p["tokens_per_run"]), p["wall_s"], p["n"]) for p in pts)
    note = ""
    if len(pts) < 2:
        note = ('<p class="muted">One model on record: run <span class="mono">%s --model &lt;m&gt;</span> with a second model to compare cost and pass rate '
                '(spends money).</p>' % e(CMD))
    elif ec["pick"]:
        note = ('<p>Cheapest model within %.0f points of the best pass rate: <b>%s</b>.</p>' % (ec["threshold"] * 100, e(ec["pick"])))
    return ('<h3>Eval economics</h3>%s<div class="econ">%s<div class="scroll"><table><thead><tr><th>Model</th><th>Pass rate</th><th>Cost / run</th>'
            '<th>Cost / passing run</th><th>Tokens / run</th><th>Wall s / run</th><th>N</th></tr></thead><tbody>%s</tbody></table></div></div>'
            '<p class="muted small">One point per model, from its latest run set; runs with an infrastructure error are not counted. '
            'Highlight = lowest cost per run among models within the regression threshold of the best pass rate.</p>'
            % (note, _scatter(pts), rows))

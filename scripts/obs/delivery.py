"""Delivery card (Overview): CI pass rate and time from metrics/ci-runs.json (scripts/ci_runs.py) and release cadence.

Offline: this module only reads files and git. The cache is written by scripts/ci_runs.py, the one script that
uses the network. Deploy frequency lives on the Flow tab, so the card links there instead of repeating it.
"""
import datetime
import html
import json
import re

from . import sources as S

CACHE = "metrics/ci-runs.json"
WEEKS = 8
DECIDED = ("success", "failure")
CHANGELOG_RE = re.compile(r"(?m)^##\s+\[?v?(\d+\.\d+(?:\.\d+)?[\w.+-]*)\]?\s*(?:[-–—(]\s*)?\(?(\d{4}-\d{2}-\d{2})?\)?\s*$")
TAG_RE = re.compile(r"v?\d+\.\d+(\.\d+)?")
NO_HISTORY = "No CI history yet. Run python3 scripts/ci_runs.py (CI does it on every build) to write metrics/ci-runs.json."


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def to_time(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def week_of(day):
    y, w, _ = day.isocalendar()
    return "%d-W%02d" % (y, w)


def last_weeks(today, n=WEEKS):
    """The last n ISO week keys, oldest first, ending with the week of today."""
    monday = today - datetime.timedelta(days=today.weekday())
    return [week_of(monday - datetime.timedelta(weeks=i)) for i in range(n - 1, -1, -1)]


def pct(part, whole):
    return round(100.0 * part / whole) if whole else None


def median(values):
    v = sorted(values)
    if not v:
        return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def p90(values):
    v = sorted(values)
    return v[min(len(v) - 1, int(0.9 * len(v)))] if v else None


def parse_runs(text):
    """The runs list from metrics/ci-runs.json text, or None when missing or not valid."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    runs = data.get("runs") if isinstance(data, dict) else data
    return [r for r in runs if isinstance(r, dict)] if isinstance(runs, list) else None


def ci_metrics(runs, today, main_branch="main"):
    """Pass rates, durations, recent failures and runs per week. Cancelled and skipped runs are not decided."""
    if not runs:
        return None
    runs = sorted(runs, key=lambda r: r.get("created_at") or "", reverse=True)
    decided = [r for r in runs if r.get("conclusion") in DECIDED]
    last30 = decided[:30]
    main30 = [r for r in decided if r.get("head_branch") == main_branch][:30]
    mins = []
    for r in decided[:100]:
        a, b = to_time(r.get("run_started_at") or r.get("created_at")), to_time(r.get("updated_at"))
        if a and b and b >= a:
            mins.append((b - a).total_seconds() / 60)
    weeks = last_weeks(today)
    per = {w: {"runs": 0, "ok": 0, "decided": 0} for w in weeks}
    for r in runs:
        t = to_time(r.get("created_at"))
        w = week_of(t.date()) if t else None
        if w in per:
            per[w]["runs"] += 1
            if r.get("conclusion") in DECIDED:
                per[w]["decided"] += 1
                per[w]["ok"] += r.get("conclusion") == "success"
    failures = [{"date": (r.get("created_at") or "")[:10], "branch": r.get("head_branch") or "",
                 "name": r.get("name") or "", "url": r.get("html_url") or ""}
                for r in runs if r.get("conclusion") == "failure"][:3]
    return {
        "runs": len(runs), "main_branch": main_branch,
        "pass_rate_30": pct(sum(r["conclusion"] == "success" for r in last30), len(last30)), "decided_30": len(last30),
        "main_pass_rate": pct(sum(r["conclusion"] == "success" for r in main30), len(main30)), "main_decided": len(main30),
        "median_min": round(median(mins), 1) if mins else None, "p90_min": round(p90(mins), 1) if mins else None,
        "failures": failures, "weeks": weeks,
        "runs_per_week": [per[w]["runs"] for w in weeks],
        "pass_per_week": [pct(per[w]["ok"], per[w]["decided"]) for w in weeks],
    }


def parse_changelog(text):
    """[{version, date}] from `## 1.2.0 (2026-01-02)` or `## [1.2.0] - 2026-01-02` headings."""
    return [{"version": m.group(1), "date": m.group(2)} for m in CHANGELOG_RE.finditer(text or "") if m.group(2)]


def release_metrics(releases, today):
    """Count, median gap and days since the last release, from [{version, date}]."""
    rel = []
    for r in releases or []:
        try:
            rel.append((r["version"], datetime.date.fromisoformat(r["date"])))
        except (KeyError, TypeError, ValueError):
            pass
    if not rel:
        return None
    rel.sort(key=lambda x: x[1])
    gaps = [(b[1] - a[1]).days for a, b in zip(rel, rel[1:])]
    gap = median(gaps)
    return {"count": len(rel), "last": rel[-1][0],
            "median_gap_days": (int(gap) if gap == int(gap) else gap) if gaps else None,
            "days_since_last": (today - rel[-1][1]).days}


def tag_releases(root):
    rows = []
    for line in S.git(root, "for-each-ref", "refs/tags", "--format=%(refname:short)|%(creatordate:short)").splitlines():
        name, _, date = line.partition("|")
        if TAG_RE.fullmatch(name):
            rows.append({"version": name, "date": date})
    return rows


def collect(root, base, today=None):
    """base: the dashboard data dict (needs "deploy" and optionally "dashboard_conf")."""
    today = today or datetime.date.today()
    conf = base.get("dashboard_conf") or {}
    branch = (base.get("deploy") or {}).get("production_branch") or "main"
    ci = ci_metrics(parse_runs(S.read(root, CACHE)), today, branch)
    changelog = parse_changelog(S.read(root, conf.get("changelog_file") or "CHANGELOG.md"))
    rel = release_metrics(changelog or tag_releases(root), today)
    return {"ci": ci, "releases": dict(rel, source="CHANGELOG" if changelog else "tags") if rel else None}


def _tile(label, value, sub, state="na", words=("healthy", "watch", "failing often")):
    badge = {"ok": words[0], "warn": words[1], "bad": words[2], "na": ""}[state]
    return ('<div class="tile %s"><div class="label">%s</div><div class="value">%s</div><div class="sub">%s%s</div></div>'
            % (state, e(label), e(value), e(sub), ' · <span class="badge">%s</span>' % badge if badge else ""))


def _num(v, suffix=""):
    return "–" if v is None else "%s%s" % (v, suffix)


def _state(v):
    return "na" if v is None else "ok" if v >= 90 else "warn" if v >= 70 else "bad"


def bars(values, weeks, title, unit=""):
    """Inline SVG bar chart, one bar per ISO week (no JS). None draws a stub titled "no data", never 0%."""
    nums = [v for v in values if isinstance(v, (int, float))]
    top = max(nums) if nums and max(nums) > 0 else 1
    rects = []
    for i, (v, w) in enumerate(zip(values, weeks)):
        x = i * 14 + 2
        if isinstance(v, (int, float)):
            h = max(1.5, 36.0 * v / top) if v else 1.5
            rects.append('<rect x="%d" y="%.1f" width="10" height="%.1f" rx="1.5"%s><title>%s: %s%s</title></rect>'
                         % (x, 40 - h, h, ' class="zero"' if not v else "", e(w), e(v), e(unit)))
        else:
            rects.append('<rect x="%d" y="38.5" width="10" height="1.5" class="zero"><title>%s: no data</title></rect>'
                         % (x, e(w)))
    last = values[-1] if values else None
    return ('<figure class="bars"><figcaption>%s <b>%s</b> <span class="muted">this week</span></figcaption>'
            '<svg viewBox="0 0 %d 40" preserveAspectRatio="none" role="img" aria-label="%s per week">%s</svg>'
            '<div class="axis"><span>%s</span><span>%s</span></div></figure>'
            % (e(title), e(_num(last, unit)) if isinstance(last, (int, float)) else "no data", len(weeks) * 14, e(title),
               "".join(rects), e(weeks[0] if weeks else ""), e(weeks[-1] if weeks else "")))


def render(dl):
    ci, rel = dl.get("ci"), dl.get("releases")
    parts = []
    if ci is None:
        parts.append('<p class="muted">%s</p>' % e(NO_HISTORY))
    else:
        parts.append('<div class="tiles mini">%s</div>' % "".join([
            _tile("CI pass rate", _num(ci["pass_rate_30"], "%"), "last %d finished runs" % ci["decided_30"],
                  _state(ci["pass_rate_30"])),
            _tile("Pass rate on %s" % ci["main_branch"], _num(ci["main_pass_rate"], "%"), "last %d runs" % ci["main_decided"],
                  _state(ci["main_pass_rate"]), ("healthy", "watch", "red too often")),
            _tile("CI time", _num(ci["median_min"], " min"), "median · p90 %s" % _num(ci["p90_min"], " min")),
        ]))
        parts.append('<div class="charts">%s%s</div>' % (
            bars(ci["runs_per_week"], ci["weeks"], "CI runs"), bars(ci["pass_per_week"], ci["weeks"], "CI pass rate", "%")))
        fails = "".join('<li>%s on <span class="mono">%s</span>%s</li>' % (
            e(f["date"]), e(f["branch"]),
            ' · <a href="%s">%s</a>' % (e(f["url"]), e(f["name"] or "run")) if f["url"].startswith("https://") else "")
            for f in ci["failures"]) or '<li class="muted">No failed runs in the history.</li>'
        parts.append('<h3>Latest failures</h3><ul class="plain">%s</ul>' % fails)
        parts.append('<p class="muted small">Cancelled and skipped runs do not count toward pass rates.</p>')
    if rel:
        parts.append('<p class="small">Releases (%s): %d · median gap %s · %s days since %s</p>' % (
            e(rel["source"]), rel["count"], e(_num(rel["median_gap_days"], " days")), e(rel["days_since_last"]), e(rel["last"])))
    parts.append('<p class="muted small">Deploy frequency and failure rate: see the Flow tab.</p>')
    return '<div class="card"><h2>Delivery</h2>%s</div>' % "".join(parts)


def line(dl):
    """One SUMMARY.md cell, or "" when there is no CI history."""
    ci = dl.get("ci")
    if not ci:
        return ""
    return "%s pass (last %d), median %s" % (_num(ci["pass_rate_30"], "%"), ci["decided_30"], _num(ci["median_min"], " min"))

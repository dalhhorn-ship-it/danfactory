#!/usr/bin/env python3
"""Build the project dashboard: versions, progress, backlog, tech debt, key metrics.

  python3 scripts/dashboard.py            # write dashboard/index.html, data.json, SUMMARY.md
  python3 scripts/dashboard.py --open     # ...and open it in a browser
  python3 scripts/dashboard.py --print    # print SUMMARY.md (cheap status for agents)

Sources (all local, so every build can regenerate it offline):
  factory.json, docs/BACKLOG.md, docs/TECH-DEBT.md, docs/PLAN.md (optional), docs/decisions/,
  CHANGELOG.md (optional), metrics/*.jsonl, metrics/ci-runs.json (written by scripts/ci_runs.py),
  git tags/log, plus automated debt signals (TODO/FIXME markers, oversized files, codegraph cycles).
Output is a self-contained HTML file (no JS, no network) with two tabs: Overview and Roadmap
(two swimlanes, value vs technical foundation, in proposed sequence). dashboard/ is git-ignored;
CI uploads it as a build artifact and writes SUMMARY.md to the job summary.

BACKLOG.md may hold `## Milestone:` checklists, a `## Ranked backlog` release table, or both;
TECH-DEBT.md may be a checklist or a table. Parsers take text and never crash on a bad source.
Lane rules and paths are configurable in factory.json -> dashboard (see DASHBOARD_DEFAULTS).
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402

OUT = os.path.join(ROOT, "dashboard")
PHASES = ["brainstorm", "operating-model", "build"]
STATES = {" ": "todo", "~": "doing", "x": "done", "X": "done", "!": "blocked", "-": "dropped"}
ITEM_RE = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(.*)$")
MILESTONE_RE = re.compile(r"^##\s+(?:Milestone:\s*)?(.+?)\s*(?:\(target:\s*([0-9-]*)\s*\))?\s*$")
DEBT_RE = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(TD-?\d+)\s+(.*?)(?:\s+[—-]\s+(.*))?$")
# A tag is #word not glued to a word or an HTML entity (&#39;), so "C#" and "&#x27;" are not tags.
TAG_RE = re.compile(r"(?<![\w&])#([A-Za-z][\w-]*)")
TASK_ID = re.compile(r"^[A-Z]{1,3}-?\d+[a-z]?$")
TASK_REF = re.compile(r"\b[A-Z]{1,3}-?\d+[a-z]?\b")
MARKER_RE = r"\b(TODO|FIXME|HACK|XXX)\b"
SKIP_DIRS = ("docs/", ".claude/", ".factory/", "dashboard/", "metrics/", "templates/",
             "scripts/dashboard.py", "README.md", "CLAUDE.md")
LARGE_FILE_LINES = 500
# Roadmap swimlanes. An item goes to the value lane unless a rule puts it in the foundation lane:
#   1. tags: #value or #feature force value; a tag in FOUNDATION_TAGS (+ dashboard.foundation_tags) -> foundation;
#   2. dashboard.lane_overrides in factory.json, keyed by release id (first word: "v4") or exact item title;
#   3. a refactor round: release id matching dashboard.refactor_id_pattern (R1, R2...) or "refactor" in its note.
# Open tech-debt items always go to the foundation lane.
FOUNDATION_TAGS = {"foundation", "tech", "arch", "architecture", "infra", "runway", "debt", "tech-debt",
                   "refactor", "quality", "ci", "process", "security", "perf", "ops", "platform",
                   "safety", "robustness"}
LANES = (("value", "Value-driven features", "value for users"),
         ("foundation", "Technical foundation", "architecture, runway, tech debt"))
STATUS_WORDS = ("shipped", "next", "candidate", "later", "dropped")
RELEASE_SECTIONS = ("ranked backlog", "ranked releases", "releases")
# Ranked release table -> roadmap columns, by the first word of its Status cell.
ROADMAP_GROUPS = (("next", "Now", "the release being built"),
                  ("candidate", "Then", "candidates in rank order"),
                  ("later", "Later", "after the candidates"))
SEVERITY_TO_IMPACT = {"critical": "high", "major": "high", "high": "high", "medium": "medium",
                      "moderate": "medium", "minor": "low", "low": "low"}
CLOSED_RE = re.compile(r"^(done|resolved|fixed|closed|dropped|wontfix|paid)\b", re.I)
# factory.json -> "dashboard" overrides these keys.
DASHBOARD_DEFAULTS = {
    "plan_file": "docs/PLAN.md",
    "changelog_file": "CHANGELOG.md",
    "lane_overrides": {},
    "foundation_tags": [],
    "refactor_id_pattern": r"R\d+",
    "deploys_since": "",
    "github_repo": "",
}


# ---------------------------------------------------------------- sources

def git(*args):
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return p.stdout.strip() if p.returncode == 0 else ""
    except OSError:
        return ""


def read(path):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def strip_code(text):
    return re.sub(r"```.*?```", "", text, flags=re.S)


def plain(text):
    """Strip simple markdown (bold, code ticks, links) and squeeze spaces."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def trim(text, n):
    text = plain(text)
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def cells(line):
    """Cells of a markdown table row, or None when the line is not a row.
    Pipe safe: a `|` inside a code span or escaped as \\| does not split a cell."""
    line = line.strip()
    if not line.startswith("|"):
        return None
    out, cur, code, i = [], "", False, 1
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return out


def is_rule(c):
    return all(re.fullmatch(r":?-+:?", x or "-") for x in c)


TEXT_HEADS = ("task", "item", "what", "feel", "description", "summary", "title")


def map_row(header, c):
    """Map row cells to header names. If a stray pipe split the free-text column (first header that
    looks like text: task, item, what...), the columns after it are read from the end of the row and the
    surplus is joined back into the text cell, so Status and Milestone never shift."""
    if len(c) <= len(header) or not header:
        return {h: (c[i] if i < len(c) else "") for i, h in enumerate(header)}
    wide = next((i for i, h in enumerate(header) if any(w in h for w in TEXT_HEADS)), len(header) - 1)
    tail = len(header) - wide - 1
    row = {h: c[i] for i, h in enumerate(header[:wide])}
    row[header[wide]] = " | ".join(c[wide:len(c) - tail])
    for j, h in enumerate(header[wide + 1:]):
        row[h] = c[len(c) - tail + j]
    return row


def col(row, *names):
    """First cell whose header contains one of the names."""
    for n in names:
        for h, v in row.items():
            if n in h:
                return v
    return ""


def section_lines(text, headings):
    """Lines under the first '## heading' whose title (lower case) is in headings."""
    out, inside = [], False
    for line in strip_code(text or "").splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().lower() in headings
            continue
        if inside:
            out.append(line)
    return out


def tags_of(text):
    return [t.lower() for t in TAG_RE.findall(text or "")]


def parse_backlog(text):
    milestones, current = [], None
    for line in strip_code(text).splitlines():
        m = MILESTONE_RE.match(line)
        if line.startswith("## ") and m:
            current = {"name": m.group(1).strip(), "target": m.group(2) or "", "items": []}
            milestones.append(current)
            continue
        im = ITEM_RE.match(line)
        if im and current is not None:
            title = im.group(2).strip()
            size = re.search(r"\((S|M|L)\)", title)
            current["items"].append({
                "state": STATES.get(im.group(1), "todo"),
                "title": TAG_RE.sub("", re.sub(r"\s*\((S|M|L)\)", "", title)).strip(),
                "size": size.group(1) if size else "",
                "tags": TAG_RE.findall(title),
            })
    for ms in milestones:
        live = [i for i in ms["items"] if i["state"] != "dropped"]
        done = sum(i["state"] == "done" for i in live)
        ms["total"], ms["done"] = len(live), done
        ms["pct"] = round(100.0 * done / len(live)) if live else 0
    return milestones


def parse_releases(text):
    """Rows of a ranked release table under '## Ranked backlog' (or '## Releases') in BACKLOG.md.

    Columns are found by header name: Rank, Release (or Name), a text column (What users feel /
    Summary / Description), Size, Plan tasks (or Tasks), Status. The release name is the bold part of
    its cell; the rest is a note. The first word of Status (shipped, next, candidate, later, dropped)
    is the chip. Returns [] when there is no such table."""
    rows, header = [], None
    for line in section_lines(text, RELEASE_SECTIONS):
        c = cells(line)
        if c is None:
            if header is not None and rows:
                break
            continue
        if header is None:
            header = [h.lower() for h in c]
            continue
        if is_rule(c):
            continue
        r = map_row(header, c)
        release = col(r, "release", "name") or (c[1] if len(c) > 1 else "")
        m = re.search(r"\*\*(.+?)\*\*", release)
        name = plain(m.group(1) if m else release)
        if not name:
            continue
        status = plain(col(r, "status"))
        word = status.split(" ", 1)[0].strip(",.;:").lower() if status else ""
        rows.append({
            "rank": plain(col(r, "rank")),
            "release": name,
            "id": name.split(" ", 1)[0],
            "note": plain(release[m.end():]) if m else "",
            "feel": trim(col(r, "feel", "what", "summary", "description"), 100),
            "size": plain(col(r, "size")),
            "tasks": plain(col(r, "tasks")),
            "tags": tags_of(line),
            "status": status,
            "chip": word if word in STATUS_WORDS else "other",
        })
    return rows


def parse_plan_tasks(text):
    """Task rows of a plan table (docs/PLAN.md): header starts with Id and has Milestone or Status.
    Pipe safe via map_row. Returns [{id, milestone, status}]."""
    rows, header = [], None
    for line in strip_code(text or "").splitlines():
        c = cells(line)
        if c is None:
            continue
        low = [h.lower() for h in c]
        if low and low[0] == "id" and ("milestone" in low or "status" in low):
            header = low
            continue
        if header is None or not c or not TASK_ID.match(c[0]) or len(c) < len(header):
            continue
        r = map_row(header, c)
        status = plain(r.get("status", ""))
        rows.append({"id": c[0], "milestone": plain(r.get("milestone", "")),
                     "status": status.split(" ", 1)[0].strip(",.;:").lower() or "todo"})
    return rows


def parse_debt(text):
    """Tech debt register: checklist lines (`- [ ] TD-001 Title — impact: high · effort: M · area: x`)
    and/or a table with an Id column (Severity or Impact, Item, Where or Area, Size or Effort, Status).
    Severity major/critical counts as high impact."""
    items, section, header = [], "", None
    for line in strip_code(text).splitlines():
        if line.startswith("## "):
            section, header = line[3:].strip().lower(), None
            continue
        m = DEBT_RE.match(line)
        if m:
            attrs = dict(re.findall(r"(\w+):\s*([^·]+?)\s*(?:·|$)", m.group(4) or ""))
            items.append({
                "id": m.group(2), "title": m.group(3).strip(),
                "open": m.group(1) not in "xX" and not section.startswith("resolved"),
                "impact": attrs.get("impact", "").lower(), "effort": attrs.get("effort", ""),
                "area": attrs.get("area", ""),
            })
            continue
        c = cells(line)
        if c is None:
            continue
        if header is None:
            if c and c[0].lower() == "id":
                header = [h.lower() for h in c]
            continue
        if is_rule(c) or len(c) < len(header):
            continue
        r = map_row(header, c)
        sev = plain(col(r, "severity", "impact")).lower()
        status = plain(col(r, "status"))
        items.append({
            "id": plain(c[0]), "title": trim(col(r, "item", "title", "description"), 160),
            "open": not CLOSED_RE.match(status) and not section.startswith("resolved"),
            "impact": SEVERITY_TO_IMPACT.get(sev, ""), "effort": plain(col(r, "size", "effort")),
            "area": plain(col(r, "where", "area")),
        })
    return items


def parse_adr(text):
    """Status and title of one ADR in docs/decisions/ (`Status: proposed | accepted ...`)."""
    title = next((l[2:].strip() for l in (text or "").splitlines() if l.startswith("# ")), "")
    m = re.search(r"(?im)^\W*status:\s*\**\s*([a-z-]+)", text or "")
    return {"title": title, "status": m.group(1).lower() if m else ""}


def collect_decisions():
    """ADRs waiting for a decision (status proposed). The 0000 template is skipped."""
    base = os.path.join(ROOT, "docs", "decisions")
    if not os.path.isdir(base):
        return {"total": 0, "open": []}
    rows = []
    for fn in sorted(os.listdir(base)):
        if not re.match(r"\d{4}-.*\.md$", fn) or fn.startswith("0000"):
            continue
        rows.append(dict(parse_adr(read(os.path.join("docs", "decisions", fn))), file=fn))
    return {"total": len(rows), "open": [r for r in rows if r["status"] == "proposed"]}


def debt_signals(f):
    files = [p for p in git("ls-files").splitlines() if p and not p.startswith(SKIP_DIRS)]
    markers = {}
    out = git("grep", "-I", "-o", "-E", MARKER_RE, "--", *files) if files else ""
    for line in out.splitlines():
        kind = line.rsplit(":", 1)[-1]
        markers[kind] = markers.get(kind, 0) + 1
    large = []
    for p in files:
        full = os.path.join(ROOT, p)
        if os.path.isfile(full) and not p.endswith((".json", ".lock", ".md", ".svg", ".csv")):
            try:
                with open(full, "rb") as fh:
                    n = sum(1 for _ in fh)
            except OSError:
                continue
            if n > LARGE_FILE_LINES:
                large.append({"file": p, "lines": n})
    cycles = None
    if f.get("integrations", {}).get("codegraph") and shutil.which("codegraph"):
        try:
            p = subprocess.run(["codegraph", "cycles", "--json"], cwd=ROOT, capture_output=True, text=True,
                               timeout=60, check=False)
            if p.returncode not in (0, 1):  # 1 = cycles found; anything else = unsupported/failed
                raise ValueError(p.stderr[:200])
            data = json.loads(p.stdout or "[]")
            cycles = len(data if isinstance(data, list) else data.get("cycles", []))
        except (OSError, ValueError, subprocess.SubprocessError):
            cycles = None
    return {"markers": markers, "marker_total": sum(markers.values()),
            "large_files": sorted(large, key=lambda x: -x["lines"])[:10], "import_cycles": cycles}


def versions():
    current = read("VERSION").strip()
    if not current:
        for path, pat in (("package.json", r'"version"\s*:\s*"([^"]+)"'),
                          ("pyproject.toml", r'(?m)^version\s*=\s*"([^"]+)"'),
                          ("Cargo.toml", r'(?m)^version\s*=\s*"([^"]+)"')):
            m = re.search(pat, read(path))
            if m:
                current = m.group(1)
                break
    tags = []
    for line in git("for-each-ref", "refs/tags", "--sort=-creatordate", "--count=8",
                    "--format=%(refname:short)|%(creatordate:short)").splitlines():
        name, _, date = line.partition("|")
        tags.append({"tag": name, "date": date})
    if not current and tags:
        current = tags[0]["tag"]
    commits = []
    for line in git("log", "-8", "--format=%h|%cs|%s").splitlines():
        sha, date, subj = (line.split("|", 2) + ["", ""])[:3]
        commits.append({"sha": sha, "date": date, "subject": subj})
    return {"current": current or "unreleased", "tags": tags, "commits": commits,
            "sha": git("rev-parse", "--short", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "commit_count": int(git("rev-list", "--count", "HEAD") or 0)}


def metric_view(f):
    hist, toks = metrics.load(metrics.HISTORY), metrics.load(metrics.TOKENS)
    alerts, ideas, _ = metrics.analyse(f, hist, toks)
    full = [r for r in hist if r["kind"] == "test" and r.get("scope") == "full"]
    deps = [r for r in hist if r["kind"] == "deploy"]
    b = f.get("budgets", {})
    last = full[-1] if full else {}
    cov = [r["coverage_pct"] for r in full if r.get("coverage_pct") is not None]
    recent = full[-20:]
    recent_deps = deps[-10:]
    tok_recent = toks[-10:]
    cached = sum(r.get("cache_read_input_tokens", 0) for r in tok_recent)
    inp = cached + sum(r.get("input_tokens", 0) + r.get("cache_creation_input_tokens", 0) for r in tok_recent)
    return {
        "test_seconds": last.get("seconds"), "test_budget": b.get("test_seconds"),
        "test_ok": last.get("ok"),
        "pass_rate": round(100.0 * sum(r["ok"] for r in recent) / len(recent)) if recent else None,
        "coverage": cov[-1] if cov else None, "coverage_min": b.get("min_coverage_pct"),
        "deploys": len(deps),
        "deploy_fail_rate": round(100.0 * sum(not r["ok"] for r in recent_deps) / len(recent_deps)) if recent_deps else None,
        "deploy_seconds": deps[-1]["seconds"] if deps else None, "deploy_budget": b.get("deploy_seconds"),
        "last_deploy": deps[-1] if deps else None, "recent_deploys": list(reversed(deps[-6:])),
        "tokens_avg": round(sum(metrics.wt(r) for r in tok_recent) / len(tok_recent)) if tok_recent else None,
        "tokens_warn": b.get("session_weighted_tokens_warn"),
        "cache_hit": round(100.0 * cached / inp) if inp else None,
        "series": {"test_seconds": [r["seconds"] for r in full[-30:]], "coverage": cov[-30:],
                   "tokens": [metrics.wt(r) for r in toks[-30:]]},
        "alerts": alerts, "suggestions": ideas,
    }


# ---------------------------------------------------------------- delivery (CI, deploys, releases)

def to_time(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def week_of(day):
    y, w, _ = day.isocalendar()
    return "%d-W%02d" % (y, w)


def last_weeks(today, n=8):
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


def parse_ci_runs(text):
    """The runs list from metrics/ci-runs.json text (scripts/ci_runs.py), or None."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    runs = data.get("runs") if isinstance(data, dict) else data
    return runs if isinstance(runs, list) else None


def ci_metrics(runs, today, main_branch="main"):
    """Pass rates, durations, last failures and runs per week. Skipped and cancelled runs do not count."""
    if not runs:
        return None
    runs = sorted((r for r in runs if isinstance(r, dict)), key=lambda r: r.get("created_at") or "", reverse=True)
    decided = [r for r in runs if r.get("conclusion") in ("success", "failure")]
    last30 = decided[:30]
    main30 = [r for r in decided if r.get("head_branch") == main_branch][:30]
    mins = []
    for r in decided[:100]:
        a, b = to_time(r.get("run_started_at") or r.get("created_at")), to_time(r.get("updated_at"))
        if a and b and b >= a:
            mins.append((b - a).total_seconds() / 60)
    fail = next((r for r in runs if r.get("conclusion") == "failure"), None)
    main_fail = next((r for r in runs if r.get("conclusion") == "failure" and r.get("head_branch") == main_branch), None)
    weeks = last_weeks(today)
    per = {w: {"runs": 0, "ok": 0, "decided": 0} for w in weeks}
    for r in runs:
        t = to_time(r.get("created_at"))
        w = week_of(t.date()) if t else None
        if w in per:
            per[w]["runs"] += 1
            if r.get("conclusion") in ("success", "failure"):
                per[w]["decided"] += 1
                per[w]["ok"] += r.get("conclusion") == "success"

    def short(r):
        return None if r is None else {"date": (r.get("created_at") or "")[:10], "branch": r.get("head_branch") or "",
                                       "url": r.get("html_url") or ""}
    return {
        "runs": len(runs), "main_branch": main_branch,
        "pass_rate_30": pct(sum(r["conclusion"] == "success" for r in last30), len(last30)),
        "decided_30": len(last30),
        "main_pass_rate": pct(sum(r["conclusion"] == "success" for r in main30), len(main30)),
        "main_decided": len(main30),
        "median_min": round(median(mins), 1) if mins else None,
        "p90_min": round(p90(mins), 1) if mins else None,
        "last_failure": short(fail), "last_main_failure": short(main_fail),
        "weeks": weeks,
        "runs_per_week": [per[w]["runs"] for w in weeks],
        "pass_per_week": [pct(per[w]["ok"], per[w]["decided"]) for w in weeks],
    }


def deploy_metrics(dates, today, source=""):
    """Deploys per week from a list of YYYY-MM-DD dates."""
    if dates is None:
        return None
    days = []
    for s in dates:
        try:
            days.append(datetime.date.fromisoformat(str(s).strip()[:10]))
        except ValueError:
            pass
    weeks = last_weeks(today)
    return {"total": len(days), "last": max(days).isoformat() if days else None, "source": source,
            "weeks": weeks, "per_week": [sum(1 for d in days if week_of(d) == w) for w in weeks]}


def deploy_dates(f, hist):
    """Deploy dates: recorded deploys (metrics.py deploy) win; else, for git deploys, the first-parent
    commits on origin/<production_branch> since dashboard.deploys_since (each merge deploys)."""
    recorded = [r["ts"][:10] for r in hist if r.get("kind") == "deploy" and r.get("ts")]
    if recorded:
        return recorded, "metrics/history.jsonl"
    dep = f.get("integrations", {}).get("deploy", {})
    if dep.get("method") != "git" or not any(dep.get(k) for k in ("project_name", "worker_name", "production_url")):
        return None, ""  # git deploys not configured yet
    ref = "origin/" + (dep.get("production_branch") or "main")
    if not git("rev-parse", "--verify", "--quiet", ref):
        return None, ""
    since = cfg(f)["deploys_since"]
    out = git("log", "--first-parent", ref, "--date=short", "--format=%ad")
    return [d for d in out.splitlines() if d and d >= since], "first-parent commits on " + ref


CHANGELOG_RE = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?\s*(?:\(|[-–—]\s*)?(\d{4}-\d{2}-\d{2})?", re.M)


def parse_changelog(text):
    """Latest version, its date and the bullet count under Unreleased. Accepts `## 1.2.0 (2026-01-02)` and
    Keep a Changelog `## [1.2.0] - 2026-01-02`."""
    res = {"latest": "", "latest_date": "", "unreleased": None, "releases": []}
    if not text:
        return res
    for m in CHANGELOG_RE.finditer(text):
        res["releases"].append({"version": m.group(1), "date": m.group(2) or ""})
    if res["releases"]:
        res["latest"], res["latest_date"] = res["releases"][0]["version"], res["releases"][0]["date"]
    lines = section_lines(text, ("unreleased", "[unreleased]"))
    if lines or re.search(r"(?im)^##\s+\[?unreleased\]?\s*$", text):
        res["unreleased"] = sum(1 for l in lines if re.match(r"^\s*[*-] ", l))
    return res


def release_metrics(releases, today):
    """Count, median gap and days since the last release, from [{version, date}] (CHANGELOG or tags)."""
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
    return {"count": len(rel), "versions": [{"version": v, "date": d.isoformat()} for v, d in rel],
            "median_gap_days": (int(gap) if gap == int(gap) else gap) if gaps else None,
            "days_since_last": (today - rel[-1][1]).days, "last": rel[-1][0]}


def tag_releases():
    """Release-looking git tags (v1.2.3 or 1.2.3) with their dates."""
    out = git("for-each-ref", "refs/tags", "--format=%(refname:short)|%(creatordate:short)")
    rows = []
    for line in out.splitlines():
        name, _, date = line.partition("|")
        if re.fullmatch(r"v?\d+\.\d+(\.\d+)?", name):
            rows.append({"version": name, "date": date})
    return rows


# ---------------------------------------------------------------- roadmap

def cfg(f):
    c = dict(DASHBOARD_DEFAULTS)
    c.update({k: v for k, v in (f.get("dashboard") or {}).items() if not k.startswith("$") and v not in ("", None)})
    return c


def lane_of(tags, rid="", note="", conf=None):
    """'value' or 'foundation'. Rules in order: #value/#feature tag, foundation tag, lane_overrides
    (by release id or title), refactor id pattern or 'refactor' in the note, else value."""
    conf = conf or DASHBOARD_DEFAULTS
    tags = {t.lower() for t in tags or []}
    if tags & {"value", "feature"}:
        return "value"
    if tags & (FOUNDATION_TAGS | {t.lower() for t in conf.get("foundation_tags") or []}):
        return "foundation"
    over = conf.get("lane_overrides") or {}
    if rid in over and over[rid] in ("value", "foundation"):
        return over[rid]
    pat = conf.get("refactor_id_pattern")
    if rid and ((pat and re.fullmatch(pat, rid)) or "refactor" in (note or "").lower()):
        return "foundation"
    return "value"


def release_tasks(row, plan):
    """Plan tasks of a release: rows with its id as milestone, plus ids named in its tasks cell
    (T55 also finds T55a and T55b)."""
    named = set(TASK_REF.findall(row.get("tasks", "")))
    out = []
    for t in plan:
        base = re.sub(r"[a-z]$", "", t["id"])
        if t["milestone"] == row.get("id") or t["id"] in named or base in named:
            out.append(t)
    return out


def roadmap(backlog, open_debt, releases=None, plan=None, conf=None):
    """Proposed sequence. Columns, left to right:
      1. a ranked release table (if any): Now (status next), Then (candidates), Later; rows keep rank order;
         open refactor rounds from the plan that no release claims join Now in the foundation lane;
      2. `## Milestone:` checklists in BACKLOG.md order, items in file order;
      3. open tech debt not yet scheduled, high impact first.
    Open cards are numbered per lane (1 = next up). Shipped and dropped releases are only counted."""
    conf = conf or DASHBOARD_DEFAULTS
    releases, plan = releases or [], plan or []
    groups, claimed = [], set()

    def rank(r):
        return (0, int(r["rank"])) if r["rank"].isdigit() else (1, 0)

    for chip, name, sub in ROADMAP_GROUPS:
        items = []
        for r in sorted((r for r in releases if r["chip"] == chip), key=rank):
            tasks = release_tasks(r, plan)
            claimed.update(t["id"] for t in tasks)
            items.append({"title": r["release"], "state": "doing" if chip == "next" else "todo", "size": r["size"],
                          "feel": r["feel"], "tasks": tasks, "lane": lane_of(r["tags"], r["id"], r["note"], conf)})
        if chip == "next" and conf.get("refactor_id_pattern"):
            rounds = {}
            for t in plan:
                if re.fullmatch(conf["refactor_id_pattern"], t["milestone"]) and t["id"] not in claimed:
                    rounds.setdefault(t["milestone"], []).append(t)
            for mid, tasks in rounds.items():
                if any(t["status"] != "done" for t in tasks):
                    items.append({"title": "%s refactor round" % mid, "state": "todo", "size": "",
                                  "tasks": tasks, "lane": "foundation"})
        groups.append((name, "", sub, items))
    for ms in backlog:
        groups.append((ms["name"], ms["target"], "", ms["items"]))
    debt_cards = [{"title": "%s %s" % (x["id"], x["title"]), "state": "todo", "size": x.get("effort", ""),
                   "lane": "foundation", "impact": x.get("impact", ""), "debt": True}
                  for x in sorted(open_debt, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("impact"), 3))]
    if debt_cards:
        groups.append(("Tech debt to schedule", "", "open items, high impact first", debt_cards))

    columns, seq = [], {"value": 0, "foundation": 0}
    for name, target, sub, items in groups:
        cards = {"value": [], "foundation": []}
        for it in items:
            if it["state"] == "dropped":
                continue
            lane = it.get("lane") or lane_of(it.get("tags", []), "", "", conf)
            if it["title"] in (conf.get("lane_overrides") or {}) and not it.get("debt"):
                lane = conf["lane_overrides"][it["title"]]
            card = {"title": it["title"], "state": it["state"], "size": it.get("size", ""),
                    "impact": it.get("impact", ""), "debt": it.get("debt", False), "feel": it.get("feel", ""),
                    "tasks": it.get("tasks", []), "seq": None}
            if it["state"] != "done":
                seq[lane] += 1
                card["seq"] = seq[lane]
            cards[lane].append(card)
        if cards["value"] or cards["foundation"]:
            columns.append({"name": name, "target": target, "sub": sub, "lanes": cards})
    return {"columns": columns, "open": dict(seq), "ranked": bool(releases),
            "shipped": sum(1 for r in releases if r["chip"] == "shipped")}


def collect():
    f = metrics.factory()
    conf = cfg(f)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    backlog_text = read("docs/BACKLOG.md")
    backlog = parse_backlog(backlog_text)
    releases = parse_releases(backlog_text)
    plan = parse_plan_tasks(read(conf["plan_file"]))
    items = [i for m in backlog for i in m["items"]]
    counts = {s: sum(i["state"] == s for i in items) for s in ("todo", "doing", "blocked", "done", "dropped")}
    debt = parse_debt(read("docs/TECH-DEBT.md"))
    open_debt = [d for d in debt if d["open"]]
    planned = [m for m in backlog if m["total"]]
    total = sum(m["total"] for m in planned)
    if total:
        progress = round(100.0 * sum(m["done"] for m in planned) / total)
    else:  # ranked release table only: shipped share of live releases
        live = [r for r in releases if r["chip"] != "dropped"]
        progress = round(100.0 * sum(r["chip"] == "shipped" for r in live) / len(live)) if live else 0
    next_up = [i["title"] for i in items if i["state"] == "todo"][:5] or \
        [r["release"] for r in releases if r["chip"] in ("next", "candidate")][:5]
    changelog = parse_changelog(read(conf["changelog_file"]))
    dated = [r for r in changelog["releases"] if r["date"]]
    hist = metrics.load(metrics.HISTORY)
    dates, dep_source = deploy_dates(f, hist)
    main_branch = f.get("integrations", {}).get("deploy", {}).get("production_branch") or "main"
    return {
        "generated": metrics.now(),
        "project": f.get("project", {}), "phase": f.get("phase", "brainstorm"), "paths": f.get("paths", {}),
        "template": f.get("template", {}), "deploy": f.get("integrations", {}).get("deploy", {}),
        "versions": versions(),
        "progress": {"milestones": backlog, "pct": progress},
        "backlog": {"counts": counts,
                    "doing": [i["title"] for i in items if i["state"] == "doing"][:8],
                    "blocked": [i["title"] for i in items if i["state"] == "blocked"][:8],
                    "next": next_up,
                    "releases": releases,
                    "next_release": next((r["release"] for r in releases if r["chip"] == "next"), "")},
        "debt": {"open": open_debt, "resolved": len(debt) - len(open_debt),
                 "by_impact": {k: sum(d["impact"] == k for d in open_debt) for k in ("high", "medium", "low")},
                 "signals": debt_signals(f)},
        "roadmap": roadmap(backlog, open_debt, releases, plan, conf),
        "decisions": collect_decisions(),
        "delivery": {
            "ci": ci_metrics(parse_ci_runs(read("metrics/ci-runs.json")), today, main_branch),
            "deploys": deploy_metrics(dates, today, dep_source),
            "changelog": changelog,
            "releases": release_metrics(dated or tag_releases(), today),
        },
        "metrics": metric_view(f),
    }


# ---------------------------------------------------------------- render

def e(x):
    return html.escape("" if x is None else str(x))


def fmt_num(v, suffix="", digits=0):
    if v is None:
        return "–"
    if isinstance(v, (int, float)) and abs(v) >= 10000:
        return "{:,.0f}{}".format(v, suffix)
    return ("{:.%df}{}" % digits).format(v, suffix)


def status(value, budget, higher_is_better=False):
    if value is None or budget is None:
        return "na"
    ok = value >= budget if higher_is_better else value <= budget
    return "ok" if ok else "bad"


def spark(values, label):
    if len(values) < 2:
        return '<span class="muted small">not enough data yet</span>'
    w, h, pad = 160, 36, 3
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(values):
        x = pad + i * (w - 2 * pad) / (len(values) - 1)
        y = h - pad - (v - lo) * (h - 2 * pad) / span
        pts.append("%.1f,%.1f" % (x, y))
    lx, ly = pts[-1].split(",")
    return ('<svg class="spark" viewBox="0 0 %d %d" role="img" aria-label="%s trend, last %d runs">'
            '<polyline points="%s"/><circle cx="%s" cy="%s" r="2.5"/></svg>'
            % (w, h, e(label), len(values), " ".join(pts), lx, ly))


def tile(label, value, sub, state="na", series=None, words=("on budget", "watch", "over budget")):
    badge = {"ok": words[0], "warn": words[1], "bad": words[2], "na": ""}[state]
    return ('<div class="tile %s"><div class="label">%s</div><div class="value">%s</div>'
            '<div class="sub">%s%s</div>%s</div>'
            % (state, e(label), e(value), e(sub),
               ' · <span class="badge">%s</span>' % badge if badge else "",
               series or ""))


def bar(pct, label):
    return ('<div class="bar" role="progressbar" aria-valuenow="%d" aria-valuemin="0" aria-valuemax="100" '
            'aria-label="%s"><span style="width:%d%%"></span></div>' % (pct, e(label), pct))


def f_codegraph():
    return bool(metrics.factory().get("integrations", {}).get("codegraph"))


def bars(values, weeks, title, unit=""):
    """Small inline SVG bar chart, one bar per week (no JS). None values draw as an empty stub."""
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
            % (e(title), fmt_num(last, unit) if isinstance(last, (int, float)) else "–", len(weeks) * 14, e(title),
               "".join(rects), e(weeks[0] if weeks else ""), e(weeks[-1] if weeks else "")))


def pass_state(v):
    return "na" if v is None else "ok" if v >= 90 else "warn" if v >= 70 else "bad"


def delivery_html(dl):
    ci, dep, rel, cl = dl["ci"], dl["deploys"], dl["releases"], dl["changelog"]
    g = lambda x, k: None if x is None else x.get(k)
    stale = rel is not None and rel["days_since_last"] > 14 and cl["unreleased"]
    tiles = "".join([
        tile("CI pass rate", fmt_num(g(ci, "pass_rate_30"), "%"), "last %s finished runs" % (g(ci, "decided_30") or 0),
             pass_state(g(ci, "pass_rate_30")), words=("healthy", "watch", "failing often")),
        tile("Pass rate on %s" % (g(ci, "main_branch") or "main"), fmt_num(g(ci, "main_pass_rate"), "%"),
             "last %s runs" % (g(ci, "main_decided") or 0), pass_state(g(ci, "main_pass_rate")),
             words=("healthy", "watch", "red too often")),
        tile("CI time", fmt_num(g(ci, "median_min"), " min", 1), "median · p90 %s" % fmt_num(g(ci, "p90_min"), " min", 1)),
        tile("Deploys", fmt_num(g(dep, "total")), "last %s" % (g(dep, "last") or "–")),
        tile("Releases", fmt_num(g(rel, "count")), "median %s days apart" % fmt_num(g(rel, "median_gap_days"))),
        tile("Since last release", "%s days" % rel["days_since_last"] if rel else "–",
             "%s unreleased changes" % (cl["unreleased"] if cl["unreleased"] is not None else "–"),
             "warn" if stale else "na", words=("", "release soon", "")),
    ])
    charts = []
    if ci:
        charts.append(bars(ci["runs_per_week"], ci["weeks"], "CI runs"))
        charts.append(bars(ci["pass_per_week"], ci["weeks"], "CI pass rate", "%"))
    if dep:
        charts.append(bars(dep["per_week"], dep["weeks"], "Deploys"))
    lines = []
    if ci is None:
        lines.append(e("No CI history yet. Run python3 scripts/ci_runs.py (CI does it on every build) "
                       "to write metrics/ci-runs.json."))
    else:
        for label, fl in (("Last failure", ci["last_failure"]), ("Last failure on " + ci["main_branch"], ci["last_main_failure"])):
            lines.append("%s: %s" % (e(label), "none" if fl is None else '%s on <span class="mono">%s</span>%s' % (
                e(fl["date"]), e(fl["branch"]), ' · <a href="%s">run</a>' % e(fl["url"]) if fl["url"] else "")))
    lines.append(e("Deploys: " + (dep["source"] if dep else "none recorded (metrics.py deploy, or set up git deploys)")))
    lines.append(e("Skipped and cancelled CI runs do not count toward pass rates."))
    return ('<div class="tiles mini">%s</div>%s<ul class="plain small-list">%s</ul>' % (
        tiles, '<div class="charts">%s</div>' % "".join(charts) if charts else "",
        "".join("<li>%s</li>" % l for l in lines)))


def render_roadmap(rm):
    cols = rm["columns"]
    if not cols:
        return ('<div class="card"><p class="muted">No roadmap yet. Add milestones and items to docs/BACKLOG.md '
                '(or a Ranked backlog table with status next, candidate or later); tag foundation work with '
                '#foundation (or #arch, #infra, #runway, #debt, #quality...).</p></div>')

    def task(t):
        return '<span class="chip id t-%s" title="%s">%s</span>' % (e(t["status"]), e(t["status"]), e(t["id"]))

    def card(c):
        badges = "".join([
            '<span class="imp %s">%s</span>' % (e(c["impact"]), e(c["impact"])) if c["impact"] else "",
            '<span class="size">%s</span>' % e(c["size"]) if c["size"] else "",
            '<span class="state">%s</span>' % e(c["state"]) if c["state"] in ("doing", "blocked") else ""])
        num = '<span class="seq">%d</span>' % c["seq"] if c["seq"] else '<span class="seq">&#10003;</span>'
        feel = '<br><span class="muted small">%s</span>' % e(c["feel"]) if c.get("feel") else ""
        tasks = '<div class="rm-tasks">%s</div>' % "".join(task(t) for t in c["tasks"]) if c.get("tasks") else ""
        return '<li class="rm-card %s">%s<span class="t">%s%s</span>%s%s</li>' % (
            e(c["state"]), num, e(c["title"]), feel, '<span class="b">%s</span>' % badges if badges else "", tasks)

    head = "".join('<div class="rm-col-h"><b>%s</b>%s</div>' % (
        e(c["name"]), '<span class="muted small">target %s</span>' % e(c["target"]) if c["target"]
        else '<span class="muted small">%s</span>' % e(c["sub"]) if c.get("sub") else "")
        for c in cols)
    rows = ""
    for key, label, sub in LANES:
        rows += '<div class="rm-lane-h %s"><b>%s</b><span class="muted small">%s · %d open</span></div>' % (
            key, e(label), e(sub), rm["open"][key])
        rows += "".join('<ul class="rm-cell %s">%s</ul>' % (
            key, "".join(card(x) for x in c["lanes"][key]) or '<li class="muted small">–</li>') for c in cols)
    ranked = (' The Ranked backlog table gives Now (status next), Then (candidate) and Later in rank order; '
              'task chips come from the plan file (green is done). %d releases shipped, not shown.' % rm.get("shipped", 0)
              if rm.get("ranked") else "")
    return ('<div class="card"><h2>Roadmap: proposed sequence</h2>'
            '<p class="muted small">Columns follow docs/BACKLOG.md; numbers are the suggested order within each lane.%s '
            'Lanes come from tags (#foundation, #value...) and factory.json dashboard.lane_overrides; open items in '
            'docs/TECH-DEBT.md land in the foundation lane.</p>'
            '<div class="scroll"><div class="rm" style="--cols:%d">'
            '<div class="rm-corner"></div>%s%s</div></div></div>' % (ranked, len(cols), head, rows))


def render(d):
    m, v, bl, debt = d["metrics"], d["versions"], d["backlog"], d["debt"]
    dec = d.get("decisions") or {"total": 0, "open": []}
    name = d["project"].get("name") or "Untitled project"
    phase_i = PHASES.index(d["phase"]) if d["phase"] in PHASES else len(PHASES) - 1
    steps = "".join('<li class="%s">%s</li>' % ("done" if i < phase_i else "now" if i == phase_i else "", e(p))
                    for i, p in enumerate(PHASES))
    chips = "".join('<span class="chip">%s</span>' % e(p) for p in
                    [d["paths"].get("primary")] + list(d["paths"].get("secondary") or []) if p)

    tiles = "".join([
        tile("Progress", "%d%%" % d["progress"]["pct"], "%d done · %d open" % (
            bl["counts"]["done"], bl["counts"]["todo"] + bl["counts"]["doing"] + bl["counts"]["blocked"])),
        tile("Full test run", fmt_num(m["test_seconds"], "s", 1), "budget %ss" % e(m["test_budget"]),
             status(m["test_seconds"], m["test_budget"]), spark(m["series"]["test_seconds"], "Test time")),
        tile("Coverage", fmt_num(m["coverage"], "%", 1), "min %s%%" % e(m["coverage_min"]),
             status(m["coverage"], m["coverage_min"], True), spark(m["series"]["coverage"], "Coverage")),
        tile("Test pass rate", fmt_num(m["pass_rate"], "%"), "last 20 runs",
             "na" if m["pass_rate"] is None else ("ok" if m["pass_rate"] >= 95 else "warn"),
             words=("healthy", "check flaky tests", "failing")),
        tile("Deploys", fmt_num(m["deploys"]), "failure rate %s (last 10)" % fmt_num(m["deploy_fail_rate"], "%"),
             "na" if m["deploy_fail_rate"] is None else ("ok" if m["deploy_fail_rate"] <= 20 else "bad"),
             words=("healthy", "watch", "unstable")),
        tile("Cost / session", fmt_num(m["tokens_avg"]), "weighted tokens · cache hit %s" % fmt_num(m["cache_hit"], "%"),
             status(m["tokens_avg"], m["tokens_warn"]), spark(m["series"]["tokens"], "Tokens per session")),
        tile("Open tech debt", str(len(debt["open"])), "%d high impact · %d markers" % (
            debt["by_impact"]["high"], debt["signals"]["marker_total"]),
             "bad" if debt["by_impact"]["high"] else ("warn" if debt["open"] else "ok"),
             words=("clear", "manageable", "high impact open")),
        tile("Open decisions", str(len(dec["open"])), "proposed ADRs in docs/decisions",
             "warn" if dec["open"] else "ok", words=("none waiting", "need an answer", "")),
    ])

    ms_rows = "".join(
        '<li><div class="row"><span class="name">%s</span><span class="muted small">%s%d/%d</span></div>%s</li>'
        % (e(ms["name"]), ("target %s · " % e(ms["target"])) if ms["target"] else "", ms["done"], ms["total"],
           bar(ms["pct"], ms["name"]))
        for ms in d["progress"]["milestones"] if ms["total"]) or '<li class="muted">No milestones yet. Add them in docs/BACKLOG.md.</li>'

    def lst(items, empty):
        return "".join("<li>%s</li>" % e(i) for i in items) or '<li class="muted">%s</li>' % e(empty)

    c = bl["counts"]
    backlog = ('<div class="counts">%s</div>' % "".join(
        '<div class="count %s"><b>%d</b><span>%s</span></div>' % (k, c[k], k) for k in ("todo", "doing", "blocked", "done"))
        + '<h3>In progress</h3><ul class="plain">%s</ul>' % lst(bl["doing"], "nothing in progress")
        + '<h3>Blocked</h3><ul class="plain">%s</ul>' % lst(bl["blocked"], "nothing blocked")
        + '<h3>Up next</h3><ul class="plain">%s</ul>' % lst(bl["next"], "backlog empty"))

    sig = debt["signals"]
    debt_rows = "".join('<tr><td data-l="ID" class="mono">%s</td><td data-l="Item">%s</td><td data-l="Impact"><span class="imp %s">%s</span></td>'
                        '<td data-l="Effort">%s</td><td data-l="Area">%s</td></tr>'
                        % (e(x["id"]), e(x["title"]), e(x["impact"] or "na"), e(x["impact"] or "–"), e(x["effort"] or "–"),
                           e(x["area"] or "–")) for x in sorted(
                               debt["open"], key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["impact"], 3)))
    debt_html = (('<div class="scroll"><table class="stack"><thead><tr><th>ID</th><th>Item</th><th>Impact</th><th>Effort</th><th>Area</th></tr></thead>'
                  '<tbody>%s</tbody></table></div>' % debt_rows) if debt_rows
                 else '<p class="muted">No open items in docs/TECH-DEBT.md.</p>')
    markers = ", ".join("%s %d" % (k, n) for k, n in sorted(sig["markers"].items())) or "none"
    debt_html += ('<h3>Automated signals</h3><ul class="plain"><li>Code markers: %s</li>'
                  '<li>Files over %d lines: %s</li><li>Import cycles: %s</li><li>Resolved items: %d</li></ul>'
                  % (e(markers), LARGE_FILE_LINES,
                     e(", ".join("%s (%d)" % (x["file"], x["lines"]) for x in sig["large_files"][:5]) or "none"),
                     e(sig["import_cycles"] if sig["import_cycles"] is not None else
                       "n/a (needs codegraph with the `cycles` command)" if f_codegraph() else "enable codegraph to track"),
                     debt["resolved"]))

    tag_rows = "".join("<tr><td class=\"mono\">%s</td><td>%s</td></tr>" % (e(t["tag"]), e(t["date"])) for t in v["tags"]) \
        or '<tr><td colspan="2" class="muted">No release tags yet (git tag v0.1.0).</td></tr>'
    dep_rows = "".join('<tr><td class="nowrap">%s</td><td>%s</td><td class="mono">%s</td><td>%s</td><td>%s</td></tr>'
                       % (e(r["ts"][5:16].replace("T", " ")), e(r.get("env")), e(r.get("sha") or "–"),
                          '<span class="imp %s">%s</span>' % ("low" if r["ok"] else "high", "ok" if r["ok"] else "failed"),
                          fmt_num(r.get("seconds"), "s")) for r in m["recent_deploys"]) \
        or '<tr><td colspan="5" class="muted">No deploys recorded (python3 scripts/metrics.py deploy).</td></tr>'
    commits = "".join('<li><span class="mono">%s</span> <span class="muted small">%s</span> %s</li>'
                      % (e(x["sha"]), e(x["date"]), e(x["subject"])) for x in v["commits"])
    alerts = "".join('<li class="alert">%s</li>' % e(a) for a in m["alerts"]) or '<li class="muted">No alerts.</li>'
    ideas = "".join("<li>%s</li>" % e(i) for i in m["suggestions"][:6]) or '<li class="muted">No suggestions.</li>'
    rel_rows = "".join(
        '<tr><td data-l="Release"><b>%s</b>%s</td><td data-l="Summary">%s</td><td data-l="Size">%s</td>'
        '<td data-l="Status"><span class="chip st-%s">%s</span></td></tr>'
        % (e(r["release"]), ' <span class="muted small">%s</span>' % e(r["note"]) if r["note"] else "",
           e(r["feel"] or "–"), e(r["size"] or "–"), e(r["chip"]), e(r["status"] or r["chip"]))
        for r in bl.get("releases") or [])
    releases = ('<div class="card wide"><h2>Ranked backlog</h2><table class="stack"><thead><tr><th>Release</th>'
                '<th>Summary</th><th>Size</th><th>Status</th></tr></thead><tbody>%s</tbody></table></div>' % rel_rows
                if rel_rows else "")
    decisions = ('<div class="card"><h2>Open decisions</h2><ul class="plain">%s</ul></div>' % "".join(
        '<li class="alert"><span class="mono">%s</span> %s</li>' % (e(x["file"][:4]), e(x["title"])) for x in dec["open"])
        if dec["open"] else "")
    dl = d.get("delivery")
    delivery = '<div class="card wide"><h2>Delivery</h2>%s</div>' % delivery_html(dl) if dl else ""
    prod = d["deploy"].get("production_url")
    live = ' · <a href="%s">%s</a>' % (e(prod), e(prod)) if prod else ""

    return TEMPLATE.format(
        title=e(name + " status"), name=e(name), one_liner=e(d["project"].get("one_liner") or ""),
        steps=steps, chips=chips or '<span class="chip muted">path not chosen</span>',
        version=e(v["current"]), sha=e(v["sha"] or "no commits"), branch=e(v["branch"]), live=live,
        generated=e(d["generated"].replace("T", " ").replace("+00:00", " UTC")),
        tree=e(d["template"].get("decision_tree_version", "")), tiles=tiles, milestones=ms_rows,
        backlog=backlog, debt=debt_html, tags=tag_rows, deploys=dep_rows,
        commits=commits or '<li class="muted">No commits yet.</li>', alerts=alerts, ideas=ideas,
        commit_count=v["commit_count"], roadmap=render_roadmap(d["roadmap"]),
        releases=releases, decisions=decisions, delivery=delivery)


def summary(d):
    m, bl, debt = d["metrics"], d["backlog"]["counts"], d["debt"]
    lines = [
        "## %s — dashboard" % (d["project"].get("name") or "project"),
        "",
        "| | |", "|---|---|",
        "| Phase / path | %s / %s |" % (d["phase"], d["paths"].get("primary") or "–"),
        "| Version | %s (%s) |" % (d["versions"]["current"], d["versions"]["sha"] or "–"),
        "| Progress | %d%% — %d done, %d doing, %d blocked, %d todo |" % (
            d["progress"]["pct"], bl["done"], bl["doing"], bl["blocked"], bl["todo"]),
        "| Tests | %s (budget %ss), pass rate %s |" % (fmt_num(m["test_seconds"], "s", 1), m["test_budget"],
                                                     fmt_num(m["pass_rate"], "%")),
        "| Coverage | %s (min %s%%) |" % (fmt_num(m["coverage"], "%", 1), m["coverage_min"]),
        "| Deploys | %s, failure rate %s |" % (m["deploys"], fmt_num(m["deploy_fail_rate"], "%")),
        "| Weighted tokens / session | %s, cache hit %s |" % (fmt_num(m["tokens_avg"]), fmt_num(m["cache_hit"], "%")),
        "| Tech debt | %d open (%d high), %d code markers |" % (
            len(debt["open"]), debt["by_impact"]["high"], debt["signals"]["marker_total"]),
    ]
    if d["backlog"].get("next_release"):
        lines.insert(7, "| Next release | %s |" % d["backlog"]["next_release"].replace("|", "/"))
    dl = d.get("delivery") or {}
    ci, rel, cl = dl.get("ci"), dl.get("releases"), dl.get("changelog") or {}
    if ci:
        lines.append("| CI | %s pass (last %d), %s %s, median %s |" % (
            fmt_num(ci["pass_rate_30"], "%"), ci["decided_30"], ci["main_branch"], fmt_num(ci["main_pass_rate"], "%"),
            fmt_num(ci["median_min"], " min", 1)))
    if rel:
        lines.append("| Releases | %d, last %s %d days ago, %s unreleased changes |" % (
            rel["count"], rel["last"], rel["days_since_last"],
            cl.get("unreleased") if cl.get("unreleased") is not None else "–"))
    dec = d.get("decisions") or {}
    if dec.get("open"):
        lines.append("| Open decisions | %d proposed ADRs |" % len(dec["open"]))
    if m["alerts"]:
        lines += ["", "**Alerts**", ""] + ["- " + a for a in m["alerts"]]
    return "\n".join(lines) + "\n"


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --bg:#f6f7f9; --surface:#ffffff; --text:#1b1f24; --muted:#5b6470; --border:#dfe3e8;
  --accent:#2f6fdb; --ok:#1f8a4c; --ok-bg:#e6f4ec; --bad:#c23934; --bad-bg:#fbeaea;
  --warn:#9a6700; --warn-bg:#fff4d6; --track:#e9edf2;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#0f1216; --surface:#171b21; --text:#e6e9ed; --muted:#9aa4b1; --border:#2a313a;
    --accent:#6ea0ff; --ok:#4cc38a; --ok-bg:#12291d; --bad:#ff7b72; --bad-bg:#2d1517;
    --warn:#e3b341; --warn-bg:#2b230f; --track:#262d36;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#0f1216; --surface:#171b21; --text:#e6e9ed; --muted:#9aa4b1; --border:#2a313a;
  --accent:#6ea0ff; --ok:#4cc38a; --ok-bg:#12291d; --bad:#ff7b72; --bad-bg:#2d1517;
  --warn:#e3b341; --warn-bg:#2b230f; --track:#262d36;
}}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; background:var(--bg); color:var(--text); }}
body {{ font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; overflow-wrap:anywhere; }}
main {{ max-width:1180px; margin:0 auto; padding:24px 16px 48px; }}
header {{ display:flex; flex-wrap:wrap; gap:12px 24px; align-items:flex-end; justify-content:space-between; margin-bottom:20px; }}
h1 {{ font-size:24px; margin:0; letter-spacing:-.01em; }}
h2 {{ font-size:15px; margin:0 0 12px; }}
h3 {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:16px 0 6px; }}
.muted {{ color:var(--muted); }} .small {{ font-size:12px; }}
.mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }}
a {{ color:var(--accent); }}
.meta {{ color:var(--muted); font-size:13px; text-align:right; }}
.steps {{ display:flex; gap:6px; list-style:none; padding:0; margin:10px 0 0; flex-wrap:wrap; }}
.steps li {{ font-size:12px; padding:3px 10px; border-radius:999px; border:1px solid var(--border); color:var(--muted); }}
.steps li.done {{ color:var(--ok); border-color:var(--ok); }}
.steps li.now {{ background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }}
.chip {{ display:inline-block; font-size:12px; padding:2px 8px; border-radius:6px; background:var(--track); margin:6px 6px 0 0; white-space:nowrap; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }}
.tile {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; border-top:3px solid var(--border); }}
.tile.ok {{ border-top-color:var(--ok); }} .tile.bad {{ border-top-color:var(--bad); }} .tile.warn {{ border-top-color:var(--warn); }}
.tile .label {{ font-size:12px; color:var(--muted); }}
.tile .value {{ font-size:24px; font-weight:650; font-variant-numeric:tabular-nums; margin:2px 0; }}
.tile .sub {{ font-size:12px; color:var(--muted); }}
.tile.ok .badge {{ color:var(--ok); }} .tile.bad .badge {{ color:var(--bad); font-weight:600; }} .tile.warn .badge {{ color:var(--warn); }}
.spark {{ width:100%; height:36px; margin-top:8px; display:block; }}
.spark polyline {{ fill:none; stroke:var(--accent); stroke-width:1.75; vector-effect:non-scaling-stroke; }}
.spark circle {{ fill:var(--accent); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px; min-width:0; }}
.card.wide {{ grid-column:1 / -1; }}
.tiles.mini {{ grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); }}
.tiles.mini .tile {{ background:var(--bg); }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:12px; }}
.bars {{ margin:0; min-width:0; }}
.bars figcaption {{ font-size:13px; margin-bottom:6px; }}
.bars svg {{ width:100%; height:48px; display:block; }}
.bars rect {{ fill:var(--accent); }} .bars rect.zero {{ fill:var(--border); }}
.bars .axis {{ display:flex; justify-content:space-between; font-size:11px; color:var(--muted); margin-top:2px; }}
ul.small-list li {{ font-size:13px; }}
.chip.st-shipped {{ background:var(--ok-bg); color:var(--ok); }}
.chip.st-next {{ background:var(--track); color:var(--accent); font-weight:600; }}
.chip.st-candidate {{ background:var(--warn-bg); color:var(--warn); }}
.chip.st-dropped {{ text-decoration:line-through; color:var(--muted); }}
.chip.id {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; border-radius:6px; margin:0; }}
ul.plain, ul.ms {{ list-style:none; padding:0; margin:0; }}
ul.plain li {{ padding:4px 0; border-bottom:1px solid var(--border); font-size:14px; }}
ul.plain li:last-child {{ border-bottom:0; }}
ul.ms li {{ margin-bottom:12px; }}
.row {{ display:flex; justify-content:space-between; gap:8px; font-size:14px; }}
.bar {{ height:8px; background:var(--track); border-radius:999px; overflow:hidden; margin-top:4px; }}
.bar span {{ display:block; height:100%; background:var(--ok); border-radius:999px; }}
.counts {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }}
.count {{ background:var(--track); border-radius:8px; padding:8px; text-align:center; }}
.count b {{ display:block; font-size:20px; font-variant-numeric:tabular-nums; }}
.count span {{ font-size:12px; color:var(--muted); }}
.count.blocked b {{ color:var(--bad); }} .count.doing b {{ color:var(--accent); }} .count.done b {{ color:var(--ok); }}
.scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; font-size:12px; color:var(--muted); font-weight:600; padding:6px 8px; border-bottom:1px solid var(--border); }}
td.mono, td.nowrap {{ white-space:nowrap; }}
td {{ padding:6px 8px; border-bottom:1px solid var(--border); vertical-align:top; }}
.imp {{ font-size:12px; padding:1px 7px; border-radius:999px; background:var(--track); }}
.imp.high {{ background:var(--bad-bg); color:var(--bad); }} .imp.medium {{ background:var(--warn-bg); color:var(--warn); }}
.imp.low {{ background:var(--ok-bg); color:var(--ok); }}
li.alert {{ color:var(--bad); }}
footer {{ margin-top:24px; font-size:12px; color:var(--muted); }}
.tabs {{ display:flex; gap:4px; border-bottom:1px solid var(--border); margin-bottom:16px; }}
.tabs label {{ padding:8px 14px; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent; margin-bottom:-1px; font-weight:600; font-size:14px; }}
.tab-input {{ position:absolute; opacity:0; pointer-events:none; }}
.panel {{ display:none; }}
#tab-overview:checked ~ .panel-overview, #tab-roadmap:checked ~ .panel-roadmap {{ display:block; }}
#tab-overview:checked ~ .tabs label[for="tab-overview"], #tab-roadmap:checked ~ .tabs label[for="tab-roadmap"] {{ color:var(--text); border-bottom-color:var(--accent); }}
#tab-overview:focus-visible ~ .tabs label[for="tab-overview"], #tab-roadmap:focus-visible ~ .tabs label[for="tab-roadmap"] {{ outline:2px solid var(--accent); outline-offset:2px; }}
.rm {{ --lane-w:minmax(150px,180px); --col-w:240px; display:grid; gap:8px; min-width:max-content;
  grid-template-columns:var(--lane-w) repeat(var(--cols),var(--col-w)); }}
.rm-col-h {{ display:flex; flex-direction:column; font-size:14px; padding:4px 2px; border-bottom:2px solid var(--border); }}
.rm-lane-h {{ display:flex; flex-direction:column; justify-content:flex-start; font-size:14px; padding:10px; border-radius:8px; border-left:4px solid var(--accent); background:var(--track);
  position:sticky; left:0; z-index:1; box-shadow:8px 0 0 var(--surface); }}
.rm-lane-h.foundation {{ border-left-color:var(--warn); }}
.rm-cell {{ list-style:none; margin:0; padding:8px; border-radius:8px; background:var(--bg); border:1px dashed var(--border); display:flex; flex-direction:column; gap:6px; }}
.rm-card {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:6px; background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:6px; padding:6px 8px; font-size:13px; }}
.rm-cell.foundation .rm-card {{ border-left-color:var(--warn); }}
.rm-card .t {{ flex:1 1 120px; }}
.rm-card .b {{ display:flex; gap:4px; }}
.rm-card .seq {{ font-variant-numeric:tabular-nums; font-weight:650; color:var(--muted); min-width:1.4em; }}
.rm-card .size, .rm-card .state {{ font-size:11px; padding:0 6px; border-radius:999px; background:var(--track); color:var(--muted); }}
.rm-card.doing {{ box-shadow:inset 0 0 0 1px var(--accent); }} .rm-card.doing .state {{ color:var(--accent); }}
.rm-card.blocked .state {{ background:var(--bad-bg); color:var(--bad); }}
.rm-card.done {{ opacity:.55; }} .rm-card.done .t {{ text-decoration:line-through; }} .rm-card.done .seq {{ color:var(--ok); }}
.rm-tasks {{ flex-basis:100%; display:flex; flex-wrap:wrap; gap:4px; }}
.rm-tasks .chip {{ font-size:11px; padding:1px 6px; }}
.chip.t-done {{ background:var(--ok-bg); color:var(--ok); }}
.chip.t-doing {{ background:var(--track); color:var(--accent); }}
.chip.t-blocked {{ background:var(--bad-bg); color:var(--bad); }}
@media (max-width:720px) {{
  .rm {{ --lane-w:104px; --col-w:210px; }} .rm-lane-h {{ padding:8px; }}
  .meta {{ text-align:left; }} .grid {{ grid-template-columns:1fr; }}
  .tiles {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  table.stack thead {{ display:none; }}
  table.stack, table.stack tbody, table.stack tr, table.stack td {{ display:block; width:100%; }}
  table.stack tr {{ border-bottom:1px solid var(--border); padding:8px 0; }}
  table.stack td {{ border:0; padding:2px 0; white-space:normal; }}
  table.stack td[data-l]::before {{ content:attr(data-l) ": "; color:var(--muted); font-size:12px; }}
  table.stack td:first-child::before {{ content:none; }}
}}
</style>
</head>
<body>
<main>
<header>
  <div>
    <h1>{name}</h1>
    <div class="muted">{one_liner}</div>
    <ol class="steps" aria-label="Project phase">{steps}</ol>
    <div>{chips}</div>
  </div>
  <div class="meta">
    <div>Version <b class="mono">{version}</b> · <span class="mono">{branch}@{sha}</span>{live}</div>
    <div>{commit_count} commits · decision tree v{tree}</div>
    <div>Generated {generated}</div>
  </div>
</header>

<input type="radio" name="tab" id="tab-overview" class="tab-input" checked>
<input type="radio" name="tab" id="tab-roadmap" class="tab-input">
<nav class="tabs" aria-label="Dashboard views"><label for="tab-overview">Overview</label><label for="tab-roadmap">Roadmap</label></nav>

<div class="panel panel-roadmap">{roadmap}</div>

<div class="panel panel-overview">
<section class="tiles" aria-label="Key metrics">{tiles}</section>

<section class="grid">
  {releases}
  <div class="card"><h2>Progress by milestone</h2><ul class="ms">{milestones}</ul></div>
  <div class="card"><h2>Backlog</h2>{backlog}</div>
  {decisions}
  {delivery}
  <div class="card"><h2>Tech debt</h2>{debt}</div>
  <div class="card"><h2>Alerts and suggestions</h2>
    <ul class="plain">{alerts}</ul><h3>Suggested improvements</h3><ul class="plain">{ideas}</ul></div>
  <div class="card"><h2>Versions</h2><div class="scroll"><table><thead><tr><th>Tag</th><th>Date</th></tr></thead><tbody>{tags}</tbody></table></div>
    <h3>Recent deploys</h3><div class="scroll"><table><thead><tr><th>When (UTC)</th><th>Env</th><th>Commit</th><th>Result</th><th>Time</th></tr></thead><tbody>{deploys}</tbody></table></div></div>
  <div class="card"><h2>Recent commits</h2><ul class="plain">{commits}</ul></div>
</section>
</div>
<footer>Built by scripts/dashboard.py from factory.json, docs/BACKLOG.md, docs/TECH-DEBT.md, docs/decisions/, metrics/ and git.
Run python3 scripts/ci_runs.py to refresh the CI history, then python3 scripts/dashboard.py.</footer>
</main>
</body>
</html>
"""


def build():
    d = collect()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render(d))
    with open(os.path.join(OUT, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    with open(os.path.join(OUT, "SUMMARY.md"), "w", encoding="utf-8") as fh:
        fh.write(summary(d))
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--print", action="store_true", dest="print_summary")
    a = ap.parse_args()
    d = build()
    if a.print_summary:
        print(summary(d), end="")
    else:
        print("dashboard written to dashboard/index.html")
    if a.open:
        webbrowser.open("file://" + os.path.join(OUT, "index.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

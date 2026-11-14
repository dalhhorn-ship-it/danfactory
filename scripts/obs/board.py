"""Dashboard data layer: BACKLOG/TECH-DEBT parsing, version and metric views, the roadmap model (split from
scripts/dashboard.py, SIZE-3). `dashboard` re-exports every name here, so `dashboard.parse_backlog` etc. still work."""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import metrics  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "scripts", "obs"))
import tplfiles  # noqa: E402

PHASES = ["brainstorm", "operating-model", "build"]
STATES = {" ": "todo", "~": "doing", "x": "done", "X": "done", "!": "blocked", "-": "dropped"}
ITEM_RE = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(.*)$")
MILESTONE_RE = re.compile(r"^##\s+(?:Milestone:\s*)?(.+?)\s*(?:\(target:\s*([0-9-]*)\s*\))?\s*$")
DEBT_RE = re.compile(r"^\s*[-*]\s+\[(.)\]\s+(TD-\d+)\s+(.*?)(?:\s+[—-]\s+(.*))?$")
CLOSED_RE = re.compile(r"^(done|resolved|fixed|closed|dropped|wontfix|paid)\b", re.I)
SEVERITY_TO_IMPACT = {"critical": "high", "major": "high", "high": "high", "medium": "medium", "minor": "low", "low": "low"}
SEQUENCE_RE = re.compile(r"^>\s*Sequence:\s*(.+)$")
RELEASE_RE = re.compile(r"\s*\(release:\s*([\w.-]+)\s*\)")
AFTER_RE = re.compile(r"\s*\(after:\s*([A-Z][A-Z0-9]{1,5}-\d+)\s*\)")
SPEC_RE = re.compile(r"docs/specs/[\w.-]+\.md")
NEXT_UP = 3
MARKER_RE = r"\b(TODO|FIXME|HACK|XXX)\b"
SKIP_DIRS = ("docs/", ".claude/", ".factory/", "dashboard/", "metrics/", "templates/",
             "scripts/dashboard.py", "scripts/obs/board.py", "README.md", "CLAUDE.md")
LARGE_FILE_LINES = 500
# Roadmap swimlanes: backlog items whose tags hit FOUNDATION_TAGS (or #foundation) go to the
# technical-foundation lane; everything else is user value. Open tech-debt items always go to foundation.
FOUNDATION_TAGS = {"foundation", "tech", "arch", "architecture", "infra", "runway", "debt", "tech-debt",
                   "refactor", "quality", "ci", "process", "security", "perf", "ops", "platform"}
LANES = (("value", "Value-driven features", "value for users"),
         ("foundation", "Technical foundation", "architecture, runway, tech debt"))



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


def parse_backlog(text):
    milestones, current = [], None
    for line in strip_code(text).splitlines():
        rel = RELEASE_RE.search(line) if line.startswith("## ") else None
        if rel:
            line = RELEASE_RE.sub("", line).rstrip()
        m = MILESTONE_RE.match(line)
        if line.startswith("## ") and m:
            current = {"name": m.group(1).strip(), "target": m.group(2) or "", "items": [], "sequence": "",
                       "release": rel.group(1) if rel else ""}
            milestones.append(current)
            continue
        sm = SEQUENCE_RE.match(line)
        if sm and current is not None and not current["sequence"]:
            current["sequence"] = sm.group(1).strip()
            continue
        im = ITEM_RE.match(line)
        if im and current is not None:
            title = im.group(2).strip()
            spec = SPEC_RE.search(title)
            # "[text](docs/specs/x.md)" -> "text"; a bare "(docs/specs/x.md)" or path is dropped from the title
            title = re.sub(r"\[([^\]]+)\]\(docs/specs/[\w.-]+\.md\)", r"\1", title)
            title = re.sub(r"\s*\(?docs/specs/[\w.-]+\.md\)?", "", title)
            size = re.search(r"\((S|M|L)\)", title)
            rel, aft = RELEASE_RE.search(title), AFTER_RE.search(title)
            title = AFTER_RE.sub("", RELEASE_RE.sub("", title))  # optional DASH-4 markers never show in titles
            current["items"].append({
                "state": STATES.get(im.group(1), "todo"),
                "title": re.sub(r"\s*\((S|M|L)\)|\s*#[\w-]+", "", title).strip(),
                "size": size.group(1) if size else "",
                "tags": re.findall(r"#([\w-]+)", title),
                "spec": spec.group(0) if spec else "",
                "release": rel.group(1) if rel else "", "after": aft.group(1) if aft else "",
            })
    for ms in milestones:
        live = [i for i in ms["items"] if i["state"] != "dropped"]
        done = sum(i["state"] == "done" for i in live)
        ms["total"], ms["done"] = len(live), done
        ms["pct"] = round(100.0 * done / len(live)) if live else 0
    return milestones


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


def parse_debt(text):
    """Tech debt register: checklist lines (`- [ ] TD-001 Title — impact: high · effort: M · area: x`) and/or a
    table `Id | Severity | Item | Where | Size | Source | Status` (columns found by header name; major = high)."""
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
        if all(re.fullmatch(r":?-+:?", x or "-") for x in c) or len(c) < len(header):
            continue
        row = dict(zip(header, c))

        def col(*names):
            return next((v for n in names for h, v in row.items() if n in h), "")
        status = col("status")
        items.append({
            "id": c[0], "title": col("item", "title", "description"),
            "open": not CLOSED_RE.match(status) and not section.startswith("resolved"),
            "impact": SEVERITY_TO_IMPACT.get(col("severity", "impact").lower(), ""),
            "effort": col("size", "effort"), "area": col("where", "area"),
        })
    return items


def debt_signals(f):
    tpl = tplfiles.owned(ROOT)  # NEW-2: unchanged template files are upstream's, not this project's debt
    files = [p for p in git("ls-files").splitlines() if p and not p.startswith(SKIP_DIRS) and p not in tpl]
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


def lane_of(tags):
    tags = {t.lower() for t in tags}
    if "value" in tags or "feature" in tags:
        return "value"
    return "foundation" if tags & FOUNDATION_TAGS else "value"


def spec_status(path):
    """PRD badge for a backlog item: 'draft' / 'approved' from the spec's Status line, else ''."""
    m = re.search(r"Status:\s*(draft|approved)", read(path)) if path else None
    return m.group(1) if m else ""


def roadmap(backlog, open_debt):
    """Proposed sequence: milestones in BACKLOG.md order, items in file order. Open items get ONE global number
    across both lanes and all milestones (1 = next up). Fully done milestones collapse to a summary line.
    Open debt not yet scheduled is a final column that continues the numbering."""
    columns, done_ms, upcoming, seq = [], [], [], 0
    debt_cards = [{"title": "%s %s" % (x["id"], x["title"]), "state": "todo", "size": x["effort"],
                   "lane": "foundation", "impact": x["impact"], "debt": True}
                  for x in sorted(open_debt, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["impact"], 3))]
    groups = [(ms["name"], ms["target"], ms.get("sequence", ""), ms["items"]) for ms in backlog]
    if debt_cards:
        groups.append(("Tech debt to schedule", "", "", debt_cards))
    for name, target, why, items in groups:
        cards = {"value": [], "foundation": []}
        live = [it for it in items if it["state"] != "dropped"]
        for it in live:
            lane = it.get("lane") or lane_of(it.get("tags", []))
            card = {"title": it["title"], "state": it["state"], "size": it.get("size", ""),
                    "impact": it.get("impact", ""), "debt": it.get("debt", False), "seq": None,
                    "prd": spec_status(it.get("spec", ""))}
            if it["state"] != "done":
                seq += 1
                card["seq"] = seq
                upcoming.append(dict(card, lane=lane, short=re.split(r"\s+AC:", it["title"])[0].strip().rstrip(".;:, ")))
            cards[lane].append(card)
        for k in cards:  # open cards first, done ones trail; sort is stable so file order is kept in each group
            cards[k].sort(key=lambda c: c["seq"] is None)
        if live and all(it["state"] == "done" for it in live):
            done_ms.append({"name": name, "done": len(live), "total": len(live)})
        elif live:
            columns.append({"name": name, "target": target, "sequence": why, "lanes": cards})
    opened = {k: sum(1 for c in columns for x in c["lanes"][k] if x["seq"]) for k in ("value", "foundation")}
    return {"columns": columns, "done": done_ms, "next": upcoming[:NEXT_UP], "open": opened}

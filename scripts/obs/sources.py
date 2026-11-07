"""Read repo facts for the observability tabs. Every function takes `root`; stdlib only, no network."""
import glob
import json
import os
import re
import subprocess

try:
    import tomllib
except ImportError:  # python < 3.11
    tomllib = None

SRC_EXT = (".py", ".ts", ".tsx", ".js", ".mjs")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ID_RE = re.compile(r"^([A-Z][A-Z0-9]{1,5}-\d+)\b")
TEST_RE = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|[^/]*\.(test|spec)\.(ts|tsx|js|mjs)$)")


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def git(root, *args):
    try:
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        return p.stdout if p.returncode == 0 else ""
    except OSError:
        return ""


def section(text, heading):
    """Body of the `## heading` section (up to the next `## `)."""
    m = re.search(r"(?ms)^##\s+%s\s*$(.*?)(?=^##\s|\Z)" % re.escape(heading), text)
    return m.group(1).strip() if m else ""


def goal_outcome(root):
    """The GOAL.md Outcome text, or '' while it is still the `_placeholder_`."""
    body = section(read(root, "docs/GOAL.md"), "Outcome")
    if not body or (body.startswith("_") and body.endswith("_")):
        return ""
    return body


def parse_prd(text, slug=""):
    """PRD header facts, or None when the file is not a `# PRD:` document."""
    t = re.search(r"(?m)^#\s+PRD:\s*(.+?)\s*$", text)
    if not t:
        return None
    sm = re.search(r"(?m)^>\s*Status:.*$", text)
    line = sm.group(0) if sm else ""
    st = re.search(r"Status:\s*([\w-]+)", line)
    bl = re.search(r"Backlog:\s*(.+?)\s*(?:·|$)", line)
    status = st.group(1).lower() if st else ""
    date = DATE_RE.search(line)
    ac = section(text, "Acceptance criteria")
    return {"slug": slug, "title": t.group(1), "status": status,
            "approved": date.group(0) if status == "approved" and date else "",
            "backlog": bl.group(1) if bl else "", "ac": len(re.findall(r"(?m)^\d+\.", ac))}


def prds(root):
    out = []
    for p in sorted(glob.glob(os.path.join(root, "docs", "specs", "*.md"))):
        base = os.path.basename(p)
        if base.startswith("_"):
            continue
        slug = base[:-3]
        text = read(root, "docs/specs/" + base)
        prd = parse_prd(text, slug)
        if prd:
            out.append(prd)
    return out


def parse_adr(text, num=""):
    t = re.search(r"(?m)^#\s+(?:\d+\s*[—-]\s*)?(.+?)\s*$", text)
    st = re.search(r"(?m)^>\s*Status:\s*([\w-]+)", text)
    return {"num": num, "title": t.group(1) if t else "", "status": st.group(1).lower() if st else "", "text": text}


def adrs(root):
    out = []
    for p in sorted(glob.glob(os.path.join(root, "docs", "decisions", "[0-9][0-9][0-9][0-9]-*.md"))):
        base = os.path.basename(p)
        if base.startswith("0000"):
            continue
        out.append(parse_adr(read(root, "docs/decisions/" + base), base[:4]))
    return out


def _strip_jsonc(s):
    """Drop // and /* */ comments outside strings, then trailing commas."""
    out, i, n, in_str = [], 0, len(s), False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif s.startswith("//", i):
            while i < n and s[i] != "\n":
                i += 1
            continue
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def parse_wrangler(text, toml=False):
    """{name, main, bindings:[{name, kind}]}: binding names only, never vars values or ids."""
    try:
        cfg = tomllib.loads(text) if toml and tomllib else json.loads(_strip_jsonc(text))
    except (ValueError, AttributeError):
        return None
    if not isinstance(cfg, dict):
        return None
    found = []

    def add(kind, items, key):
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and it.get(key):
                found.append({"name": str(it[key]), "kind": kind})

    add("d1_databases", cfg.get("d1_databases"), "binding")
    add("kv_namespaces", cfg.get("kv_namespaces"), "binding")
    add("r2_buckets", cfg.get("r2_buckets"), "binding")
    q = cfg.get("queues") if isinstance(cfg.get("queues"), dict) else {}
    add("queue producer", q.get("producers"), "binding")
    add("queue consumer", q.get("consumers"), "queue")
    do = cfg.get("durable_objects") if isinstance(cfg.get("durable_objects"), dict) else {}
    add("durable_object", do.get("bindings"), "name")
    add("service", cfg.get("services"), "binding")
    for k in ("ai", "assets"):
        if isinstance(cfg.get(k), dict) and cfg[k].get("binding"):
            found.append({"name": str(cfg[k]["binding"]), "kind": k})
    return {"name": str(cfg.get("name") or ""), "main": str(cfg.get("main") or ""),
            "bindings": sorted(found, key=lambda b: (b["name"], b["kind"]))}


def wrangler(root):
    for fn, toml in (("wrangler.jsonc", False), ("wrangler.json", False), ("wrangler.toml", True)):
        text = read(root, fn)
        if text:
            return parse_wrangler(text, toml)
    return None


def tables(root):
    names = set()
    for p in glob.glob(os.path.join(root, "migrations", "*.sql")):
        names.update(re.findall(r"(?i)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)", read(root, os.path.relpath(p, root))))
    return sorted(names)


def git_log(root, limit=500):
    """Newest-first commits: sha, subject, body, files, version (first tag at or after the commit).
    Assumes linear history."""
    raw = git(root, "log", "-n%d" % limit, "--name-only", "--format=%x1e%H%x1f%s%x1f%b%x1f%D%x1f")
    commits = []
    for rec in raw.split("\x1e")[1:]:
        parts = rec.split("\x1f")
        if len(parts) < 5:
            continue
        sha, subject, body, deco, files = parts[:5]
        tags = re.findall(r"tag:\s*([^,\s]+)", deco)
        commits.append({"sha": sha[:7], "subject": subject, "body": body, "tag": tags[0] if tags else "",
                        "files": [f for f in files.splitlines() if f.strip()]})
    nxt = ""
    for c in commits:  # newest first, so carry the nearest later tag backwards in time
        nxt = c["tag"] or nxt
        c["version"] = nxt
    return commits


def project_files(root):
    out = git(root, "ls-files").splitlines()
    if out:
        return sorted(out)
    found = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in (".git", "node_modules", "__pycache__", "dashboard")]
        found += [os.path.relpath(os.path.join(d, f), root) for f in files]
    return sorted(found)


def is_test(path):
    return bool(TEST_RE.search(path))


def test_files(root):
    return [p for p in project_files(root) if is_test(p) and p.endswith(SRC_EXT)]


def commit_times(root):
    """{path: unix time of the last commit touching it}, from one git walk (newest first)."""
    out, cur, times = git(root, "log", "--name-only", "--format=%x1e%ct"), 0, {}
    for ln in out.splitlines():
        if ln.startswith("\x1e"):
            cur = int(ln[1:] or 0)
        elif ln.strip():
            times.setdefault(ln.strip(), cur)
    return times


def last_record(root, kind):
    """Newest row of kind across metrics/records.jsonl (committed) and records.local.jsonl (gitignored; `check`
    rows), written by `metrics.py record <kind>`; else None."""
    row = None
    for name in ("metrics/records.jsonl", "metrics/records.local.jsonl"):
        for ln in read(root, name).splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("kind") == kind and r.get("ts") and (row is None or str(r["ts"]) >= str(row["ts"])):
                row = r
    return row

"""Size monitoring (SIZE-1): lines per area, big files, always-loaded context, growth over 7 and 30 days, budget flags.

Stdlib and offline. Current numbers come from `git ls-files` read from the working tree; the past is read from git
objects in one `git cat-file --batch` call (blobs shared between snapshots are read once). Budgets: factory.json
`budgets.size` over DEFAULTS. A flag never fails anything; the gate `size` check only warns.
"""
import json
import os
import subprocess
import sys

SRC_EXT = (".py", ".ts", ".tsx", ".js", ".mjs")
DEFAULTS = {"file_lines_warn": 400, "file_lines_max": 700, "always_loaded_tokens_max": 2500,
            "agents_max": 20, "code_growth_30d_pct_warn": 25}
AREAS = ("code", "tests", "docs", "hooks", "agents", "skills", "evals")
LABELS = {"code": "Product code (incl. hooks)", "tests": "Tests", "docs": "Docs (*.md)", "hooks": "Hooks (also in code)",
          "agents": "Agents", "skills": "Skills", "evals": "Evals"}
WINDOWS = (7, 30)
TOP = 8
NO_HISTORY = "not enough history"
SKIP = ("node_modules/", "dashboard/", "metrics/", ".git/")


def budgets(factory):
    b = dict(DEFAULTS)
    for k, v in (((factory or {}).get("budgets") or {}).get("size") or {}).items():
        if k in b and isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            b[k] = v
    return b


def _is_test(p):
    return p.startswith(".factory/tests/") or "/tests/" in "/" + p or p.startswith("tests/") or \
        p.rsplit("/", 1)[-1].startswith("test_") or p.endswith(("_test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js"))


def area(p):
    """The area a path counts in (first match), or None. Hooks are a second view of code files."""
    if p.startswith("evals/"):
        return "evals"
    if _is_test(p):
        return "tests"
    if p.startswith(".claude/agents/"):
        return "agents"
    if p.startswith(".claude/skills/"):
        return "skills"
    if p.endswith(SRC_EXT) and not p.startswith(".factory/"):
        return "code"
    if p.endswith(".md"):
        return "docs"
    return None


def is_product(p):
    return area(p) == "code"


def _areas_of(p):
    a = area(p)
    return (a, "hooks") if a == "code" and p.startswith(".claude/hooks/") else (a,)


def _lines(data):
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _git(root, *args, inp=None):
    try:
        p = subprocess.run(["git", "-C", root, "-c", "core.quotepath=off", *args], cwd=root, input=inp,
                           capture_output=True, check=False)
        return p.stdout if p.returncode == 0 else b""
    except OSError:
        return b""


def has_git(root):
    return os.path.exists(os.path.join(root, ".git")) and bool(_git(root, "rev-parse", "--git-dir").strip())


def _tracked(root):
    if has_git(root):
        out = _git(root, "ls-files", "-z").decode("utf-8", "replace")
        return [p for p in out.split("\0") if p]
    res = []
    for d, dirs, files in os.walk(root):
        rel = os.path.relpath(d, root).replace(os.sep, "/")
        dirs[:] = [x for x in dirs if not (rel == "." and x + "/" in SKIP) and x not in ("node_modules", ".git")]
        res += [(rel + "/" + f if rel != "." else f) for f in files]
    return res


def _count(rows):
    """{area: {"files": n, "lines": n}} from [(path, lines)]."""
    out = {a: {"files": 0, "lines": 0} for a in AREAS}
    for p, n in rows:
        for a in _areas_of(p):
            if a:
                out[a]["files"] += 1
                out[a]["lines"] += n
    return out


def current_files(root):
    rows = []
    for p in _tracked(root):
        if not area(p) or p.startswith(SKIP):
            continue
        try:
            with open(os.path.join(root, p), "rb") as fh:
                rows.append((p, _lines(fh.read())))
        except OSError:
            continue  # tracked but deleted in the working tree
    return rows


def _snapshots(root, shas):
    """{sha: {area: counts}} for commits, reading every distinct blob once via cat-file --batch."""
    trees, blobs = {}, {}
    for sha in shas:
        ents = []
        for rec in _git(root, "ls-tree", "-r", "-z", sha).decode("utf-8", "replace").split("\0"):
            if "\t" not in rec:
                continue
            meta, path = rec.split("\t", 1)
            m = meta.split()
            if len(m) == 3 and m[1] == "blob" and area(path) and not path.startswith(SKIP):
                ents.append((path, m[2]))
                blobs[m[2]] = None
        trees[sha] = ents
    out = _git(root, "cat-file", "--batch", inp=("\n".join(blobs) + "\n").encode()) if blobs else b""
    i = 0
    while i < len(out):
        nl = out.index(b"\n", i)
        head = out[i:nl].split()
        if len(head) != 3:  # "<sha> missing"
            i = nl + 1
            continue
        size = int(head[2])
        blobs[head[0].decode()] = _lines(out[nl + 1:nl + 1 + size])
        i = nl + 1 + size + 1
    return {sha: _count([(p, blobs.get(b) or 0) for p, b in ents]) for sha, ents in trees.items()}


def _at(root, days, now):
    """The commit nearest the date `days` ago: the latest at or before it, else the first commit when history is
    shorter (labelled with its real age). None when there is no usable commit."""
    before = _git(root, "rev-list", "-1", "--before=%d" % (now - days * 86400), "HEAD").decode().strip()
    if before:
        return before, days
    first = _git(root, "rev-list", "--max-parents=0", "--format=%ct", "HEAD").decode().split()
    if len(first) < 3:
        return None
    age = (now - int(first[2])) // 86400
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    return (first[1], int(age)) if age >= 1 and first[1] != head else None


def growth(root, now_counts, now=None):
    """{"7": {...}|None, "30": ...}: per window {days, areas: {a: {then, delta, pct}}} or None (not enough history)."""
    import time
    now = int(now or time.time())
    res, picks = {}, {}
    if has_git(root):
        for w in WINDOWS:
            picks[w] = _at(root, w, now)
    snaps = _snapshots(root, sorted({p[0] for p in picks.values() if p})) if any(picks.values()) else {}
    for w in WINDOWS:
        pk = picks.get(w)
        if not pk or pk[0] not in snaps:
            res[str(w)] = None
            continue
        then = snaps[pk[0]]
        res[str(w)] = {"days": pk[1], "sha": pk[0][:7], "areas": {a: {
            "then": then[a]["lines"], "delta": now_counts[a]["lines"] - then[a]["lines"],
            "pct": round(100.0 * (now_counts[a]["lines"] - then[a]["lines"]) / then[a]["lines"], 1) if then[a]["lines"] else None}
            for a in AREAS}}
    return res


def always_loaded(root):
    """Tokens (chars/4) of CLAUDE.md plus what the SessionStart hook prints for `{}`; absent parts count 0."""
    claude = 0
    try:
        with open(os.path.join(root, "CLAUDE.md"), encoding="utf-8", errors="replace") as fh:
            claude = len(fh.read())
    except OSError:
        pass
    note = 0
    hook = os.path.join(root, ".claude", "hooks", "session_start.py")
    if os.path.isfile(hook):
        try:
            p = subprocess.run([sys.executable, hook], input="{}", cwd=root, capture_output=True, text=True, timeout=10,
                               env=dict(os.environ, CLAUDE_PROJECT_DIR=root))
            note = len(p.stdout)
        except (OSError, subprocess.SubprocessError):
            pass
    return {"claude_md": claude // 4, "session_start": note // 4, "total": (claude + note) // 4}


def counts(root, files):
    ls = lambda d, suf="": len([f for f in files if f.startswith(d) and f.endswith(suf) and "/" not in f[len(d):]])  # noqa: E731
    return {"agents": ls(".claude/agents/", ".md"),
            "skills": len([f for f in files if f.startswith(".claude/skills/") and f.endswith("/SKILL.md")]),
            "hooks": len([f for f in ls_names(files, ".claude/hooks/") if f.endswith(".py") and not f.startswith("_")]),
            "scripts": len([f for f in ls_names(files, "scripts/") if f.endswith((".py", ".sh"))])}


def ls_names(files, d):
    return [f[len(d):] for f in files if f.startswith(d) and "/" not in f[len(d):]]


def flags(d, b):
    """Breaches as [{kind, level, subject, value, budget, action}], worst first."""
    out = []
    for r in d["files"]:
        if r["lines"] > b["file_lines_max"]:
            out.append({"kind": "file-over-size", "level": "high", "subject": r["path"], "value": r["lines"], "budget": b["file_lines_max"],
                        "action": "split the module, or move it to an optional pack (raise the budget only with a reason)"})
        elif r["lines"] > b["file_lines_warn"]:
            out.append({"kind": "file-large", "level": "medium", "subject": r["path"], "value": r["lines"], "budget": b["file_lines_warn"],
                        "action": "agents read it in pieces; split it before it passes %d lines" % b["file_lines_max"]})
    if d["always_loaded"]["total"] > b["always_loaded_tokens_max"]:
        out.append({"kind": "always-loaded", "level": "high", "subject": "CLAUDE.md + session start note",
                    "value": d["always_loaded"]["total"], "budget": b["always_loaded_tokens_max"],
                    "action": "trim CLAUDE.md or the start note; move detail into docs/"})
    if d["counts"]["agents"] > b["agents_max"]:
        out.append({"kind": "agents", "level": "medium", "subject": "agents", "value": d["counts"]["agents"], "budget": b["agents_max"],
                    "action": "merge or retire an agent, or raise the budget with a reason"})
    g = (d["growth"].get("30") or {}).get("areas", {}).get("code")
    if g and g["pct"] is not None and g["pct"] > b["code_growth_30d_pct_warn"]:
        out.append({"kind": "size-growth", "level": "medium", "subject": "product code", "days": d["growth"]["30"]["days"], "value": g["pct"], "budget": b["code_growth_30d_pct_warn"],
                    "action": "pause features and trim, move rarely used code to an optional pack, or raise the budget with a reason"})
    out.sort(key=lambda f: (f["level"] != "high", -f["value"] / f["budget"]))
    return out


def text(f):
    """One alert line."""
    if f["kind"] == "size-growth":
        return "Size: %s grew %s%% in %d days (budget %s%% per 30 days). Action: %s" % (
            f["subject"], f["value"], f.get("days", 30), f["budget"], f["action"])
    unit = " tokens" if f["kind"] == "always-loaded" else " lines" if f["kind"].startswith("file") else ""
    return "Size: %s is %s%s (budget %s). Action: %s" % (f["subject"], f["value"], unit, f["budget"], f["action"])


def collect(root, factory=None):
    if factory is None:
        try:
            with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
                factory = json.load(fh)
        except (OSError, ValueError):
            factory = {}
    b = budgets(factory)
    rows = current_files(root)
    now = _count(rows)
    prod = sorted(({"path": p, "lines": n} for p, n in rows if is_product(p)), key=lambda r: (-r["lines"], r["path"]))
    d = {"budgets": b, "areas": now, "files": prod, "top": prod[:TOP], "always_loaded": always_loaded(root),
         "counts": counts(root, [p for p, _ in rows]), "growth": growth(root, now),
         "test_ratio": round(now["tests"]["lines"] / now["code"]["lines"], 2) if now["code"]["lines"] else None}
    d["flags"] = flags(d, b)
    d["files"] = [r for r in prod if r["lines"] > b["file_lines_warn"]]  # data.json keeps flagged files only
    d["alerts"] = [text(f) for f in d["flags"]]
    return d


def growth_text(g, a="code"):
    """'+N lines (+P%) in 30d' for a window dict, or NO_HISTORY."""
    if not g:
        return NO_HISTORY
    r = g["areas"][a]
    return "%+d lines%s in %dd" % (r["delta"], " (%+.0f%%)" % r["pct"] if r["pct"] is not None else "", g["days"])


def line(d):
    over = [f for f in d["flags"] if f["kind"] == "file-over-size"]
    return "%d flags; code %s lines in %s files, %d over %d lines; always loaded ~%d tokens; code growth %s" % (
        len(d["flags"]), format(d["areas"]["code"]["lines"], ","), d["areas"]["code"]["files"], len(over),
        d["budgets"]["file_lines_max"], d["always_loaded"]["total"], growth_text(d["growth"].get("30")))

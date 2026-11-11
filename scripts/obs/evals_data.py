"""Derivations for the Evals tab views (EVAL-4): library, heatmap, gate coverage, economics. Pure and offline.

Inputs are the rows of metrics/evals.jsonl (already filtered by evals.read_rows), evals/tasks/*/task.json and
evals/rules.json. Anything malformed is skipped or shown as "unknown"; nothing here raises on bad data.
"""
import json
import os
import subprocess

DOTS = 10
HEAT_SETS = 12
KINDS_WITH_HOOK = ("hook", "deny")  # a gate mapped to one of these has a guard that can fire (proof strength applies)
STRENGTH_ORDER = {"strong": 0, "weak": 1, "unknown": 2, "n/a": 3}


def _num(r, k):
    v = r.get(k)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _counted(rows):
    return [r for r in rows if not r.get("error")]


def load_tasks(root):
    """Tolerant task loader: [{id, title, gates, prompt, graders, covers, fixture, bad}]; a bad task.json is skipped."""
    d = os.path.join(root, "evals", "tasks")
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for name in names:
        p = os.path.join(d, name, "task.json")
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                t = json.load(fh)
        except (OSError, ValueError):
            t = None
        if not isinstance(t, dict):
            out.append({"id": name, "title": "unreadable task.json", "gates": [], "prompt": "", "graders": [],
                        "covers": [], "fixture": None, "bad": True})
            continue
        gates = t.get("gates") if isinstance(t.get("gates"), list) else []
        graders = [g for g in t.get("graders") or [] if isinstance(g, dict)] if isinstance(t.get("graders"), list) else []
        covers = t.get("covers") if isinstance(t.get("covers"), list) else []
        fx = "evals/tasks/%s/fixture" % name
        out.append({"id": str(t.get("id") or name), "title": str(t.get("title") or "(no title)"), "gates": [str(g) for g in gates],
                    "prompt": str(t.get("prompt") or ""), "graders": [str(g.get("type") or "?") for g in graders],
                    "covers": [str(c) for c in covers], "fixture": fx if os.path.isdir(os.path.join(root, fx)) else None,
                    "bad": not (t.get("title") and gates and graders), "dir": name})
    return out


def load_rules(root):
    """(rules, ok). rules: [{id, title, kind, source, gates, hook}]; ok False when the file is missing or unreadable."""
    try:
        with open(os.path.join(root, "evals", "rules.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        raw = data.get("rules") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return [], False
    except (OSError, ValueError):
        return [], False
    rules = []
    for r in raw:
        if isinstance(r, dict) and r.get("id") and r.get("title"):
            g = r.get("gates")
            rules.append({"id": str(r["id"]), "title": str(r["title"]), "kind": str(r.get("kind") or "rule"),
                          "source": str(r.get("source") or ""), "hook": str(r.get("hook") or ""),
                          "gates": [str(x) for x in g] if isinstance(g, list) else []})
    return rules, True


def added_dates(root):
    """{dir name: YYYY-MM-DD of the commit that first added its task.json}; {} when git history is unavailable."""
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--name-only", "--format=@%cs", "--", "evals/tasks"], cwd=root,
                             capture_output=True, text=True, timeout=20, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    dates, cur = {}, None
    for ln in out.splitlines():  # newest first, so the last assignment is the oldest = first commit
        if ln.startswith("@"):
            cur = ln[1:]
        elif ln.endswith("/task.json") and cur:
            parts = ln.split("/")
            if len(parts) == 4:
                dates[parts[2]] = cur
    return dates


def run_strength(r):
    """strong = a guard blocked a call in this run, weak = guard never acted, unknown = row has no evidence field."""
    ev = r.get("hook_evidence")
    if not isinstance(ev, dict):
        return "unknown"
    blocked = ev.get("blocked")
    return "strong" if (isinstance(blocked, list) and blocked) or _num(ev, "guard_blocks") > 0 else "weak"


def hookable(task, rules):
    gates = set(task["gates"])
    return any(r["kind"] in KINDS_WITH_HOOK and gates & set(r["gates"]) for r in rules)


def task_strength(task, runs, rules):
    """(label, detail). n/a when no gate of the task maps to a hook or deny rule; else from the runs shown."""
    if rules and not hookable(task, rules):
        return "n/a", "no hook or deny rule is mapped to this task's gates, so there is nothing to fire"
    marks = [run_strength(r) for r in runs]
    ev = [m for m in marks if m != "unknown"]
    if not ev:
        return "unknown", "no run carries hook evidence yet (rows written before EVAL-4)"
    strong = ev.count("strong")
    if strong:
        return "strong", "a guard blocked a call in %d of %d runs with evidence" % (strong, len(ev))
    return "weak", "no guard blocked a call in %d runs with evidence: the agent never reached the guard" % len(ev)


def library(root, rows, tasks=None, rules=None):
    tasks = load_tasks(root) if tasks is None else tasks
    rules = load_rules(root)[0] if rules is None else rules
    dates = added_dates(root)
    out = []
    for t in tasks:
        runs = [r for r in _counted(rows) if r["task"] == t["id"]][-DOTS:]
        label, why = task_strength(t, runs, rules)
        cost = round(sum(_num(r, "cost_usd") for r in runs) / len(runs), 4) if runs else None
        out.append({**t, "dots": [bool(r.get("pass")) for r in runs], "cost_per_run": cost, "strength": label,
                    "strength_why": why, "added": dates.get(t.get("dir") or t["id"], "unknown")})
    return out


def heatmap(rows, task_ids):
    sets = []
    for r in rows:
        if r["set"] not in sets:
            sets.append(r["set"])
    sets = sets[-HEAT_SETS:]
    cols = []
    for s in sets:
        rs = [r for r in rows if r["set"] == s]
        ts = max((str(r.get("ts") or "") for r in rs), default="")
        cols.append({"set": s, "date": ts[:10] or "?", "n": len(_counted(rs))})
    ids = list(task_ids) + sorted({r["task"] for r in rows} - set(task_ids))
    grid = {}
    for tid in ids:
        cells = []
        for s in sets:
            rs = [r for r in _counted(rows) if r["task"] == tid and r["set"] == s]
            cells.append({"runs": len(rs), "passes": sum(bool(r.get("pass")) for r in rs)} if rs else None)
        grid[tid] = cells
    return {"cols": cols, "tasks": ids, "grid": grid}


def coverage(rules, lib):
    """Per rule: covered by which tasks and at what strength. Uncovered first; then weak, then strong."""
    by_gate = {}
    for t in lib:
        for g in t["gates"]:
            by_gate.setdefault(g, []).append(t)
    out = []
    for r in rules:
        tasks = {}
        for g in r["gates"]:
            for t in by_gate.get(g, []):
                tasks[t["id"]] = t["strength"]
        seen = {v for v in tasks.values() if v != "n/a"}  # n/a tasks have no hook to fire: they never weaken a cover
        if not tasks:
            status = "uncovered"
        elif not seen or "strong" in seen:
            status = "covered"
        elif "unknown" in seen:
            status = "covered (unknown proof)"
        else:
            status = "covered (weak)"
        out.append({**r, "tasks": sorted(tasks), "strengths": tasks, "status": status})
    rank = {"uncovered": 0, "covered (weak)": 1, "covered (unknown proof)": 2, "covered": 3}
    out.sort(key=lambda x: (rank[x["status"]], x["id"]))
    return out


def economics(rows, threshold):
    """One point per model: its latest run set. Highlights the cheapest model within `threshold` of the best pass rate."""
    models = []
    for r in rows:
        m = str(r.get("model") or "?")
        if m not in models:
            models.append(m)
    pts = []
    for m in models:
        mine = [r for r in rows if str(r.get("model") or "?") == m]
        sid = mine[-1]["set"]
        rs = _counted([r for r in mine if r["set"] == sid])
        if not rs:
            continue
        ok = [r for r in rs if r.get("pass")]
        cost = sum(_num(r, "cost_usd") for r in rs)
        tok = sum(_num(r, "tokens_in") + _num(r, "tokens_cache") + _num(r, "tokens_out") for r in rs)
        pts.append({"model": m, "set": sid, "n": len(rs), "pass_rate": round(len(ok) / len(rs), 3),
                    "cost_per_run": round(cost / len(rs), 4), "cost_per_pass": round(cost / len(ok), 4) if ok else None,
                    "tokens_per_run": round(tok / len(rs)), "wall_s": round(sum(_num(r, "wall_s") for r in rs) / len(rs), 1)})
    best = max((p["pass_rate"] for p in pts), default=0)
    ok_models = [p for p in pts if p["pass_rate"] >= best - threshold and p["pass_rate"] > 0]
    pick = min(ok_models, key=lambda p: p["cost_per_run"])["model"] if len(pts) > 1 and ok_models else None
    for p in pts:
        p["cheapest_ok"] = p["model"] == pick
    return {"points": pts, "pick": pick, "threshold": threshold}

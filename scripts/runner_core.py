"""Fixer runner base: settings, constants, errors, rows and budget arithmetic, status summary.
Split from scripts/runner.py (SIZE-3); `runner` re-exports every name, so `runner.<name>` still works."""
import datetime
import json
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gate  # noqa: E402
import issues as L  # noqa: E402
import sandbox as S  # noqa: E402


BASELINE = "metrics/acceptance-baseline.json"

DEFAULTS = {"enabled": False, "staging_branch": "staging", "max_attempts": 3, "daily_budget_usd": 5, "run_budget_usd": 2,
            "model": "sonnet", "review_model": "sonnet", "max_turns": 40, "timeout_s": 900, "review_turns": 12,
            "attempt_estimate_usd": 0.5, "max_parallel": 1, "schedule_ok": False}
PARALLEL_CAP = 4  # hard cap whatever autonomy.max_parallel says
# One lock per shared resource of a parallel run: git worktree add/remove (they race on .git/worktrees), the in-process gate (it patches
# module globals), the staging worktree (merges, ledger, commits) and the runner rows file.
WT_LOCK, GATE_LOCK, MERGE_LOCK, ROWS_LOCK = threading.RLock(), threading.RLock(), threading.RLock(), threading.RLock()
# Paths a fixer may never change, on top of gate.protected: the gate and the machinery that judges or records its work.
RUNNER_PROTECTED = ["metrics/acceptance-baseline.json", "factory.json", ".claude/**", ".github/**", "issues/**", "metrics/**",
                    "scripts/gate.py", "scripts/gate_checks.py", "scripts/acceptance.py", "scripts/acceptance_exec.py", "scripts/runner.py",
                    "scripts/runner_*.py", "scripts/sandbox.py", "scripts/issues.py",
                    "scripts/metrics.py", "scripts/check.sh"]
# Empty files Claude Code's Bash sandbox (bubblewrap) leaves in the working directory as deny-mount points. Found in the smoke
# run: they showed up as untracked files and made the gate fail (`env-file-added`). Untracked and 0 bytes only: removed before commit.
SANDBOX_ARTIFACTS = (".env", ".env.development", ".env.development.local", ".env.local", ".env.production", ".env.production.local",
                     ".env.test", ".env.test.local", ".gitmodules", ".npmrc", ".yarnrc", ".yarnrc.yml", "bunfig.toml", "package-lock.json",
                     "package.json", "pnpm-lock.yaml", "yarn.lock", ".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile",
                     ".gitconfig", ".mcp.json", ".ripgreprc", ".vscode", ".idea")
IDENT = ["-c", "user.name=danfactory-runner", "-c", "user.email=runner@example.invalid", "-c", "core.hooksPath=/dev/null",
         "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false"]
EMPTY = "No runner activity yet: `python3 scripts/runner.py run --next` after setting factory.json autonomy.enabled (docs/policies/runner.md)."


class Refuse(Exception):
    pass


class Fail(Exception):
    """An attempt that must end now with a reason code (the loop goes on with the next attempt, or stops for budget-stop)."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def settings(root):
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            cfg = json.load(fh).get("autonomy") or {}
    except (OSError, ValueError):
        cfg = {}
    return {**DEFAULTS, **cfg}


def git(args, cwd, check=True):
    return S.git(IDENT + list(args), cwd, check=check)


def out_of(p):
    return (p.stdout or "").strip()


def rows_path(root):
    return os.path.join(root, S.RUNNER_ROWS)


def load_rows(root, staging=None):
    """Rows from the working tree file and, when a staging branch exists, from its committed copy (de-duplicated):
    runs commit their rows on staging, so a checkout of main must still see today's spend."""
    lines = []
    try:
        with open(rows_path(root), encoding="utf-8") as fh:
            lines += fh.read().splitlines()
    except OSError:
        pass
    if staging:
        p = subprocess.run(["git", "show", "%s:%s" % (staging, S.RUNNER_ROWS.replace(os.sep, "/"))], cwd=root, capture_output=True,
                           text=True)
        if p.returncode == 0:
            lines += p.stdout.splitlines()
    rows, seen = [], set()
    for ln in lines:
        if ln in seen or not ln.strip():
            continue
        seen.add(ln)
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def spent(rows, day=None):
    return sum(float(r.get("cost_usd") or 0) for r in rows if day is None or str(r.get("ts", ""))[:10] == day)


def mean_attempt_cost(rows):
    c = [float(r.get("cost_usd") or 0) for r in rows if r.get("kind") == "attempt"]
    return sum(c) / len(c) if c else 0.0


def estimate(rows, cfg):
    """Cost guess for the next paid unit: the mean attempt so far, else the conservative autonomy.attempt_estimate_usd (0.5)."""
    if any(r.get("kind") == "attempt" for r in rows):
        return mean_attempt_cost(rows)
    return float(cfg.get("attempt_estimate_usd", DEFAULTS["attempt_estimate_usd"]))


def remaining(rows, run_id, cfg, extra=0.0):
    """USD left under the tighter of the daily and the run cap (may be negative). `extra` = estimates of other fixers' running calls."""
    run = spent([r for r in rows if r.get("run") == run_id])
    return min(float(cfg["daily_budget_usd"]) - spent(rows, today()), float(cfg["run_budget_usd"]) - run) - extra


def budget_stop(rows, run_id, cfg, extra=0.0):
    """Why the next attempt may not start, or None. Estimate of the next attempt = estimate(). `extra` is the sum of the estimates of
    attempts running in parallel that have not booked their cost yet (AUTO-6: one shared budget)."""
    est = estimate(rows, cfg)
    day = spent(rows, today())
    run = spent([r for r in rows if r.get("run") == run_id])
    dcap, rcap = float(cfg["daily_budget_usd"]), float(cfg["run_budget_usd"])
    run_note = " plus ~$%.2f in flight" % extra if extra else ""
    if day >= dcap or day + extra + est > dcap:
        return "daily budget: $%.2f spent today%s plus ~$%.2f for the next attempt would pass the $%.2f cap" % (day, run_note, est, dcap)
    if run >= rcap or run + extra + est > rcap:
        return "run budget: $%.2f spent in this run%s plus ~$%.2f for the next attempt would pass the $%.2f cap" % (run, run_note, est, rcap)
    return None


def staging_lead(root, cfg, prod):
    p = subprocess.run(["git", "rev-list", "--count", "%s..%s" % (prod, cfg["staging_branch"])], cwd=root, capture_output=True, text=True)
    return int(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip().isdigit() else None


def parked_on(root, cfg):
    """[{id, title}] of issues in issues/blocked/ on the staging branch (or the working tree when there is no staging)."""
    st = cfg["staging_branch"]
    ok = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "refs/heads/" + st], cwd=root, capture_output=True)
    if ok.returncode != 0:
        return [{"id": i["id"], "title": i["title"]} for i in L.load(root) if i["state"] == "blocked"]
    p = subprocess.run(["git", "ls-tree", "-r", "--name-only", st, "--", "issues/blocked"], cwd=root, capture_output=True, text=True)
    res = []
    for path in p.stdout.splitlines():
        m = L.FILE_RE.match(os.path.basename(path))
        if m:
            res.append({"id": "ISS-" + m.group(1), "title": m.group(2)})
    return res


def summary(root):
    """Numbers for `status` and the dashboard Runner block, all from metrics/runner.jsonl and git."""
    cfg = settings(root)
    rows = load_rows(root, cfg["staging_branch"])
    att = [r for r in rows if r.get("kind") == "attempt"]
    groups = {}
    for r in att:
        groups.setdefault((r.get("run"), r.get("issue")), []).append(r)
    fixed = [g for g in groups.values() if any(x.get("outcome") == "merged" for x in g)]
    first = [g for g in groups.values() if any(x.get("attempt") == 1 for x in g)]
    first_pass = [g for g in first if any(x.get("attempt") == 1 and x.get("outcome") == "merged" for x in g)]
    spend = spent([r for r in rows if r.get("kind") in ("attempt", "second-reading")])
    last_codes = {}
    for r in att:
        last_codes[r.get("issue")] = r.get("codes") or []
    parked = [dict(p, codes=last_codes.get(p["id"], [])) for p in parked_on(root, cfg)]
    prod = (gate.config(root)[1] or {}).get("base_branch", "main")
    return {"exists": bool(rows) or bool(parked), "enabled": bool(cfg["enabled"]), "runs": len({r.get("run") for r in att}),
            "attempts": len(att), "fixed": len(fixed), "first_try_rate": (len(first_pass) / len(first)) if first else None,
            "rework_per_fixed": (sum(len(g) - 1 for g in fixed) / len(fixed)) if fixed else None,
            "cost_per_fixed": (spend / len(fixed)) if fixed else None, "spend_total": round(spend, 4),
            "spend_today": round(spent(rows, today()), 4), "daily_cap": float(cfg["daily_budget_usd"]),
            "parked": parked, "staging": cfg["staging_branch"], "prod": prod, "staging_lead": staging_lead(root, cfg, prod),
            "parallel": parallel_numbers(rows)}


def parallel_numbers(rows):
    """AUTO-6: parallel runs, the highest number of fixers seen working at once, attempts that ended `stale-after-merge`."""
    par = [r for r in rows if r.get("kind") == "parallel"]
    return {"runs": len(par), "max_concurrent": max([int(r.get("max_concurrent") or 0) for r in par] or [0]),
            "stale_after_merge": sum(1 for r in rows if r.get("kind") == "attempt" and "stale-after-merge" in (r.get("codes") or []))}


def human(st):
    if not st["exists"]:
        return EMPTY
    pct = lambda v: "n/a" if v is None else "%d%%" % round(100 * v)  # noqa: E731
    num = lambda v, f: "n/a" if v is None else f % v  # noqa: E731
    out = ["runner: %d run(s), %d attempt(s), %d issue(s) fixed; first-try pass %s, rework %s per fixed issue, $%s per fixed issue"
           % (st["runs"], st["attempts"], st["fixed"], pct(st["first_try_rate"]), num(st["rework_per_fixed"], "%.1f"),
              num(st["cost_per_fixed"], "%.2f")),
           "spend today $%.2f of $%.2f; autonomy %s" % (st["spend_today"], st["daily_cap"], "enabled" if st["enabled"] else "disabled"),
           "%s is %s commit(s) ahead of %s (promote it yourself, docs/policies/runner.md)"
           % (st["staging"], "?" if st["staging_lead"] is None else st["staging_lead"], st["prod"])]
    pl = st.get("parallel") or {}
    if pl.get("runs"):
        out.append("parallel: %d run(s), up to %d fixer(s) at once, %d attempt(s) stale-after-merge" % (pl["runs"], pl["max_concurrent"], pl["stale_after_merge"]))
    for p in st["parked"]:
        out.append("parked %s: %s [%s]" % (p["id"], p["title"], ", ".join(p["codes"]) or "no codes"))
    return "\n".join(out)

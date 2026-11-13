#!/usr/bin/env python3
"""Fixer runner (AUTO-4): one issue, one sandboxed agent, the gate decides, merges go to staging only. Stdlib only.
Design: docs/decisions/0009-fixer-runner.md. Policy: docs/policies/runner.md. PRD: docs/specs/gated-autonomy.md (C4).

  runner.py run [--issue ISS-n | --next] [--model M] [--max-attempts N] [--dry-run]   # spends money; you start every run
  runner.py status [--json]
  runner.py unpark ISS-n

Per attempt (at most autonomy.max_attempts): fresh git worktree from the staging branch (.claude/worktrees/runner-ISS-n, branch
fix/ISS-n) -> headless fixer in the eval sandbox (scripts/sandbox.py) -> the runner commits with trailers it controls
(Refs, Fixer-Attempt, Runner) -> the issue's tests must pass -> an independent reviewer agent returns ship or fix-first and the
runner writes the Review trailer -> gate.py with review required -> pass: merge --no-ff into staging, issues sync, worktree
removed; fail: the next attempt gets the gate's reasons. After the cap the issue moves to issues/blocked/ with an attempt log.
The budget (autonomy.daily_budget_usd, run_budget_usd) is checked before every attempt, never after. The runner never pushes
and never touches the production branch. Rows: metrics/runner.jsonl, committed on staging.
Exit codes: 0 fixed and merged (or nothing to do), 1 parked, 2 refused or usage error, 3 stopped by a budget cap."""
import argparse
import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gate  # noqa: E402
import issues as L  # noqa: E402
import sandbox as S  # noqa: E402

DEFAULTS = {"enabled": False, "staging_branch": "staging", "max_attempts": 3, "daily_budget_usd": 5, "run_budget_usd": 2,
            "model": "sonnet", "review_model": "sonnet", "max_turns": 40, "timeout_s": 900, "review_turns": 12}
# Paths a fixer may never change, on top of gate.protected: the gate and the machinery that judges or records its work.
RUNNER_PROTECTED = ["metrics/acceptance-baseline.json", "factory.json", ".claude/**", ".github/**", "issues/**", "metrics/**",
                    "scripts/gate.py", "scripts/acceptance.py", "scripts/runner.py", "scripts/sandbox.py", "scripts/issues.py",
                    "scripts/metrics.py", "scripts/check.sh"]
# Empty files Claude Code's Bash sandbox (bubblewrap) leaves in the working directory as deny-mount points. Found in the smoke
# run: they showed up as untracked files and made the gate fail (`env-file-added`). Untracked and 0 bytes only: removed before commit.
SANDBOX_ARTIFACTS = (".env", ".env.development", ".env.development.local", ".env.local", ".env.production", ".env.production.local",
                     ".env.test", ".env.test.local", ".gitmodules", ".npmrc", ".yarnrc", ".yarnrc.yml", "bunfig.toml", "package-lock.json",
                     "package.json", "pnpm-lock.yaml", "yarn.lock", ".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile",
                     ".gitconfig", ".mcp.json", ".ripgreprc", ".vscode", ".idea")
IDENT = ["-c", "user.name=danfactory-runner", "-c", "user.email=runner@example.invalid"]
EMPTY = "No runner activity yet: `python3 scripts/runner.py run --next` after setting factory.json autonomy.enabled (docs/policies/runner.md)."
DIFF_MAX = 40000


class Refuse(Exception):
    pass


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


# ---------------------------------------------------------------- rows and summary

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


def budget_stop(rows, run_id, cfg):
    """Why the next attempt may not start, or None. Estimate of the next attempt = mean cost of all attempts so far."""
    est = mean_attempt_cost(rows)
    day = spent(rows, today())
    run = spent([r for r in rows if r.get("run") == run_id])
    dcap, rcap = float(cfg["daily_budget_usd"]), float(cfg["run_budget_usd"])
    if day >= dcap or day + est > dcap:
        return "daily budget: $%.2f spent today plus ~$%.2f for the next attempt would pass the $%.2f cap" % (day, est, dcap)
    if run >= rcap or run + est > rcap:
        return "run budget: $%.2f spent in this run plus ~$%.2f for the next attempt would pass the $%.2f cap" % (run, est, rcap)
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
            "parked": parked, "staging": cfg["staging_branch"], "prod": prod, "staging_lead": staging_lead(root, cfg, prod)}


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
    for p in st["parked"]:
        out.append("parked %s: %s [%s]" % (p["id"], p["title"], ", ".join(p["codes"]) or "no codes"))
    return "\n".join(out)


# ---------------------------------------------------------------- git plumbing

def current_branch(root):
    b = out_of(git(["symbolic-ref", "--quiet", "--short", "HEAD"], root, check=False))
    if not b:
        raise Refuse("HEAD is detached: check out the branch the fixes should build on")
    return b


def worktrees(root):
    """{branch: path} of checked-out branches, from `git worktree list --porcelain`."""
    res, path = {}, None
    for ln in out_of(git(["worktree", "list", "--porcelain"], root)).splitlines():
        if ln.startswith("worktree "):
            path = ln[9:]
        elif ln.startswith("branch refs/heads/") and path:
            res[ln[18:]] = path
    return res


def wt_dir(root, name):
    return os.path.join(root, ".claude", "worktrees", name)


def remove_wt(root, path):
    if os.path.exists(path):
        git(["worktree", "remove", "--force", path], root, check=False)
        shutil.rmtree(path, ignore_errors=True)
    git(["worktree", "prune"], root, check=False)


def ensure_staging(root, cfg):
    """(path of a worktree with the staging branch checked out, whether it is a temporary one we must remove).
    Creates staging from the current branch if missing and merges the current branch in when it moved ahead."""
    st, cur = cfg["staging_branch"], current_branch(root)
    if st == gate.config(root)[1].get("base_branch", "main"):
        raise Refuse("autonomy.staging_branch must differ from the production branch (%s)" % st)
    if git(["rev-parse", "--verify", "--quiet", "refs/heads/" + st], root, check=False).returncode != 0:
        git(["branch", st, "HEAD"], root)
    where = worktrees(root).get(st)
    temp = False
    if where and os.path.abspath(where) == os.path.abspath(root):
        wt = root
    else:
        wt = wt_dir(root, "runner-staging")
        if where and os.path.abspath(where) != os.path.abspath(wt):
            raise Refuse("branch %s is checked out in %s: check out another branch there first" % (st, where))
        if where:  # leftover of a crashed run: keep its uncommitted rows, drop everything else
            git(["add", S.RUNNER_ROWS], wt, check=False)
            git(["commit", "-q", "-m", "runner: recover rows of an interrupted run"], wt, check=False)
            git(["reset", "-q", "--hard"], wt, check=False)
        else:
            os.makedirs(os.path.dirname(wt), exist_ok=True)
            git(["worktree", "add", "-q", wt, st], root)
        temp = True
    if cur != st and git(["merge-base", "--is-ancestor", cur, st], root, check=False).returncode != 0:
        m = git(["merge", "--no-edit", "-q", cur], wt, check=False)
        if m.returncode != 0:
            git(["merge", "--abort"], wt, check=False)
            if temp:
                remove_wt(root, wt)
            raise Refuse("could not bring %s up to date with %s (%s): merge them yourself" % (st, cur, (m.stderr or m.stdout).strip()[:120]))
    return wt, temp


def drop_sandbox_artifacts(wt):
    untracked = [p for p in out_of(git(["ls-files", "--others", "--exclude-standard", "-z"], wt)).split("\0") if p]
    for p in untracked:
        full = os.path.join(wt, p)
        if p in SANDBOX_ARTIFACTS and os.path.isfile(full) and os.path.getsize(full) == 0:
            os.remove(full)


def changed_files(wt):
    tracked = out_of(git(["diff", "--name-only", "-z", "HEAD"], wt)).split("\0")
    other = out_of(git(["ls-files", "--others", "--exclude-standard", "-z"], wt)).split("\0")
    return sorted({p for p in tracked + other if p})


def commit_ledger(wt, msg):
    git(["add", "-A", "--", "issues", S.RUNNER_ROWS], wt, check=False)
    if git(["diff", "--cached", "--quiet"], wt, check=False).returncode != 0:
        git(["commit", "-q", "-m", msg], wt)


# ---------------------------------------------------------------- prompts

def fixer_prompt(iss, root_rel, prd, run_id, k, cap, prev):
    ids = " ".join(sorted(iss["tests"]))
    with open(iss["path"], encoding="utf-8") as fh:
        body = fh.read()
    p = ["You are the fixer in an unattended runner (run %s, attempt %d of %d). Fix ONE issue in this project so that its failing "
         "acceptance tests pass." % (run_id, k, cap), "", "Issue file (%s):" % root_rel, "```", body.strip(), "```", "",
         "The PRD is docs/specs/%s.md: its acceptance criteria define the behaviour. Read it first." % prd,
         "Check your work with: python3 scripts/acceptance.py run --ids %s" % ids, "",
         "Rules (the runner enforces them):",
         "- Change product code (and add tests of your own if useful) until those tests pass without breaking the others.",
         "- Never edit tests/acceptance/, its manifest.json or metrics/acceptance-baseline.json. Do not edit factory.json, .claude/, "
         ".github/, issues/, metrics/ or the scripts gate.py, acceptance.py, runner.py, sandbox.py, issues.py, metrics.py, check.sh. "
         "A change there is reverted and the attempt fails.",
         "- Do not run git commit, git push or git checkout: the runner commits your changes after you stop.",
         "- Keep the change small and in the project's style. No new dependencies, no secrets, no network."]
    if prev:
        p += ["", "Previous attempt(s) were rejected. Their gate reasons (fix these first):"] + prev
    return "\n".join(p) + "\n"


def review_prompt(iss, prd, diff):
    return ("You are an independent code reviewer for an unattended fixer run. Review the diff below against the issue and the PRD "
            "(docs/specs/%s.md, readable with your tools). You cannot edit anything.\n\n"
            "Issue %s: %s\nFailing tests it must fix: %s\n\n"
            "Judge: does the change fix the issue for the right reason (no special-casing of test inputs, no hard-coded expected values), "
            "stay in scope, avoid secrets and unrelated edits, and match the PRD? Answer in a few lines of reasons, then end with exactly "
            "one final line: `VERDICT: ship` or `VERDICT: fix-first`.\n\n```diff\n%s\n```\n"
            % (prd, iss["id"], iss["title"], ", ".join(sorted(iss["tests"])), diff))


def final_text(events):
    for e in reversed(events):
        if e.get("type") == "result" and isinstance(e.get("result"), str):
            return e["result"]
    return ""


def parse_verdict(text):
    import re
    m = re.findall(r"(?im)^\W*VERDICT:\s*(ship|fix-first)\b", text or "")
    return m[-1].lower() if m else None


# ---------------------------------------------------------------- the attempt

def call_claude(prompt, model, turns, cwd, cfg, tools):
    tmp = tempfile.mkdtemp(prefix="runner-")
    try:
        home, scratch = os.path.join(tmp, "home"), os.path.join(tmp, "tmp")
        os.makedirs(home)
        os.makedirs(scratch)
        env = S.scrubbed_env(os.environ, home, scratch)
        t0 = time.time()
        out, rc = S.run_claude(prompt, model, turns, cwd, env, cfg["timeout_s"], tools)
        ev = S.parse_events(out)
        tok, cost, _turns, has = S.usage_cost(ev)
        return {"events": ev, "rc": rc, "tokens": tok, "cost": cost, "has_result": has, "seconds": time.time() - t0,
                "text": final_text(ev)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def gate_verdict(wt, base):
    """gate.py in-process with review forced to required; the gate module is the runner's own, not the fixer's copy."""
    orig = gate.config

    def cfg(root):
        f, g = orig(root)
        return f, dict(g, review="required")
    gate.config = cfg
    try:
        return gate.run_gate(wt, base)
    finally:
        gate.config = orig


def gate_reasons(v):
    return ["- gate `%s` [%s]: %s" % (c["id"], ", ".join(c["codes"]), c["detail"][:300]) for c in v["checks"] if c["status"] == "fail"]


def attempt(root, cfg, iss, prd, run_id, k, prev, model, review_model, staging):
    """One attempt in a fresh worktree. Returns (row, log line, reasons for the next attempt, merged-ready flag)."""
    name = "runner-" + iss["id"]
    wt, branch = wt_dir(root, name), "fix/" + iss["id"]
    remove_wt(root, wt)
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    base = out_of(git(["rev-parse", staging], root))
    git(["worktree", "add", "-q", "-B", branch, wt, staging], root)
    row = {"ts": now(), "kind": "attempt", "run": run_id, "issue": iss["id"], "attempt": k, "model": model, "review_model": review_model,
           "cost_usd": 0.0, "fixer_cost_usd": 0.0, "review_cost_usd": 0.0, "tokens_in": 0, "tokens_cache": 0, "tokens_out": 0,
           "seconds": 0.0, "gate": "skip", "codes": [], "review": "-", "outcome": "fail", "base": base[:9]}
    t0 = time.time()
    reasons = []

    def done(codes, reason):
        row["codes"] = codes
        row["seconds"] = round(time.time() - t0, 1)
        row["cost_usd"] = round(row["fixer_cost_usd"] + row["review_cost_usd"], 5)
        reasons.extend(reason if isinstance(reason, list) else [reason])
        return row, reasons

    rel = "issues/%s/%s" % (iss["state"], os.path.basename(iss["path"]))
    f = call_claude(fixer_prompt(iss, rel, prd, run_id, k, int(cfg["max_attempts"]), prev), model, int(cfg["max_turns"]), wt, cfg, S.TOOLS)
    row["fixer_cost_usd"] = f["cost"]
    for key in ("tokens_in", "tokens_cache", "tokens_out"):
        row[key] = f["tokens"][key]
    if f["rc"] == 124:
        return done(["fixer-timeout"], "- fixer timed out after %ss" % cfg["timeout_s"])
    if not f["has_result"]:
        return done(["fixer-error"], "- fixer produced no result (claude exit %s)" % f["rc"])
    # a commit the fixer made itself (with trailers of its own choosing) is squashed away: only the runner's commit survives
    git(["reset", "-q", "--soft", base], wt, check=False)
    drop_sandbox_artifacts(wt)
    files = changed_files(wt)
    pats = list(gate.config(root)[1].get("protected") or []) + RUNNER_PROTECTED
    hit = [p for p in files if gate.matches(p, pats)]
    if hit:
        for p in hit:
            if git(["ls-files", "--error-unmatch", p], wt, check=False).returncode == 0:
                git(["checkout", "HEAD", "--", p], wt, check=False)
            else:
                try:
                    os.remove(os.path.join(wt, p))
                except OSError:
                    pass
        return done(["fixer-touched-protected"], "- you changed protected paths (reverted, attempt lost): " + ", ".join(hit[:6]))
    if not files:
        return done(["no-change"], "- the fixer changed no file")
    msg = "fix(%s): %s\n\nRefs: %s\nFixer-Attempt: %d\nRunner: %s\n" % (iss["id"], iss["title"][:70], iss["id"], k, run_id)
    git(["add", "-A"], wt)
    git(["commit", "-q", "-m", msg], wt)
    # the issue's own tests must pass: the gate's baseline check does not cover tests that were failing when admitted
    try:
        tests, _adm = L.results(wt, None)
    except L.Usage as ex:
        return done(["acceptance-error"], "- acceptance suite did not run: %s" % str(ex)[:200])
    still = sorted(t for t in iss["tests"] if tests.get(t, {}).get("status") != "pass")
    if still:
        return done(["issue-not-fixed"], ["- issue tests still failing: %s: %s" % (t, (tests.get(t) or {}).get("message", "missing")[:160]) for t in still[:5]])
    diff = git(["diff", "--stat", "--patch", "%s..HEAD" % base], wt).stdout[:DIFF_MAX]
    rv = call_claude(review_prompt(iss, prd, diff), review_model, int(cfg["review_turns"]), wt, cfg, S.READ_TOOLS)
    row["review_cost_usd"] = rv["cost"]
    drop_sandbox_artifacts(wt)  # the reviewer's sandbox leaves its mount points in the same directory
    verdict = parse_verdict(rv["text"]) if rv["has_result"] else None
    row["review"] = verdict or "fix-first"
    if verdict is None:
        row["codes"].append("review-unparsed")
    note = " ".join((rv["text"] or "").split())[:400]
    git(["commit", "-q", "--amend", "-m", msg + "Review: %s\n" % row["review"]], wt)
    v = gate_verdict(wt, base)
    row["gate"] = v["verdict"]
    codes = list(v["codes"]) + [c for c in row["codes"] if c not in v["codes"]]
    if v["verdict"] == "pass" and row["review"] == "ship":
        row["outcome"] = "pass"
        return done([], [])
    rs = gate_reasons(v)
    if row["review"] != "ship":
        rs.append("- reviewer said fix-first: " + (note or "no reasons given"))
    return done(codes, rs)


# ---------------------------------------------------------------- commands

def preconditions(root, cfg, dry=False):
    if not cfg["enabled"]:
        raise Refuse("autonomy is not enabled: set factory.json autonomy.enabled to true (docs/policies/runner.md)")
    if not dry:
        problem = S.sandbox_problem()
        if problem:
            raise Refuse(problem)
    if git(["rev-parse", "--verify", "--quiet", "HEAD"], root, check=False).returncode != 0:
        raise Refuse("the project has no commit yet")
    if out_of(git(["status", "--porcelain"], root)):
        raise Refuse("the working tree is not clean: commit or stash first (the runner builds on committed state)")


def pick_issue(ledger_root, ref, nxt):
    issues = L.load(ledger_root)
    approved = gate.approved_slugs(ledger_root)
    if ref:
        iss = L._get(issues, ref)
        if iss["state"] == "blocked":
            raise Refuse("%s is parked: `runner.py unpark %s` after you acted on it" % (iss["id"], iss["id"]))
        if iss["state"] != "open":
            raise Refuse("%s is %s, not open" % (iss["id"], iss["state"]))
        if iss["meta"]["prd"] not in approved:
            raise Refuse("the PRD of %s (%s) is not approved: no build without an approved PRD (docs/policies/prd-approval.md)"
                         % (iss["id"], iss["meta"]["prd"]))
        return iss
    for iss in issues:
        if iss["state"] == "open" and iss["meta"]["prd"] in approved and iss["tests"]:
            return iss
    return None


def attempt_log(run_id, model, rows):
    lines = ["Run %s (model %s), %s:" % (run_id, model, now())]
    for r in rows:
        lines.append("- attempt %d: gate %s, review %s, codes [%s], $%.2f, %ss" % (
            r["attempt"], r["gate"], r["review"], ", ".join(r["codes"]) or "-", r["cost_usd"], r["seconds"]))
    return "\n".join(lines)


def cmd_run(a, root):
    cfg = settings(root)
    if a.model:
        cfg["model"] = a.model
    if a.max_attempts:
        cfg["max_attempts"] = a.max_attempts
    cap = int(cfg["max_attempts"])
    if not a.issue and not a.next:
        raise Refuse("give --issue ISS-n or --next")
    preconditions(root, cfg, a.dry_run)
    if a.dry_run:
        iss = pick_issue(root, a.issue, a.next)
        rows = load_rows(root, cfg["staging_branch"])
        print("runner (dry run): would fix %s, up to %d attempt(s), model %s; spent today $%.2f of $%.2f; %s"
              % (iss["id"] if iss else "nothing (no open issue with an approved PRD)", cap, cfg["model"], spent(rows, today()),
                 float(cfg["daily_budget_usd"]), budget_stop(rows, "dry-run", cfg) or "budget ok"))
        return 0
    lock = os.path.join(root, ".claude", "worktrees", ".runner.lock")
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        try:
            os.kill(int(open(lock).read() or 0), 0)
            raise Refuse("another runner is active (%s)" % lock)
        except (OSError, ValueError):
            pass
    try:  # refuse before anything is created when the root's own ledger already shows the problem
        pick_issue(root, a.issue, a.next)
    except L.Usage:
        pass  # the issue may exist on staging only; the staging ledger decides
    swt, temp = None, False
    try:
        swt, temp = ensure_staging(root, cfg)
        return run_issue(a, root, cfg, swt, cap)
    finally:
        if swt and temp:
            remove_wt(root, swt)
        git(["worktree", "prune"], root, check=False)
        try:
            os.remove(lock)
        except OSError:
            pass


def run_issue(a, root, cfg, swt, cap):
    staging = cfg["staging_branch"]
    iss = pick_issue(swt, a.issue, a.next)
    if iss is None:
        print("runner: no open issue with an approved PRD: nothing to do")
        return 0
    prd = iss["meta"]["prd"]
    run_id = "%s-%s" % (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), iss["id"])
    print("runner: run %s, issue %s (%s), model %s, up to %d attempt(s), staging %s" % (run_id, iss["id"], iss["title"][:60], cfg["model"], cap, staging))
    mine, prev, stop, merged = [], [], None, False
    try:
        for k in range(1, cap + 1):
            stop = budget_stop(load_rows(swt), run_id, cfg)
            if stop:
                print("runner: stopped before attempt %d: %s" % (k, stop))
                S.append_row(rows_path(swt), {"ts": now(), "kind": "stop", "run": run_id, "issue": iss["id"], "attempt": k,
                                              "cost_usd": 0, "reason": stop})
                break
            row, reasons = attempt(root, cfg, iss, prd, run_id, k, prev, cfg["model"], cfg["review_model"], staging)
            S.append_row(rows_path(swt), row)
            mine.append(row)
            print("runner: attempt %d: gate %s, review %s, %s, $%.2f" % (k, row["gate"], row["review"], row["outcome"] if row["outcome"] == "pass"
                                                                         else "codes " + (",".join(row["codes"]) or "-"), row["cost_usd"]))
            if row["outcome"] == "pass":
                merged = True
                break
            prev = reasons
        if merged:
            row = mine[-1]
            m = git(["merge", "--no-ff", "-q", "-m", "runner: merge fix/%s (%s)\n\nRefs: %s\nRunner: %s" % (iss["id"], iss["title"][:60], iss["id"], run_id),
                     "fix/" + iss["id"]], swt, check=False)
            if m.returncode != 0:
                git(["merge", "--abort"], swt, check=False)
                raise Refuse("merge into %s failed: %s" % (staging, (m.stderr or m.stdout).strip()[:200]))
            row["outcome"] = "merged"
            rewrite_last(swt, row)
            with contextlib.redirect_stdout(io.StringIO()):
                L.main(["--root", swt, "sync"])
            commit_ledger(swt, "runner: %s fixed (run %s)\n\nRefs: %s\nRunner: %s" % (iss["id"], run_id, iss["id"], run_id))
            git(["branch", "-q", "-d", "fix/" + iss["id"]], root, check=False)
            print("runner: %s fixed and merged into %s (not pushed, not promoted)" % (iss["id"], staging))
            return 0
        if stop:
            return 3
        S.append_row(rows_path(swt), {"ts": now(), "kind": "park", "run": run_id, "issue": iss["id"], "attempt": len(mine), "cost_usd": 0,
                                      "codes": mine[-1]["codes"] if mine else []})
        L.cmd_block(swt, iss["id"], attempt_log(run_id, cfg["model"], mine) + ("\n\nLast gate reasons:\n" + "\n".join(prev) if prev else ""))
        print("runner: %s parked in issues/blocked/ after %d attempt(s); nothing merged (branch fix/%s kept to inspect)" % (iss["id"], len(mine), iss["id"]))
        return 1
    finally:
        remove_wt(root, wt_dir(root, "runner-" + iss["id"]))
        commit_ledger(swt, "runner: %s %s (run %s)\n\nRefs: %s\nRunner: %s" % (
            iss["id"], "stopped by a budget cap" if stop else "parked" if not merged else "rows", run_id, iss["id"], run_id))


def rewrite_last(swt, row):
    """Replace the last row of the rows file (the attempt that was just merged) with its final outcome."""
    p = rows_path(swt)
    with open(p, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    lines[-1] = json.dumps(row, sort_keys=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def cmd_status(a, root):
    st = summary(root)
    print(json.dumps(st, indent=1) if a.json else human(st))
    return 0


def cmd_unpark(a, root):
    cfg = settings(root)
    swt, temp = ensure_staging(root, cfg)
    try:
        r = L.cmd_unpark(swt, a.issue)
        S.append_row(rows_path(swt), {"ts": now(), "kind": "unpark", "run": "-", "issue": r["unparked"], "cost_usd": 0})
        commit_ledger(swt, "runner: unpark %s\n\nRefs: %s" % (r["unparked"], r["unparked"]))
        print("runner: %s unparked on %s: `runner.py run --issue %s` to try again" % (r["unparked"], cfg["staging_branch"], r["unparked"]))
        return 0
    finally:
        if temp:
            remove_wt(root, swt)


def main(argv=None, root=None):
    ap = argparse.ArgumentParser(prog="runner.py", description="Fixer runner (docs/policies/runner.md)")
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run")
    s.add_argument("--issue")
    s.add_argument("--next", action="store_true")
    s.add_argument("--model")
    s.add_argument("--max-attempts", type=int)
    s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("unpark")
    s.add_argument("issue")
    try:
        a = ap.parse_args(argv)
    except SystemExit as ex:
        return 0 if ex.code in (0, None) else 2
    root = os.path.abspath(a.root or root or os.getcwd())
    try:
        return {"run": cmd_run, "status": cmd_status, "unpark": cmd_unpark}[a.cmd](a, root)
    except (Refuse, L.Usage) as ex:
        print("runner: refused: %s" % ex, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

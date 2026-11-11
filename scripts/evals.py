#!/usr/bin/env python3
"""Agent eval harness: run a fixed task suite against the factory in disposable copies, grade, compare.

  python3 scripts/evals.py list
  python3 scripts/evals.py run [--task ID] [--n N] [--model M] [--set NAME]   # spends money; manual only
  python3 scripts/evals.py baseline [--set NAME]    # promote a run set (default: latest) to metrics/evals-baseline.json
  python3 scripts/evals.py compare  [--set NAME]    # per-task and per-gate deltas vs baseline; exit 1 on a regression

Each run: git-tracked files of this repo (working-tree content, so uncommitted template changes are tested)
-> fresh temp dir, made a project copy (no `origin`, so not template mode; docs/specs/template-mode.md),
base project + task fixture overlaid, baseline git commit, then headless `claude -p` with cwd = that dir and a
scrubbed environment. Graders (scripts/evals_graders.py) look at the files and the tool-call log. One row per
run goes to metrics/evals.jsonl; raw transcripts to metrics/eval-transcripts/ (git-ignored, pruned after 30 days).
Settings come from factory.json `evals`. Never run in CI (docs/policies/evals.md). Stdlib only.
Exit codes: 0 ok, 1 regression (compare) or no results, 2 usage/config error.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evals_graders as G  # noqa: E402

TASKS_DIR = os.path.join(ROOT, "evals", "tasks")
BASE_DIR = os.path.join(ROOT, "evals", "base")
RESULTS = os.path.join(ROOT, "metrics", "evals.jsonl")
BASELINE = os.path.join(ROOT, "metrics", "evals-baseline.json")
TRANSCRIPTS = os.path.join(ROOT, "metrics", "eval-transcripts")
TRANSCRIPT_DAYS = 30
DEFAULTS = {"n": 3, "model": "sonnet", "budget_usd": 5, "regression_threshold": 0.34, "max_turns": 30,
            "timeout_s": 600}
# Never copied into the sandbox: the graders, fixtures and docs that describe them, and this repo's own handoff note.
EXCLUDE = (".factory/HANDOFF.md", "evals/", "scripts/evals.py", "scripts/evals_graders.py", ".factory/tests/test_evals.py",
           "metrics/evals", "metrics/eval-transcripts/", "docs/policies/evals.md",
           "docs/decisions/0006-agent-eval-harness.md", "docs/specs/agent-eval-harness.md")
# Environment variables the sandboxed agent may see. Everything else (CLOUDFLARE_*, GITHUB_*, GH_*, AWS_*, cloud and
# SSH variables, CLAUDE_CODE_* of this session) is dropped. The first group is what claude needs to reach the API.
ENV_ALLOW = ("PATH", "LANG", "LC_ALL", "TERM", "TZ",
             "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
             "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
             "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
TOOLS = "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Skill,Task,Agent,TodoWrite"
GIT_ID = ["-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false"]
TASK_KEYS = ("id", "title", "gates", "prompt", "max_turns", "graders")


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def settings():
    try:
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            cfg = json.load(fh).get("evals") or {}
    except (OSError, ValueError):
        cfg = {}
    return {**DEFAULTS, **cfg}


# ---------- suite ----------
def load_tasks(tasks_dir=None):
    tasks = []
    d = tasks_dir or TASKS_DIR
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        p = os.path.join(d, name, "task.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                t = json.load(fh)
            t["_dir"] = os.path.join(d, name)
            tasks.append(t)
    return tasks


def validate_task(t):
    """List of schema problems for a task (empty = valid): AC1, a prompt, gates and deterministic graders."""
    errs = []
    for k in TASK_KEYS:
        if not t.get(k):
            errs.append("missing %s" % k)
    if errs:
        return errs
    if t["id"] != os.path.basename(t.get("_dir", t["id"])):
        errs.append("id does not match directory name")
    if not isinstance(t["max_turns"], int) or t["max_turns"] < 1:
        errs.append("max_turns must be a positive int")
    seen = set()
    for g in t["graders"]:
        gid = g.get("id")
        if not gid or gid in seen:
            errs.append("grader id missing or duplicate: %s" % gid)
        seen.add(gid)
        if g.get("type") not in G.GRADERS:
            errs.append("unknown grader type %s" % g.get("type"))
        if g.get("gate") not in t["gates"]:
            errs.append("grader %s gate %s is not in the task's gates" % (gid, g.get("gate")))
    for gate in t["gates"]:
        if not any(g.get("gate") == gate for g in t["graders"]):
            errs.append("gate %s has no grader" % gate)
    return errs


# ---------- sandbox ----------
def git(args, cwd, **kw):
    return subprocess.run(["git", *GIT_ID, *args], cwd=cwd, capture_output=True, text=True, check=kw.get("check", True),
                          env={"PATH": os.environ.get("PATH", ""), "HOME": cwd, "GIT_CONFIG_GLOBAL": os.devnull,
                               "GIT_CONFIG_SYSTEM": os.devnull})


def template_sha():
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\0") if f and not f.startswith(EXCLUDE) and os.path.isfile(os.path.join(ROOT, f))]


def overlay(src, dst):
    for base, _, files in os.walk(src):
        for f in files:
            s = os.path.join(base, f)
            d = os.path.join(dst, os.path.relpath(s, src))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)


def generate(dst, specs):
    """task.json `generate`: [{path, line (uses {i}), count, overrides: {"<i>": text}}] for big fixture files."""
    for g in specs or []:
        p = os.path.join(dst, g["path"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        ov = g.get("overrides") or {}
        with open(p, "w", encoding="utf-8") as fh:
            for i in range(1, int(g["count"]) + 1):
                fh.write(ov.get(str(i), g["line"].format(i=i)) + "\n")


def make_project(factory_path):
    with open(factory_path, encoding="utf-8") as fh:
        f = json.load(fh)
    f["project"] = {"name": "evalproj", "one_liner": "tiny text utility library"}
    f["phase"] = "build"
    f["paths"] = {"primary": "library-cli", "secondary": []}
    cmd = "python3 -m unittest discover -s tests -q"
    f["commands"].update(test=cmd, test_affected=cmd)
    f.pop("evals", None)
    with open(factory_path, "w", encoding="utf-8") as fh:
        json.dump(f, fh, indent=2)
        fh.write("\n")


def prepare_workdir(task, dst):
    """Disposable copy of the template as a project (or as the template, if task.template_mode), baseline committed."""
    for rel in tracked_files():
        d = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), d)
    if not task.get("template_mode"):
        make_project(os.path.join(dst, "factory.json"))
        overlay(BASE_DIR, dst)
    fx = os.path.join(task["_dir"], "fixture")
    if os.path.isdir(fx):
        overlay(fx, dst)
    generate(dst, task.get("generate"))
    for w in task.get("write") or []:  # files the repo's .gitignore would keep out of fixture/ (e.g. .env)
        with open(os.path.join(dst, w["path"]), "w", encoding="utf-8") as fh:
            fh.write(w["content"])
    git(["init", "-q", "-b", "main"], dst)
    git(["add", "-A", "-f"], dst)
    git(["commit", "-q", "-m", "eval baseline"], dst)
    if task.get("template_mode"):  # looks like the template repo itself: origin = template.source_repo
        with open(os.path.join(dst, "factory.json"), encoding="utf-8") as fh:
            src = json.load(fh)["template"]["source_repo"]
        git(["remote", "add", "origin", "https://github.com/%s" % src], dst)
    return dst


def scrubbed_env(src, home, tmp):
    """Allow-listed variables only, HOME and TMPDIR pointing at throwaway dirs. EVALS_HOME=real keeps the real HOME
    (needed where claude logs in via ~/.claude; the agent can then read that login, see docs/policies/evals.md)."""
    env = {k: src[k] for k in ENV_ALLOW if k in src}
    env.update(HOME=src.get("HOME", home) if src.get("EVALS_HOME") == "real" else home, TMPDIR=tmp,
               GIT_TERMINAL_PROMPT="0", CODEGRAPH_TELEMETRY="0")
    return env


def claude_cmd(model, max_turns):
    return ["claude", "-p", "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--model", model, "--max-turns", str(max_turns), "--permission-mode", "acceptEdits",
            "--allowedTools", TOOLS, "--no-session-persistence"]


def run_claude(prompt, model, max_turns, cwd, env, timeout):
    """Real model call. The prompt goes on stdin (--allowedTools is variadic and would swallow a positional)."""
    try:
        p = subprocess.run(claude_cmd(model, max_turns), input=prompt, cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=timeout, check=False)
        return p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return out, 124


def parse_events(text):
    ev = []
    for line in (text or "").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            ev.append(obj)
    return ev


def hooks_fired(events):
    names = set()
    for e in events:
        if e.get("type") == "system" and str(e.get("subtype", "")).startswith("hook_"):
            names.add(str(e.get("hook_name") or e.get("hook_event") or "hook"))
    return sorted(names)


def hook_evidence(events):
    """Per-run proof that a guard acted (docs/policies/evals.md): {fired, blocked, guard_blocks}.
    fired = hook names that responded; blocked = hooks whose response was not a success (a PreToolUse hook exiting 2
    blocks the call; exit_code/outcome say so); guard_blocks = tool calls whose result shows a guard stopped them
    (hook error text or a settings deny rule), which also catches blocks the stream shows only in the tool result."""
    fired, blocked = set(), set()
    for e in events or []:
        if e.get("type") == "system" and e.get("subtype") == "hook_response":
            name = str(e.get("hook_name") or e.get("hook_event") or "hook")
            fired.add(name)
            code = str(e.get("exit_code", "0"))
            if code not in ("0", "") or str(e.get("outcome", "success")) not in ("success", ""):
                blocked.add(name)
    return {"fired": sorted(fired), "blocked": sorted(blocked),
            "guard_blocks": sum(1 for c in G.tool_calls(events) if c["blocked"])}


# ---------- one run ----------
def run_once(task, model, set_id, idx, claude_fn=None, cfg=None):
    cfg = cfg or settings()
    claude_fn = claude_fn or run_claude
    run_id = "%s-%s-%d" % (set_id, task["id"], idx)
    tmp = tempfile.mkdtemp(prefix="evals-")
    try:
        work = prepare_workdir(task, os.path.join(tmp, "project"))
        home, scratch = os.path.join(tmp, "home"), os.path.join(tmp, "tmp")
        os.makedirs(home)
        os.makedirs(scratch)
        env = scrubbed_env(os.environ, home, scratch)
        t0 = time.time()
        out, rc = claude_fn(task["prompt"], model, task["max_turns"], work, env, cfg["timeout_s"])
        wall = time.time() - t0
        events = parse_events(out)
        results_ev = [e for e in events if e.get("type") == "result"]  # >1 when a background subagent wakes the agent
        error = None if results_ev else "no result event (claude exit %s)" % rc
        results = {}
        for spec in task["graders"]:
            ok, detail = G.run_grader(spec, work, events)
            results[spec["id"]] = {"ok": bool(ok), "gate": spec["gate"], "detail": detail}
        gates = {g: all(r["ok"] for r in results.values() if r["gate"] == g) for g in task["gates"]}
        usage = [e.get("usage") or {} for e in results_ev]
        u = {k: sum(x.get(k, 0) or 0 for x in usage) for k in ("input_tokens", "cache_creation_input_tokens",
                                                              "cache_read_input_tokens", "output_tokens")}
        row = {"task": task["id"], "run_id": run_id, "set": set_id, "ts": now(),
               "graders": {k: v["ok"] for k, v in results.items()}, "gates": gates,
               "pass": error is None and all(gates.values()),
               "tokens_in": u.get("input_tokens", 0),
               "tokens_cache": u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
               "tokens_out": u.get("output_tokens", 0),
               "cost_usd": round(max([float(e.get("total_cost_usd") or 0) for e in results_ev] or [0]), 5),  # cumulative
               "turns": sum(e.get("num_turns", 0) or 0 for e in results_ev), "wall_s": round(wall, 1), "model": model,
               "template_sha": template_sha(), "hooks": hooks_fired(events), "hook_evidence": hook_evidence(events), "error": error,
               "details": {k: v["detail"] for k, v in results.items() if not v["ok"]}}
        return row, out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def append_row(row):
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def save_transcript(run_id, text):
    os.makedirs(TRANSCRIPTS, exist_ok=True)
    with open(os.path.join(TRANSCRIPTS, run_id + ".jsonl"), "w", encoding="utf-8") as fh:
        fh.write(text)


def prune_transcripts(days=TRANSCRIPT_DAYS):
    cutoff = time.time() - days * 86400
    for f in (os.listdir(TRANSCRIPTS) if os.path.isdir(TRANSCRIPTS) else []):
        p = os.path.join(TRANSCRIPTS, f)
        if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
            os.remove(p)


# ---------- suite run ----------
def run_suite(tasks, n, model, budget, set_id, claude_fn=None, cfg=None, out=print):
    """Round-robin (run 1 of every task, then run 2, ...) so a budget stop leaves even coverage.
    Stops before a run when cumulative cost + mean cost so far would exceed budget. Returns (rows, stop_reason)."""
    rows, spent, stop = [], 0.0, None
    prune_transcripts()
    for i in range(1, n + 1):
        for t in tasks:
            est = spent / len(rows) if rows else 0.0
            if rows and spent + est > budget:
                stop = "budget: $%.2f spent over %d runs, next run would pass the $%.2f cap (est $%.2f each)" % (
                    spent, len(rows), budget, est)
                break
            row, raw = run_once(t, model, set_id, i, claude_fn, cfg)
            append_row(row)
            save_transcript(row["run_id"], raw)
            rows.append(row)
            spent += row["cost_usd"]
            out("  %s #%d %s $%.3f %ss %s" % (t["id"], i, "pass" if row["pass"] else ("ERROR" if row["error"] else "FAIL"),
                                           row["cost_usd"], row["wall_s"], ",".join(k for k, v in row["gates"].items() if not v)))
        if stop:
            break
    return rows, stop


# ---------- results, baseline, compare ----------
def read_rows(path=None):
    rows = []
    try:
        with open(path or RESULTS, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("task") and r.get("set"):
                    rows.append(r)
    except OSError:
        pass
    return rows


def latest_set(rows):
    return rows[-1]["set"] if rows else None


def rates(rows):
    """{'tasks': {id: {runs, passes, rate}}, 'gates': {...}}; rows with an infra `error` are not counted."""
    t, g = {}, {}
    for r in rows:
        if r.get("error"):
            continue
        a = t.setdefault(r["task"], {"runs": 0, "passes": 0})
        a["runs"] += 1
        a["passes"] += 1 if r.get("pass") else 0
        for gate, ok in (r.get("gates") or {}).items():
            b = g.setdefault(gate, {"runs": 0, "passes": 0})
            b["runs"] += 1
            b["passes"] += 1 if ok else 0
    for d in (t, g):
        for v in d.values():
            v["rate"] = round(v["passes"] / v["runs"], 3) if v["runs"] else 0.0
    return {"tasks": t, "gates": g}


def make_baseline(rows, set_id):
    sel = [r for r in rows if r["set"] == set_id]
    if not sel:
        return None
    return {"set": set_id, "ts": now(), "model": sel[0].get("model"), "template_sha": sel[0].get("template_sha"),
            "n": max((rates(sel)["tasks"][k]["runs"] for k in rates(sel)["tasks"]), default=0), **rates(sel)}


def compare(base, cur, threshold):
    """(report lines, regressed: bool). Regression = pass-rate drop strictly greater than threshold."""
    lines, bad = [], False
    for kind in ("tasks", "gates"):
        lines.append("%s:" % kind)
        for key in sorted(set(base.get(kind, {})) | set(cur.get(kind, {}))):
            b, c = base.get(kind, {}).get(key), cur.get(kind, {}).get(key)
            if not b or not c:
                lines.append("  %-24s %s" % (key, "new (no baseline)" if not b else "not in this set"))
                continue
            delta = round(c["rate"] - b["rate"], 3)
            reg = delta < -threshold
            bad = bad or reg
            flaky = " flaky" if kind == "tasks" and 0 < c["passes"] < c["runs"] else ""
            lines.append("  %-24s %d/%d (%.0f%%) vs %d/%d (%.0f%%) %+.0f pts%s%s" % (
                key, c["passes"], c["runs"], c["rate"] * 100, b["passes"], b["runs"], b["rate"] * 100, delta * 100,
                " REGRESSION" if reg else "", flaky))
    return lines, bad


# ---------- cli ----------
def cmd_list(a):
    for t in load_tasks():
        print("%-20s gates=%s turns=%s graders=%s  %s" % (t["id"], ",".join(t["gates"]), t["max_turns"],
              ",".join(g["type"] for g in t["graders"]), t["title"]))
    return 0


def cmd_run(a):
    cfg = settings()
    tasks = load_tasks()
    bad = [(t.get("id"), validate_task(t)) for t in tasks if validate_task(t)]
    if bad:
        print("invalid tasks: %s" % bad)
        return 2
    if a.task:
        tasks = [t for t in tasks if t["id"] in a.task]
        if not tasks:
            print("no such task: %s" % ",".join(a.task))
            return 2
    n, model = a.n or cfg["n"], a.model or cfg["model"]
    set_id = a.set or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print("evals: %d task(s) x %d, model %s, budget $%s, set %s" % (len(tasks), n, model, cfg["budget_usd"], set_id))
    rows, stop = run_suite(tasks, n, model, float(cfg["budget_usd"]), set_id, cfg=cfg)
    r = rates(rows)
    ok = [x for x in rows if x["pass"]]
    cost = sum(x["cost_usd"] for x in rows)
    tok = sum(x["tokens_in"] + x["tokens_cache"] + x["tokens_out"] for x in rows)
    reg = "n/a"
    try:
        with open(BASELINE, encoding="utf-8") as fh:
            reg = "yes" if compare(json.load(fh), r, float(cfg["regression_threshold"]))[1] else "no"
    except (OSError, ValueError):
        pass
    flaky = [k for k, v in r["tasks"].items() if 0 < v["passes"] < v["runs"]]
    print("evals: %d/%d runs passed, %d tokens, $%.2f, regression %s%s -> %s" % (
        len(ok), len(rows), tok, cost, reg, ", flaky: " + ",".join(flaky) if flaky else "",
        os.path.relpath(RESULTS, ROOT)))
    if stop:
        print("evals: stopped early, " + stop)
    return 0 if rows else 1


def cmd_baseline(a):
    rows = read_rows()
    sid = a.set or latest_set(rows)
    b = make_baseline(rows, sid) if sid else None
    if not b:
        print("no rows for set %s in %s" % (sid, os.path.relpath(RESULTS, ROOT)))
        return 1
    with open(BASELINE, "w", encoding="utf-8") as fh:
        json.dump(b, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("baseline: set %s (%d tasks, N=%d, model %s) -> %s" % (sid, len(b["tasks"]), b["n"], b["model"],
                                                               os.path.relpath(BASELINE, ROOT)))
    return 0


def cmd_compare(a):
    rows = read_rows()
    sid = a.set or latest_set(rows)
    try:
        with open(BASELINE, encoding="utf-8") as fh:
            base = json.load(fh)
    except (OSError, ValueError):
        print("no baseline: run `evals.py baseline` first")
        return 1
    cur = rates([r for r in rows if r["set"] == sid])
    if not cur["tasks"]:
        print("no rows for set %s" % sid)
        return 1
    th = float(settings()["regression_threshold"])
    lines, bad = compare(base, cur, th)
    print("compare: set %s vs baseline %s (threshold %.0f pts)" % (sid, base.get("set"), th * 100))
    print("\n".join(lines))
    print("compare: %s" % ("REGRESSION" if bad else "no regression"))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("--task", action="append")
    r.add_argument("--n", type=int)
    r.add_argument("--model")
    r.add_argument("--set")
    for name in ("baseline", "compare"):
        sub.add_parser(name).add_argument("--set")
    a = ap.parse_args(argv)
    return {"list": cmd_list, "run": cmd_run, "baseline": cmd_baseline, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fixer runner (AUTO-4): one issue, one sandboxed agent, the gate decides, merges go to staging only. Stdlib only.
Design: docs/decisions/0009-fixer-runner.md. Policy: docs/policies/runner.md. PRD: docs/specs/gated-autonomy.md (C4).

  runner.py run [--issue ISS-n | --next] [--model M] [--max-attempts N] [--dry-run]   # spends money; you start every run
  runner.py run --next --parallel N [--scheduled]   # AUTO-6: N fixers (N <= autonomy.max_parallel, cap 4), merges serial
  runner.py status [--json]
  runner.py unpark ISS-n

Per attempt (at most autonomy.max_attempts): fresh git worktree from the staging branch (.claude/worktrees/runner-ISS-n, branch
fix/ISS-n) -> headless fixer in the eval sandbox (scripts/sandbox.py) -> the runner commits with trailers it controls
(Refs, Fixer-Attempt, Runner) -> the issue's tests must pass -> an independent reviewer agent returns ship or fix-first and the
runner writes the Review trailer -> gate.py with review required -> pass: merge --no-ff into staging, issues sync, worktree
removed; fail: the next attempt gets the gate's reasons. After the cap the issue moves to issues/blocked/ with an attempt log.
The budget (autonomy.daily_budget_usd, run_budget_usd) is checked before every paid call, never after. Hardening (ADR 0009): fixer-written
code runs only in the tree sandbox on a fresh checkout of the commit; the reviewer is read-only in its own checkout. The runner never pushes
and never touches the production branch. Rows: metrics/runner.jsonl, committed on staging.
Parallel (AUTO-6, ADR 0010 C6): one worktree and fixer thread per issue (the paid work is separate claude processes), merges to staging
one at a time under a lock, each re-gated against the CURRENT staging tip (one rebase-and-regate, else `stale-after-merge`), one shared
budget (daily cap against all spend plus in-flight estimates), `--scheduled` only with autonomy.schedule_ok.
Exit codes: 0 fixed and merged (or nothing to do), 1 parked, 2 refused or usage error, 3 stopped by a budget cap."""
import argparse
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gate  # noqa: E402,F401
import issues as L  # noqa: E402
import sandbox as S  # noqa: E402
from runner_core import *  # noqa: E402,F401,F403
from runner_git import *  # noqa: E402,F401,F403
from runner_agent import *  # noqa: E402,F401,F403
from runner_attempt import *  # noqa: E402,F401,F403
from runner_pick import *  # noqa: E402,F401,F403
from runner_parallel import *  # noqa: E402,F401,F403


def preconditions(root, cfg, dry=False):
    if not cfg["enabled"]:
        raise Refuse("autonomy is not enabled: set factory.json autonomy.enabled to true (docs/policies/runner.md)")
    if not dry:
        problem = S.sandbox_problem() or S.tree_sandbox_problem()
        if problem:
            raise Refuse(problem)
    if git(["rev-parse", "--verify", "--quiet", "HEAD"], root, check=False).returncode != 0:
        raise Refuse("the project has no commit yet")
    if out_of(git(["status", "--porcelain"], root)):
        raise Refuse("the working tree is not clean: commit or stash first (the runner builds on committed state)")


def cmd_run(a, root):
    cfg = settings(root)
    if a.model:
        cfg["model"] = a.model
    if a.max_attempts is not None:
        cfg["max_attempts"] = a.max_attempts
    try:
        cap = int(cfg["max_attempts"])
    except (TypeError, ValueError):
        cap = 0
    if cap < 1:  # a configuration error, not a reason to park an issue after zero attempts
        raise Refuse("autonomy.max_attempts must be a whole number of at least 1 (got %r)" % (cfg["max_attempts"],))
    if not a.issue and not a.next:
        raise Refuse("give --issue ISS-n or --next")
    sched, par = bool(getattr(a, "scheduled", False)), getattr(a, "parallel", 1)
    if sched and cfg.get("schedule_ok") is not True:
        raise Refuse("--scheduled needs your standing go: set factory.json autonomy.schedule_ok to true (it is false by default; docs/policies/runner.md)")
    try:
        top = min(PARALLEL_CAP, int(cfg["max_parallel"]))
    except (TypeError, ValueError):
        top = 1
    if not isinstance(par, int) or par < 1 or par > max(top, 1):
        raise Refuse("--parallel %s is outside 1..%d (autonomy.max_parallel is %s, hard cap %d)" % (par, max(top, 1), cfg["max_parallel"], PARALLEL_CAP))
    if par > 1 and not a.next:
        raise Refuse("--parallel picks its own issues: use --next, not --issue")
    preconditions(root, cfg, a.dry_run)
    if a.dry_run:
        if par > 1:
            batch = pick_batch(root, par, sched)
            what = ", ".join(i["id"] for i in batch) or "nothing (no open issue with an approved PRD)"
        else:
            iss = pick_issue(root, a.issue, a.next, sched)
            what = iss["id"] if iss else "nothing (no open issue with an approved PRD)"
        rows = load_rows(root, cfg["staging_branch"])
        print("runner (dry run): would fix %s, up to %d attempt(s) each, model %s; spent today $%.2f of $%.2f; %s"
              % (what, cap, cfg["model"], spent(rows, today()), float(cfg["daily_budget_usd"]), budget_stop(rows, "dry-run", cfg) or "budget ok"))
        return 0
    lock = os.path.join(root, ".claude", "worktrees", ".runner.lock")
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    held, swt, temp = False, None, False
    try:
        acquire_lock(lock)
        held = True
        try:  # refuse before anything is created when the root's own ledger already shows the problem
            pick_issue(root, a.issue, a.next, sched)
        except L.Usage:
            pass  # the issue may exist on staging only; the staging ledger decides
        swt, temp = ensure_staging(root, cfg)
        if par > 1:
            return run_parallel(a, root, cfg, swt, cap, par, sched)
        return run_issue(a, root, cfg, swt, cap)
    finally:
        if swt and temp:
            remove_wt(root, swt)
        git(["worktree", "prune"], root, check=False)
        if held:
            try:
                os.remove(lock)
            except OSError:
                pass


LOCK_MAX_AGE = 2 * 3600


def acquire_lock(lock):
    """Create the lock file (pid inside). A lock whose process is gone or that is older than 2 hours is stale: reclaimed with a note."""
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            why = None
            try:
                age = time.time() - os.path.getmtime(lock)
                with open(lock, encoding="utf-8") as fh:
                    pid = int(fh.read().strip() or 0)
                if pid <= 0:
                    why = "no valid pid in it"
                elif age > LOCK_MAX_AGE:
                    why = "it is %.0f minutes old" % (age / 60)
                else:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        why = "process %d is gone" % pid
                    except PermissionError:
                        pass  # alive, owned by someone else
            except (OSError, ValueError):
                why = "unreadable"
            if not why:
                raise Refuse("another runner is active (%s)" % lock)
            print("runner: reclaimed a stale lock (%s)" % why)
            try:
                os.remove(lock)
            except OSError:
                pass
            continue
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return
    raise Refuse("could not take the runner lock %s" % lock)


def run_issue(a, root, cfg, swt, cap):
    staging = cfg["staging_branch"]
    iss = pick_issue(swt, a.issue, a.next, bool(getattr(a, "scheduled", False)))
    if iss is None:
        print("runner: no open issue with an approved PRD: nothing to do")
        return 0
    prd = iss["meta"]["prd"]
    run_id = "%s-%s" % (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), iss["id"])
    print("runner: run %s, issue %s (%s), model %s, up to %d attempt(s), staging %s" % (run_id, iss["id"], iss["title"][:60], cfg["model"], cap, staging))
    sick = base_problem(root, swt, run_id)
    if sick:  # pilot 2: a stale docs index on staging failed every attempt; nothing paid starts on a base that already fails
        print("runner: refused before any paid call: the staging base already fails the gate: %s" % sick)
        S.append_row(rows_path(swt), {"ts": now(), "kind": "base-unhealthy", "run": run_id, "issue": iss["id"], "cost_usd": 0,
                                      "detail": sick[:1000]})
        return 1
    mine, prev, stop, merged = [], [], None, False
    try:
        for k in range(1, cap + 1):
            stop = budget_stop(load_rows(swt), run_id, cfg)
            if stop:
                print("runner: stopped before attempt %d: %s" % (k, stop))
                S.append_row(rows_path(swt), {"ts": now(), "kind": "stop", "run": run_id, "issue": iss["id"], "attempt": k,
                                              "cost_usd": 0, "reason": stop})
                break
            rows_now = load_rows(swt)
            before = remaining(rows_now, run_id, cfg)
            row, reasons = attempt(root, cfg, iss, prd, run_id, k, prev, cfg["model"], cfg["review_model"], staging, lambda: before,
                                   estimate(rows_now, cfg))
            S.append_row(rows_path(swt), row)
            mine.append(row)
            if "budget-stop" in row["codes"]:
                stop = reasons[0]
                print("runner: stopped during attempt %d: %s" % (k, stop))
                S.append_row(rows_path(swt), {"ts": now(), "kind": "stop", "run": run_id, "issue": iss["id"], "attempt": k, "cost_usd": 0,
                                              "reason": stop})
                break
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
            sync_ledger(root, swt, run_id)
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
    s.add_argument("--parallel", type=int, default=1, metavar="N")
    s.add_argument("--scheduled", action="store_true")
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
    import runner  # the imported copy: runner_* modules share one set of names with it
    sys.exit(runner.main())

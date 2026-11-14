"""Fixer runner parallel mode (AUTO-6, ADR 0010 C6): shared budget, serial merges, ledger sync.
Split from scripts/runner.py (SIZE-3); `runner` re-exports every name, so `runner.<name>` still works."""
import concurrent.futures
import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import issues as L  # noqa: E402
import sandbox as S  # noqa: E402

from runner_core import (BASELINE, Fail, MERGE_LOCK, ROWS_LOCK, budget_stop, estimate, git, load_rows, now, out_of,
                         remaining, rows_path, today)
from runner_git import checkout, commit_ledger, remove_wt, wt_dir
from runner_attempt import attempt, base_problem, gate_reasons, gate_verdict
from runner_pick import attempt_log, pick_batch


class Shared:
    """Budget and rows shared by the parallel fixers. One lock: the daily cap is checked against all spend booked so far plus the
    estimate of every attempt still running, so the fixers cannot together pass the cap; rows are appended one at a time."""

    def __init__(self, swt, cfg, run_id):
        self.swt, self.cfg, self.run_id = swt, cfg, run_id
        self.lock = threading.RLock()
        self.inflight, self.peak = {}, 0

    def _others(self, key):
        return sum(v for k, v in self.inflight.items() if k != key)

    def begin(self, key):
        """(reason to stop or None, estimate). On success the attempt's estimate counts against everybody else's budget."""
        with self.lock:
            rows = load_rows(self.swt)
            est = estimate(rows, self.cfg)
            stop = budget_stop(rows, self.run_id, self.cfg, extra=self._others(key))
            if not stop:
                self.inflight[key] = est
                self.peak = max(self.peak, len(self.inflight))
            return stop, est

    def left(self, key):
        with self.lock:
            return remaining(load_rows(self.swt), self.run_id, self.cfg, extra=self._others(key))

    def append(self, row):
        with self.lock, ROWS_LOCK:
            S.append_row(rows_path(self.swt), row)

    def end(self, key, row=None):
        """Book the attempt (its row) and drop its in-flight estimate in one step, so the cost is never counted twice or not at all."""
        with self.lock:
            if row is not None:
                self.append(row)
            self.inflight.pop(key, None)


def land(root, swt, iss, row, staging):
    """Under MERGE_LOCK: merge the passing fix into staging, re-gated against the CURRENT tip first. None when merged, else the
    reason it became a failed attempt (`stale-after-merge`). The fix was gated against the tip it started from; when staging moved
    since, the fix is rebased onto the tip once and its tests and the gate run again on a fresh checkout of the result."""
    name, branch = "runner-" + iss["id"], "fix/" + iss["id"]
    sha = out_of(git(["rev-parse", "refs/heads/" + branch], root))
    tip = out_of(git(["rev-parse", "HEAD"], swt))
    if git(["merge-base", "--is-ancestor", tip, sha], root, check=False).returncode != 0:
        row["regated_on"] = tip[:9]
        try:
            with checkout(root, sha, name + "-rebase") as rb:
                r = rb.g(["rebase", tip], check=False)
                if r.returncode != 0:
                    rb.g(["rebase", "--abort"], check=False)
                    return "- staging moved while this fix was running and the fix conflicts with it (rebase failed): " + " ".join((r.stderr or r.stdout).split())[:200]
                new = rb.head()
            with checkout(root, new, name + "-retests") as t, S.TreeSandbox(t.path) as ts:
                tests, _adm = L.results(t.path, None, env=ts.acceptance_env())
            still = sorted(x for x in iss["tests"] if tests.get(x, {}).get("status") != "pass")
            if still:
                return "- after rebasing onto the new staging tip the issue tests fail: %s" % ", ".join(still[:5])
            with checkout(root, new, name + "-regate") as gt:
                v = gate_verdict(gt.path, tip)
            if v["verdict"] != "pass":
                return "- after rebasing onto the new staging tip the gate fails:\n" + "\n".join(gate_reasons(v))
            sha = new
        except (Fail, L.Usage, S.SandboxUnavailable) as ex:
            return "- the re-check against the new staging tip did not run: %s" % str(ex)[:200]
    m = git(["merge", "--no-ff", "-q", "-m", "runner: merge fix/%s (%s)\n\nRefs: %s\nRunner: %s" % (iss["id"], iss["title"][:60], iss["id"], row["run"]), sha], swt, check=False)
    if m.returncode != 0:
        git(["merge", "--abort"], swt, check=False)
        return "- merge into %s failed: %s" % (staging, " ".join((m.stderr or m.stdout).split())[:200])
    return None


def fix_one(sh, root, cfg, swt, iss, cap):
    """One fixer thread: up to `cap` attempts for one issue. Returns (issue id, outcome: merged|parked|stopped, message)."""
    key, staging, run_id = iss["id"], cfg["staging_branch"], sh.run_id
    prd, mine, prev, stop = iss["meta"]["prd"], [], [], None
    try:
        for k in range(1, cap + 1):
            stop, est = sh.begin(key)
            if stop:
                with MERGE_LOCK:
                    sh.append({"ts": now(), "kind": "stop", "run": run_id, "issue": key, "attempt": k, "cost_usd": 0, "reason": stop})
                break
            row = None
            try:
                row, reasons = attempt(root, cfg, iss, prd, run_id, k, prev, cfg["model"], cfg["review_model"], staging, lambda: sh.left(key), est)
                if row["outcome"] == "pass":
                    with MERGE_LOCK:
                        why = land(root, swt, iss, row, staging)
                        if why:
                            row["outcome"], row["codes"] = "fail", row["codes"] + ["stale-after-merge"]
                            row["detail"] = why[:1000]
                            reasons = [why]
                            sh.end(key, row)
                        else:
                            row["outcome"] = "merged"
                            sh.end(key, row)
                            remove_wt(root, wt_dir(root, "runner-" + key))
                            git(["branch", "-q", "-D", "fix/" + key], root, check=False)
                            sync_ledger(root, swt, run_id)
                            commit_ledger(swt, "runner: %s fixed (run %s)\n\nRefs: %s\nRunner: %s" % (key, run_id, key, run_id))
                else:
                    sh.end(key, row)
            finally:
                sh.end(key)  # a crash must not leave an estimate in flight (no-op when the row was booked)
            mine.append(row)
            if "budget-stop" in row["codes"]:
                stop = reasons[0]
                with MERGE_LOCK:
                    sh.append({"ts": now(), "kind": "stop", "run": run_id, "issue": key, "attempt": k, "cost_usd": 0, "reason": stop})
                break
            if row["outcome"] == "merged":
                return key, "merged", "attempt %d: merged into %s ($%.2f)" % (k, staging, row["cost_usd"])
            prev = reasons
        if stop:
            return key, "stopped", "stopped by a budget cap: " + stop
        with MERGE_LOCK:
            sh.append({"ts": now(), "kind": "park", "run": run_id, "issue": key, "attempt": len(mine), "cost_usd": 0,
                       "codes": mine[-1]["codes"] if mine else []})
            L.cmd_block(swt, key, attempt_log(run_id, cfg["model"], mine) + ("\n\nLast gate reasons:\n" + "\n".join(prev) if prev else ""))
        return key, "parked", "parked in issues/blocked/ after %d attempt(s) (codes %s; branch fix/%s kept)" % (len(mine), ",".join(mine[-1]["codes"]) or "-", key)
    finally:
        remove_wt(root, wt_dir(root, "runner-" + key))
        with MERGE_LOCK:
            commit_ledger(swt, "runner: %s %s (run %s)\n\nRefs: %s\nRunner: %s" % (key, "rows", run_id, key, run_id))


def run_parallel(a, root, cfg, swt, cap, n, scheduled):
    """`run --next --parallel N`: N fixers on issues that share no failing test or fingerprint; merges are serial."""
    staging = cfg["staging_branch"]
    batch = pick_batch(swt, n, scheduled)
    if not batch:
        print("runner: no open issue with an approved PRD%s: nothing to do" % (" that is in progress ([~])" if scheduled else ""))
        return 0
    run_id = "%s-par%d" % (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), len(batch))
    print("runner: run %s, %d fixer(s) in parallel on %s, model %s, up to %d attempt(s) each, staging %s"
          % (run_id, len(batch), ", ".join(i["id"] for i in batch), cfg["model"], cap, staging))
    sick = base_problem(root, swt, run_id)
    if sick:
        print("runner: refused before any paid call: the staging base already fails the gate: %s" % sick)
        S.append_row(rows_path(swt), {"ts": now(), "kind": "base-unhealthy", "run": run_id, "issue": ",".join(i["id"] for i in batch),
                                      "cost_usd": 0, "detail": sick[:1000]})
        return 1
    sh = Shared(swt, cfg, run_id)
    res = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as ex:
            futs = [ex.submit(fix_one, sh, root, cfg, swt, iss, cap) for iss in batch]
            for f in futs:
                res.append(f.result())
    finally:
        sh.append({"ts": now(), "kind": "parallel", "run": run_id, "workers": len(batch), "max_concurrent": sh.peak, "cost_usd": 0,
                   "issues": [i["id"] for i in batch]})
        with MERGE_LOCK:
            commit_ledger(swt, "runner: parallel run %s\n\nRefs: %s\nRunner: %s" % (run_id, batch[0]["id"], run_id))
    for key, outcome, msg in res:
        print("runner: %s %s" % (key, msg))
    outs = {r[1] for r in res}
    print("runner: parallel run done: %s (max %d fixer(s) at once; nothing pushed, nothing promoted)" % (", ".join("%s %s" % (r[0], r[1]) for r in res), sh.peak))
    return 3 if "stopped" in outs else 1 if "parked" in outs else 0


def sync_ledger(root, swt, run_id):
    """issues.py sync on the merged state. The acceptance suite executes the merged fixer code, so it runs on a fresh checkout of the
    merge commit in the tree sandbox; sync then reads those results (--from-json) instead of running anything itself."""
    head = out_of(git(["rev-parse", "HEAD"], swt))
    tmp = tempfile.mkdtemp(prefix="runner-sync-")
    try:
        with checkout(root, head, "runner-sync") as t, S.TreeSandbox(t.path) as ts:
            tests, adm = L.results(t.path, None, env=ts.acceptance_env())
        path = os.path.join(tmp, "results.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"tests": list(tests.values()), "admitted": sorted(adm)}, fh)
        with contextlib.redirect_stdout(io.StringIO()):
            L.main(["--root", swt, "sync", "--from-json", path])
        ratchet_baseline(swt, tests, adm)
    except (L.Usage, S.SandboxUnavailable, Fail) as ex:
        print("runner: could not sync the issue ledger (%s): run `python3 scripts/issues.py sync` yourself" % str(ex)[:120], file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ratchet_baseline(swt, tests, adm):
    """TD-019: record the admitted tests that pass on the fresh checkout of the merge in the baseline on staging (never shrinks),
    so the gate's acceptance-regression check protects them from now on. Committed with the merge rows by commit_ledger."""
    path = os.path.join(swt, BASELINE)
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = {}
    have = set(old.get("passing") or []) if isinstance(old, dict) else set()
    now = {t["id"] for t in tests.values() if t.get("status") == "pass" and t["id"] in adm}
    if now <= have:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"passing": sorted(have | now), "date": today(), "sha": out_of(git(["rev-parse", "--short", "HEAD"], swt))}, fh, indent=2)
        fh.write("\n")


def rewrite_last(swt, row):
    """Replace the last row of the rows file (the attempt that was just merged) with its final outcome."""
    p = rows_path(swt)
    with open(p, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    lines[-1] = json.dumps(row, sort_keys=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

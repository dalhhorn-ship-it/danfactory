"""Fixer runner attempt processes (AUTO-8, TD-020): with --parallel N each attempt (fixer, review, gate) runs in its own OS process,
`python3 scripts/runner.py attempt --json`, so gate runs no longer wait on each other and the gate's in-process WRAP/config patching
lives in that child only. The parent owns the budget and the rows: it answers the child's "how much is left" requests (so the
shared in-flight accounting stays in one place) and books the cost the child reports back with its row. Child protocol, on its stdin
and stdout (every line starts with the marker): parent -> one JSON line of parameters, then one number per `left` request;
child -> `left` requests and one final `result` line. Split from scripts/runner.py (SIZE-3); `runner` re-exports every name."""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from runner_core import now, share_wt_lock
from runner_attempt import attempt

MARK = "@@runner "


def attempt_in_process(root, cfg, iss, prd, run_id, k, prev, model, review_model, staging, left, est):
    """Parent side: run `attempt` in a child process. Returns (row, reasons) like `attempt`. A child that dies without a result
    is a failed attempt booked at the estimate (it may have spent money before it died)."""
    params = {"root": root, "cfg": cfg, "iss": iss, "prd": prd, "run_id": run_id, "k": k, "prev": prev, "model": model,
              "review_model": review_model, "staging": staging, "est": est, "left": left()}
    t0, result = time.time(), None
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err:
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "runner.py"), "--root", root, "attempt", "--json"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=err, text=True, cwd=root)
        try:
            try:
                p.stdin.write(json.dumps(params) + "\n")
                p.stdin.flush()
                for line in p.stdout:
                    if line.startswith(MARK + "left"):
                        p.stdin.write("%r\n" % float(left()))
                        p.stdin.flush()
                    elif line.startswith(MARK + "result "):
                        result = json.loads(line[len(MARK) + 7:])
            except (OSError, ValueError):
                pass  # the child went away or spoke nonsense: no result
            p.wait()
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
        err.seek(0)
        tail = " ".join(err.read().split())[-300:]
    if result and isinstance(result.get("row"), dict):
        return result["row"], list(result.get("reasons") or [])
    why = "- the attempt process died without a result (exit %s): %s" % (p.returncode, tail)
    row = {"ts": now(), "kind": "attempt", "run": run_id, "issue": iss["id"], "attempt": k, "model": model, "review_model": review_model,
           "cost_usd": round(est, 5), "fixer_cost_usd": round(est, 5), "review_cost_usd": 0.0, "cost_estimated": True, "tokens_in": 0,
           "tokens_cache": 0, "tokens_out": 0, "seconds": round(time.time() - t0, 1), "gate": "skip", "codes": ["attempt-crashed"],
           "review": "-", "outcome": "fail", "base": "-", "detail": why[:1000]}
    return row, [why]


def child_main(root):
    """Child side of `runner.py attempt --json`: parameters from stdin, the result on stdout; everything else goes to stderr."""
    out, sys.stdout = sys.stdout, sys.stderr
    a = json.loads(sys.stdin.readline())
    share_wt_lock(root)
    first = [a["left"]]

    def left():
        if first:  # the parent's figure at the start; later calls ask it again (it knows what the others spent meanwhile)
            return first.pop()
        out.write(MARK + "left\n")
        out.flush()
        return float(sys.stdin.readline())

    row, reasons = attempt(root, a["cfg"], a["iss"], a["prd"], a["run_id"], a["k"], a["prev"], a["model"], a["review_model"],
                           a["staging"], left, a["est"])
    out.write(MARK + "result " + json.dumps({"row": row, "reasons": reasons}) + "\n")
    out.flush()
    return 0
